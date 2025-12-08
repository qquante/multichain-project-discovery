# services/monitor/main.py
"""
Stage 3: Monitor Service
Runs continuously, monitors ALL confirmed projects based on their priority.
Publishes EACH project update + fingerprint to Telegram.
"""

import os
import sys
import time
import json
import redis
from datetime import datetime

# Add shared modules to path
sys.path.insert(0, '/app/shared')
sys.path.insert(0, '/app')

from agent.monitor import ProjectMonitor
from agent.database import (
    init_db, 
    get_projects_to_monitor, 
    get_monitoring_stats,
    activate_monitoring_for_confirmed,
    get_fingerprints,
    MONITOR_INTERVALS,
    update_calendar_status,
    save_to_calendar
)

# Configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
CHECK_INTERVAL = 60  # Check for projects to monitor every 60 seconds
BATCH_SIZE = 999999  # Process ALL - no limit

# Redis channels
CHANNEL_CONFIRMED = 'projects:confirmed'
CHANNEL_MONITORED = 'projects:monitored'
CHANNEL_ALERT = 'projects:alert'
CHANNEL_LAUNCHED = 'projects:launched'
CHANNEL_ABANDONED = 'projects:abandoned'
CHANNEL_FINGERPRINT = 'fingerprint:new'
CHANNEL_DELETE = 'monitor:delete'


class MonitorService:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL)
        self.pubsub = self.redis.pubsub()
        self.monitor = ProjectMonitor(verbose=True)
        init_db()
        
    def log(self, msg: str):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [MONITOR] {msg}", flush=True)
    
    def _get_chain_group(self, chain: str) -> str:
        """Map chain to group key for telegram-chains (8 groups)."""
        chain_lower = (chain or 'unknown').lower()
        
        megaeth_chains = ['megaeth', 'abstract', 'movement']
        if chain_lower in ['sol', 'solana']:
            return 'solana'
        elif chain_lower in ['base']:
            return 'base'
        elif chain_lower in ['eth', 'ethereum']:
            return 'ethereum'
        elif chain_lower in ['bsc', 'bnb', 'binance']:
            return 'bsc'
        elif chain_lower in ['monad']:
            return 'monad'
        elif chain_lower in megaeth_chains:
            return 'megaeth'
        elif chain_lower in ['unknown', '']:
            return 'unknown'
        else:
            return 'other'
    
    def publish_project_update(self, result: dict, project: dict, update_type: str):
        """Publish project update to Redis for Telegram alerts."""
        
        if update_type == 'launched':
            channel = CHANNEL_LAUNCHED
        elif update_type == 'abandoned':
            channel = CHANNEL_ABANDONED
        elif update_type in ['alert', 'imminent']:
            channel = CHANNEL_ALERT
        else:
            channel = CHANNEL_MONITORED
        
        message = {
            # Basic info
            "twitter_handle": result.get('twitter_handle', ''),
            "project_name": project.get('project_name'),
            "project_chain": project.get('project_chain'),
            "update_type": update_type,
            
            # Status
            "status": result.get('status'),
            "status_before": project.get('monitoring_status'),
            "status_after": result.get('status'),
            "priority": result.get('priority'),
            "priority_before": project.get('priority'),
            "priority_after": result.get('priority'),
            "monitoring_status": result.get('status'),
            "launch_urgency": result.get('launch_urgency', 'unknown'),
            "launch_date_mentioned": result.get('launch_date'),
            "estimated_hours_until_launch": result.get('hours_until_launch'),
            
            # CA detection
            "ca_detected": result.get('ca_found', False),
            "ca_mentioned": result.get('ca_found', False),
            "ca_address": result.get('ca_address'),
            "ca_source": result.get('ca_source'),
            
            # Changes
            "changes_detected": result.get('changes', []),
            "changes": result.get('changes', []),
            "summary": result.get('summary', ''),
            
            # Followers
            "followers_current": project.get('followers_current', 0),
            "followers": project.get('followers_current', 0),
            "followers_change": result.get('followers_change', 0),
            "followers_growth": result.get('followers_growth', 0),
            
            # Activity
            "activity_level": result.get('activity_level', 'unknown'),
            "inactive_days": result.get('inactive_days', 0),
            "new_tweets_count": result.get('new_tweets_count', 0),
            "last_tweet_at": result.get('last_tweet_at'),
            "last_tweet_text": result.get('last_tweet_text'),
            
            # Bio/Pinned
            "bio_changed": result.get('bio_changed', False),
            "bio_new": result.get('bio_new'),
            "pinned_changed": result.get('pinned_changed', False),
            "pinned_new": result.get('pinned_new'),
            
            # Site
            "site_accessible": result.get('site_accessible', False),
            "site_changed": result.get('site_changed', False),
            "site_ca_found": result.get('site_ca_found', False),
            
            # AI Analysis
            "ai_analysis": result.get('summary', ''),
            
            # Activity
            "activity_level": result.get('activity_level', 'unknown'),
            "followers_growth": result.get('followers_growth', 0),
            
            # AlphaGate enrichment data (ALL fields)
            "found_in_alphagate": result.get('found_in_alphagate', False),
            "key_followers": result.get('key_followers', []),
            "key_followers_count": result.get('key_followers_count', 0),
            "alpha_hunters": result.get('alpha_hunters', []),
            "alpha_hunters_count": result.get('alpha_hunters_count', 0),
            "followers_when_found": result.get('followers_when_found', 0),
            "best_hunter_winrate": result.get('best_hunter_winrate', 0.0),
            "alphagate_bio_changes": result.get('alphagate_bio_changes', 0),
            "alphagate_username_changes": result.get('alphagate_username_changes', 0),
            "alphagate_alerts": result.get('alphagate_alerts', []),
            
            "timestamp": datetime.now().isoformat()
        }
        
        json_msg = json.dumps(message)
        self.redis.publish(channel, json_msg)
        self.log(f"[PUBLISH] {channel} | @{result.get('twitter_handle', '')} | type={update_type}")
        
        # Publish to chain-specific channel for telegram-chains service
        chain = (project.get('project_chain') or 'unknown').lower()
        chain_channel = f"projects:monitored:{self._get_chain_group(chain)}"
        self.redis.publish(chain_channel, json_msg)
        self.log(f"[PUBLISH] {chain_channel}")
    
    def publish_fingerprint(self, twitter_handle: str):
        """Publish latest fingerprint for this project to Redis."""
        fingerprints = get_fingerprints(twitter_handle=twitter_handle, stage=3, limit=1)
        
        if fingerprints:
            fp = fingerprints[0]
            self.redis.publish(CHANNEL_FINGERPRINT, json.dumps(fp))
            self.log(f"[PUBLISH] {CHANNEL_FINGERPRINT} | @{twitter_handle} | decision={fp.get('decision')}")
    
    def process_monitoring_queue(self):
        """Process ALL projects that are due for monitoring."""
        projects = get_projects_to_monitor(limit=BATCH_SIZE)
        
        if not projects:
            return 0
        
        self.log(f"Processing {len(projects)} projects for monitoring...")
        
        start_time = time.time()
        processed = 0
        
        for i, project in enumerate(projects, 1):
            try:
                handle = project.get('twitter_handle', 'unknown')
                priority = project.get('priority', 'medium')
                
                self.log(f"[{i}/{len(projects)}] Monitoring @{handle} (priority={priority})...")
                
                result = self.monitor.monitor_project(project)
                processed += 1
                
                if result:
                    new_status = result.get('status')
                    old_status = project.get('monitoring_status')
                    urgency = result.get('launch_urgency', 'unknown')
                    new_priority = result.get('priority', 'low')
                    
                    # Determine update type and publish
                    # CRITICAL: Check CA first - if CA detected, SILENTLY remove (no alert!)
                    if result.get('ca_found'):
                        # CA detected - project already launched
                        # SILENTLY update calendar and remove from monitoring - NO TELEGRAM ALERT!
                        update_calendar_status(handle, 'launched', result.get('ca_address'))
                        self.log(f"[CA_DETECTED] @{handle} - CA: {result.get('ca_address', '')[:20]}... - SILENTLY removed")
                    elif new_status == 'launched' and not result.get('ca_found'):
                        # Launched WITHOUT CA detection (e.g., announcement only)
                        # This case should be rare - usually launched = CA found
                        self.publish_project_update(result, project, 'launched')
                        update_calendar_status(handle, 'launched', result.get('ca_address'))
                        self.log(f"[CALENDAR] @{handle} marked as launched (no CA)")
                    elif new_status == 'abandoned':
                        self.publish_project_update(result, project, 'abandoned')
                        update_calendar_status(handle, 'cancelled')
                        self.log(f"[CALENDAR] @{handle} marked as cancelled")
                    elif urgency in ['imminent', 'soon'] or new_priority in ['critical', 'high']:
                        self.publish_project_update(result, project, 'alert')
                        save_to_calendar({
                            'twitter_handle': handle,
                            'launch_urgency': urgency,
                            'launch_date': result.get('launch_date'),
                            'chain': project.get('project_chain')
                        })
                    else:
                        # Only publish monitored update if:
                        # 1. NOT the first monitoring (monitor_count > 0)
                        # 2. Has impactful changes (not routine check)
                        monitor_count = project.get('monitor_count', 0) or 0
                        changes = result.get('changes', [])
                        
                        is_first_monitor = monitor_count == 0
                        has_changes = len(changes) > 0 and changes != ['routine check']
                        
                        if is_first_monitor:
                            self.log(f"[SKIP] @{handle} - first monitoring, no alert")
                        elif not has_changes:
                            self.log(f"[SKIP] @{handle} - no impactful changes")
                        else:
                            # Has impactful changes after first monitor
                            self.publish_project_update(result, project, 'monitored')
                    
                    # Always publish fingerprint
                    self.publish_fingerprint(handle)
                
                time.sleep(2)  # Delay between monitoring checks
                
            except Exception as e:
                self.log(f"[ERROR] Monitoring failed for @{handle}: {str(e)}")
                continue
        
        elapsed = time.time() - start_time
        self.log(f"Batch complete | processed={processed} | time={elapsed:.1f}s")
        
        return processed
    
    def handle_confirmed_notification(self, message):
        """Handle notification of newly confirmed project."""
        try:
            data = json.loads(message['data'])
            handle = data.get('twitter_handle', 'unknown')
            project_id = data.get('project_id')
            
            self.log(f"[NOTIFICATION] New confirmed project: @{handle} (id={project_id})")
            
            # Activate monitoring for confirmed projects
            activate_monitoring_for_confirmed()
            
        except Exception as e:
            self.log(f"[ERROR] Failed to handle notification: {str(e)}")
    
    def handle_delete_request(self, message):
        """Handle request to delete project from monitoring."""
        try:
            data = json.loads(message['data'])
            handle = data.get('twitter_handle', '')
            requested_by = data.get('requested_by', 'unknown')
            
            self.log(f"[DELETE] @{handle} requested by @{requested_by}")
            
            # Update project status to removed
            from agent.database import get_connection
            conn = get_connection()
            cur = conn.cursor()
            
            cur.execute('''
                UPDATE verified_projects 
                SET monitoring_status = 'removed',
                    updated_at = ?
                WHERE LOWER(twitter_handle) = LOWER(?)
            ''', (datetime.now().isoformat(), handle.lstrip('@')))
            
            rows_affected = cur.rowcount
            conn.commit()
            conn.close()
            
            if rows_affected > 0:
                self.log(f"[DELETED] @{handle} removed from monitoring")
                # Notify via Redis
                self.redis.publish(CHANNEL_ABANDONED, json.dumps({
                    'twitter_handle': handle,
                    'project_name': '',
                    'project_chain': '',
                    'inactive_days': 0,
                    'ai_analysis': f'Removed from monitoring by @{requested_by}',
                    'summary': f'Manually removed by @{requested_by}',
                    'timestamp': datetime.now().isoformat()
                }))
            else:
                self.log(f"[NOT_FOUND] @{handle} not found in monitoring")
            
        except Exception as e:
            self.log(f"[ERROR] Failed to handle delete request: {str(e)}")
    
    def run(self):
        """Main loop: monitor projects continuously based on priority."""
        self.log("Service started")
        self.log(f"Redis: {REDIS_URL}")
        self.log(f"Batch size: UNLIMITED (processing all)")
        self.log(f"Monitor intervals: {MONITOR_INTERVALS}")
        
        # Show initial stats
        stats = get_monitoring_stats()
        self.log(f"[STATS] by_status={stats.get('by_monitoring_status', {})} | checks={stats.get('total_monitoring_checks', 0)}")
        
        # Activate monitoring for any confirmed projects
        activate_monitoring_for_confirmed()
        
        # Subscribe to channels
        self.pubsub.subscribe(CHANNEL_CONFIRMED, CHANNEL_DELETE)
        self.log(f"Subscribed to: {CHANNEL_CONFIRMED}, {CHANNEL_DELETE}")
        
        last_check = 0
        
        while True:
            try:
                # Check for Redis messages (non-blocking)
                message = self.pubsub.get_message(timeout=1.0)
                
                if message and message['type'] == 'message':
                    channel = message['channel']
                    if isinstance(channel, bytes):
                        channel = channel.decode('utf-8')
                    
                    if channel == CHANNEL_DELETE:
                        self.handle_delete_request(message)
                    else:
                        self.handle_confirmed_notification(message)
                
                # Check for projects to monitor periodically
                if time.time() - last_check > CHECK_INTERVAL:
                    projects_due = get_projects_to_monitor(limit=1)
                    if projects_due:
                        self.process_monitoring_queue()
                    else:
                        self.log("[IDLE] No projects due for monitoring")
                    last_check = time.time()
                
                time.sleep(0.1)  # Small sleep to prevent CPU spinning
                
            except KeyboardInterrupt:
                self.log("Shutting down...")
                self.pubsub.close()
                break
            except Exception as e:
                self.log(f"[ERROR] {str(e)}")
                time.sleep(5)  # Wait before retry


if __name__ == "__main__":
    service = MonitorService()
    service.run()
