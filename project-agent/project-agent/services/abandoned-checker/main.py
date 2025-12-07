# services/abandoned-checker/main.py
"""
Abandoned Projects Checker Service
Runs every 7 days to check abandoned projects.
If 30+ days without posting → status = 'removed' (stops monitoring).
If project posted again → status = 'active' (reactivates monitoring).
"""

import os
import sys
import time
import json
import redis
from datetime import datetime, timedelta

# Add shared modules to path
sys.path.insert(0, '/app/shared')
sys.path.insert(0, '/app')

from users.api_client import UserTweetsClient
from agent.database import get_connection

# Configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
CHECK_INTERVAL_DAYS = int(os.environ.get('CHECK_INTERVAL_DAYS', 7))
DAYS_TO_REMOVE = 30  # Days without posting to mark as removed

# Redis channels
CHANNEL_REACTIVATED = 'projects:reactivated'
CHANNEL_REMOVED = 'projects:removed'


class AbandonedChecker:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL)
        self.tweets_client = UserTweetsClient(verbose=True)
        
    def log(self, msg: str):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [ABANDONED-CHECKER] {msg}", flush=True)
    
    def get_abandoned_projects(self) -> list:
        """Get all projects with status 'abandoned'."""
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT id, twitter_handle, author_id, project_name, project_chain,
                   last_tweet_at, inactive_days, monitoring_status, updated_at
            FROM verified_projects 
            WHERE monitoring_status = 'abandoned'
        ''')
        
        rows = cur.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def check_latest_tweet(self, twitter_handle: str) -> dict:
        """Check the latest tweet from a user."""
        try:
            result = self.tweets_client.get_user_tweets(
                user_name=twitter_handle.lstrip('@'),
                include_replies=False
            )
            
            tweets = result.get('tweets', [])
            
            if tweets:
                latest = tweets[0]
                return {
                    'has_tweets': True,
                    'latest_at': latest.get('createdAt'),
                    'latest_text': latest.get('text', '')[:200]
                }
            else:
                return {'has_tweets': False}
                
        except Exception as e:
            self.log(f"[ERROR] Failed to fetch tweets for @{twitter_handle}: {str(e)[:50]}")
            return {'error': str(e)}
    
    def calculate_days_inactive(self, last_tweet_at: str) -> int:
        """Calculate days since last tweet."""
        if not last_tweet_at:
            return 999  # Very high number if no tweet date
        
        try:
            # Try parsing Twitter date format
            # Example: "Thu Dec 04 11:27:17 +0000 2025"
            last_dt = datetime.strptime(last_tweet_at, "%a %b %d %H:%M:%S %z %Y")
            now = datetime.now(last_dt.tzinfo)
            days = (now - last_dt).days
            return max(0, days)
        except:
            try:
                # Try ISO format
                last_dt = datetime.fromisoformat(last_tweet_at.replace('Z', '+00:00'))
                now = datetime.now(last_dt.tzinfo) if last_dt.tzinfo else datetime.now()
                days = (now - last_dt).days
                return max(0, days)
            except:
                return 999
    
    def update_project_status(self, project_id: int, new_status: str, updates: dict = None):
        """Update project status in database."""
        conn = get_connection()
        cur = conn.cursor()
        
        update_fields = ['monitoring_status = ?', 'updated_at = ?']
        values = [new_status, datetime.now().isoformat()]
        
        if updates:
            for field, value in updates.items():
                update_fields.append(f'{field} = ?')
                values.append(value)
        
        values.append(project_id)
        
        cur.execute(f'''
            UPDATE verified_projects 
            SET {', '.join(update_fields)}
            WHERE id = ?
        ''', values)
        
        conn.commit()
        conn.close()
    
    def publish_status_change(self, project: dict, new_status: str, reason: str):
        """Publish status change to Redis for Telegram notification."""
        channel = CHANNEL_REMOVED if new_status == 'removed' else CHANNEL_REACTIVATED
        
        message = {
            'twitter_handle': project.get('twitter_handle'),
            'project_name': project.get('project_name', ''),
            'project_chain': project.get('project_chain', ''),
            'old_status': project.get('monitoring_status'),
            'new_status': new_status,
            'reason': reason,
            'inactive_days': project.get('inactive_days', 0),
            'timestamp': datetime.now().isoformat()
        }
        
        self.redis.publish(channel, json.dumps(message))
        self.log(f"[PUBLISH] {channel} | @{project.get('twitter_handle')}")
    
    def check_project(self, project: dict) -> dict:
        """Check a single abandoned project."""
        handle = project.get('twitter_handle', '')
        project_id = project.get('id')
        
        self.log(f"[CHECK] @{handle}")
        
        # Get latest tweet info
        tweet_info = self.check_latest_tweet(handle)
        
        if 'error' in tweet_info:
            return {'status': 'error', 'error': tweet_info['error']}
        
        # Calculate days inactive
        if tweet_info.get('has_tweets'):
            days_inactive = self.calculate_days_inactive(tweet_info.get('latest_at'))
        else:
            # No tweets found, use stored value or default high
            days_inactive = project.get('inactive_days', 999)
        
        self.log(f"[INACTIVE] @{handle} | {days_inactive} days")
        
        result = {
            'twitter_handle': handle,
            'days_inactive': days_inactive,
            'action': None
        }
        
        if days_inactive >= DAYS_TO_REMOVE:
            # 30+ days without posting → remove from monitoring
            self.update_project_status(project_id, 'removed', {
                'inactive_days': days_inactive
            })
            self.publish_status_change(project, 'removed', f'{days_inactive} days without posting')
            result['action'] = 'removed'
            self.log(f"[REMOVED] @{handle} | {days_inactive} days inactive")
            
        elif days_inactive < 30 and tweet_info.get('has_tweets'):
            # Posted recently → reactivate monitoring
            self.update_project_status(project_id, 'active', {
                'inactive_days': days_inactive,
                'last_tweet_at': tweet_info.get('latest_at')
            })
            self.publish_status_change(project, 'active', 'Posted recently, reactivated')
            result['action'] = 'reactivated'
            self.log(f"[REACTIVATED] @{handle} | posted {days_inactive} days ago")
            
        else:
            # Still abandoned but not 30 days yet
            self.update_project_status(project_id, 'abandoned', {
                'inactive_days': days_inactive
            })
            result['action'] = 'still_abandoned'
            self.log(f"[STILL_ABANDONED] @{handle} | {days_inactive} days")
        
        return result
    
    def run_check_cycle(self):
        """Run one check cycle for all abandoned projects."""
        self.log("=" * 60)
        self.log("Starting abandoned projects check")
        
        start_time = time.time()
        
        # Get abandoned projects
        projects = self.get_abandoned_projects()
        self.log(f"[FOUND] {len(projects)} abandoned projects")
        
        if not projects:
            self.log("[DONE] No abandoned projects to check")
            return
        
        results = {
            'checked': 0,
            'removed': 0,
            'reactivated': 0,
            'still_abandoned': 0,
            'errors': 0
        }
        
        for i, project in enumerate(projects, 1):
            self.log(f"\n[{i}/{len(projects)}]")
            
            try:
                result = self.check_project(project)
                results['checked'] += 1
                
                action = result.get('action')
                if action == 'removed':
                    results['removed'] += 1
                elif action == 'reactivated':
                    results['reactivated'] += 1
                elif action == 'still_abandoned':
                    results['still_abandoned'] += 1
                    
            except Exception as e:
                self.log(f"[ERROR] {str(e)[:50]}")
                results['errors'] += 1
            
            # Rate limiting
            time.sleep(2)
        
        elapsed = time.time() - start_time
        
        self.log("\n" + "=" * 60)
        self.log(f"[DONE] checked={results['checked']} | removed={results['removed']} | "
                 f"reactivated={results['reactivated']} | still_abandoned={results['still_abandoned']} | "
                 f"errors={results['errors']} | time={elapsed:.1f}s")
        self.log("=" * 60)
    
    def run(self):
        """Main loop: run check every N days."""
        self.log(f"Service started | interval={CHECK_INTERVAL_DAYS} days")
        self.log(f"Redis: {REDIS_URL}")
        self.log(f"Days to remove: {DAYS_TO_REMOVE}")
        
        interval_seconds = CHECK_INTERVAL_DAYS * 24 * 3600
        
        while True:
            try:
                # Run check cycle
                self.run_check_cycle()
                
                # Wait for next cycle
                next_run = datetime.now() + timedelta(days=CHECK_INTERVAL_DAYS)
                next_run_str = next_run.strftime('%Y-%m-%d %H:%M:%S')
                self.log(f"Next check at: {next_run_str}")
                
                time.sleep(interval_seconds)
                
            except KeyboardInterrupt:
                self.log("Shutting down...")
                break
            except Exception as e:
                self.log(f"[ERROR] {str(e)}")
                time.sleep(3600)  # Wait 1 hour on error before retry


if __name__ == "__main__":
    checker = AbandonedChecker()
    checker.run()

