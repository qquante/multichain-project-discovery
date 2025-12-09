# services/triage/main.py
"""
Stage 1: Triage Service
Runs continuously, processes ALL pending tweets with LLM.
Publishes EACH result (triaged OR rejected) to Telegram.
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

from agent.analyzer import TweetAnalyzer
from agent.database import init_db, get_pending_tweets, get_triage_stats, get_fingerprints

# Configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6388')
BATCH_SIZE = 999999  # Process ALL tweets - no limit
POLL_INTERVAL = 10  # Check for new tweets every 10 seconds
DELAY_BETWEEN_TWEETS = 1.0  # Delay between LLM calls

# Redis channels
CHANNEL_NEW_TWEETS = 'tweets:new'
CHANNEL_TRIAGED = 'projects:triaged'
CHANNEL_REJECTED = 'triage:rejected'
CHANNEL_MENTION = 'mentions:new'
CHANNEL_FINGERPRINT = 'fingerprint:new'


class TriageService:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL)
        self.pubsub = self.redis.pubsub()
        self.analyzer = TweetAnalyzer(verbose=True)
        init_db()
        
    def log(self, msg: str):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [TRIAGE] {msg}", flush=True)
    
    def publish_triaged_project(self, result: dict, tweet: dict):
        """Publish triaged project to Redis for verification and Telegram."""
        project = result.get('project', {}) or {}
        source = result.get('source', {}) or {}
        signals = result.get('signals', {}) or {}
        launch = result.get('launch', {}) or {}
        mentions = result.get('mentions', {}) or {}
        
        message = {
            # Project info
            "twitter_handle": source.get('twitter_handle', ''),
            "project_name": project.get('name'),
            "project_ticker": project.get('ticker'),
            "project_type": project.get('type'),
            "project_chain": project.get('chain'),
            "confidence": result.get('confidence', 0),
            
            # Author info from tweet
            "author_id": tweet.get('author_id'),
            "author_followers": tweet.get('author_followers', 0),
            
            # Launch info
            "launch_status": launch.get('status'),
            "launch_date": launch.get('date'),
            "launch_time": launch.get('time'),
            "launch_platform": launch.get('platform'),
            
            # Signals
            "has_ca": project.get('has_ca', False),
            "ca_address": project.get('ca_address'),
            "keywords_found": signals.get('keywords_found', []),
            "has_telegram": signals.get('has_telegram', False),
            "telegram_link": signals.get('telegram_link'),
            "has_website": signals.get('has_website', False),
            "website_link": signals.get('website_link'),
            "has_discord": signals.get('has_discord', False),
            "links": signals.get('links', []),
            
            # Mentions
            "tagged_accounts": mentions.get('tagged_accounts', []),
            "tagged_chains": mentions.get('tagged_chains', []),
            "tagged_platforms": mentions.get('tagged_platforms', []),
            
            # Source tweet
            "source_tweet_id": source.get('tweet_id'),
            "tweet_id": source.get('tweet_id'),
            "tweet_date": source.get('tweet_date'),
            "tweet_text_preview": source.get('tweet_text_preview'),
            
            # Discovery source tracking
            "discovery_source": tweet.get('discovery_source', 'collector'),
            "discovery_keyword": tweet.get('discovery_keyword') or tweet.get('batch_name'),
            
            "timestamp": datetime.now().isoformat()
        }
        
        self.redis.publish(CHANNEL_TRIAGED, json.dumps(message))
        self.log(f"[PUBLISH] {CHANNEL_TRIAGED} | @{source.get('twitter_handle', '')}")
    
    def publish_rejected(self, result: dict, tweet: dict):
        """Publish rejected tweet to Redis for Telegram."""
        message = {
            "twitter_handle": f"@{tweet.get('author_username', '')}",
            "tweet_id": tweet.get('id'),
            "confidence": result.get('confidence', 0),
            "rejection_reason": result.get('rejection_reason', ''),
            "input_tweet_text": tweet.get('text', '')[:500],
            "author_followers": tweet.get('author_followers', 0),
            "llm_reasoning": result.get('rejection_reason', ''),
            "key_factors": {
                "keywords_found": (result.get('signals') or {}).get('keywords_found', []),
                "has_links": (result.get('signals') or {}).get('has_links', False),
                "has_telegram": (result.get('signals') or {}).get('has_telegram', False),
                "has_website": (result.get('signals') or {}).get('has_website', False),
                "has_discord": (result.get('signals') or {}).get('has_discord', False)
            },
            "timestamp": datetime.now().isoformat()
        }
        
        self.redis.publish(CHANNEL_REJECTED, json.dumps(message))
        self.log(f"[PUBLISH] {CHANNEL_REJECTED} | @{tweet.get('author_username', '')}")
    
    def publish_mention(self, result: dict, tweet: dict):
        """Publish mention to Redis for Telegram."""
        mentioned_projects = result.get('mentioned_projects', [])
        author_analysis = result.get('author_analysis', {}) or {}
        project_data = result.get('project', {}) or {}
        launch_data = result.get('launch', {}) or {}
        
        for mentioned in mentioned_projects:
            message = {
                "source_tweet_id": tweet.get('id'),
                "source_author_handle": tweet.get('author_username', ''),
                "source_author_id": tweet.get('author_id'),
                "source_author_followers": tweet.get('author_followers', 0),
                "source_tweet_text": tweet.get('text', '')[:500],
                "mentioned_handle": mentioned.get('handle', '').lstrip('@'),
                "project_name_extracted": mentioned.get('name_from_tweet') or project_data.get('name'),
                "project_ticker_extracted": mentioned.get('ticker_from_tweet') or project_data.get('ticker'),
                "project_chain_extracted": mentioned.get('chain_mentioned') or project_data.get('chain'),
                "name_possibilities": project_data.get('name_possibilities', []),
                "ticker_possibilities": project_data.get('ticker_possibilities', []),
                "launch_date_mentioned": launch_data.get('date'),
                "mention_type": author_analysis.get('author_type', 'influencer'),
                "confidence": mentioned.get('confidence', result.get('confidence', 0)),
                "timestamp": datetime.now().isoformat()
            }
            
            self.redis.publish(CHANNEL_MENTION, json.dumps(message))
            self.log(f"[PUBLISH] {CHANNEL_MENTION} | @{tweet.get('author_username', '')} mentioned @{mentioned.get('handle', '')}")
    
    def publish_fingerprint(self, tweet: dict):
        """Publish latest fingerprint for this tweet to Redis."""
        # Get the most recent fingerprint for this tweet
        fingerprints = get_fingerprints(twitter_handle=f"@{tweet.get('author_username', '')}", stage=1, limit=1)
        
        if fingerprints:
            fp = fingerprints[0]
            self.redis.publish(CHANNEL_FINGERPRINT, json.dumps(fp))
            self.log(f"[PUBLISH] {CHANNEL_FINGERPRINT} | @{tweet.get('author_username', '')} | decision={fp.get('decision')}")
    
    def process_pending_tweets(self):
        """Process ALL pending tweets."""
        pending = get_pending_tweets(limit=BATCH_SIZE)
        
        if not pending:
            return 0
        
        self.log(f"Processing {len(pending)} pending tweets...")
        
        start_time = time.time()
        processed = 0
        triaged = 0
        rejected = 0
        
        for i, tweet in enumerate(pending, 1):
            try:
                self.log(f"[{i}/{len(pending)}] Processing @{tweet.get('author_username', '')}...")
                
                result = self.analyzer.analyze_tweet(tweet)
                processed += 1
                
                if result:
                    is_project = result.get('is_project', False)
                    has_ca = (result.get('project') or {}).get('has_ca', False)
                    author_analysis = result.get('author_analysis') or {}
                    # CRITICAL: Default to False (conservative)
                    is_author_project = author_analysis.get('is_author_the_project')
                    if is_author_project is None:
                        is_author_project = False
                    mentioned_projects = result.get('mentioned_projects', [])
                    
                    if is_project and not has_ca:
                        if not is_author_project:
                            # Author is NOT the project
                            if mentioned_projects:
                                # Publish as mention
                                self.publish_mention(result, tweet)
                                self.log(f"[MENTION] @{tweet.get('author_username', '')} | mentioned {len(mentioned_projects)} projects")
                            else:
                                # No handles found - skip (don't publish as triaged)
                                self.log(f"[SKIP_NOT_PROJECT] @{tweet.get('author_username', '')} | not project, no handles found")
                        else:
                            # Author IS the project - publish as triaged
                            triaged += 1
                            self.publish_triaged_project(result, tweet)
                    else:
                        rejected += 1
                        # Publish rejected tweet
                        self.publish_rejected(result, tweet)
                    
                    # Always publish fingerprint
                    self.publish_fingerprint(tweet)
                
                time.sleep(DELAY_BETWEEN_TWEETS)
                
            except Exception as e:
                self.log(f"[ERROR] Tweet processing failed: {str(e)}")
                continue
        
        elapsed = time.time() - start_time
        self.log(f"Batch complete | processed={processed} | triaged={triaged} | rejected={rejected} | time={elapsed:.1f}s")
        
        return processed
    
    def handle_new_tweets_notification(self, message):
        """Handle notification of new tweets from collector."""
        try:
            data = json.loads(message['data'])
            batch = data.get('batch', 'unknown')
            new_count = data.get('new_tweets', 0)
            
            self.log(f"[NOTIFICATION] New tweets from batch={batch} | count={new_count}")
            
            # Process the new tweets
            self.process_pending_tweets()
            
        except Exception as e:
            self.log(f"[ERROR] Failed to handle notification: {str(e)}")
    
    def run(self):
        """Main loop: listen to Redis and process tweets continuously."""
        self.log("Service started")
        self.log(f"Redis: {REDIS_URL}")
        self.log(f"Batch size: UNLIMITED (processing all)")
        
        # Show initial stats
        stats = get_triage_stats()
        self.log(f"[STATS] processed={stats['total_processed']} | triaged={stats['total_triaged']}")
        
        # Subscribe to new tweets channel
        self.pubsub.subscribe(CHANNEL_NEW_TWEETS)
        self.log(f"Subscribed to: {CHANNEL_NEW_TWEETS}")
        
        # Process any existing pending tweets first
        self.process_pending_tweets()
        
        last_poll = time.time()
        
        while True:
            try:
                # Check for Redis messages (non-blocking)
                message = self.pubsub.get_message(timeout=1.0)
                
                if message and message['type'] == 'message':
                    self.handle_new_tweets_notification(message)
                
                # Also poll periodically in case we missed messages
                if time.time() - last_poll > POLL_INTERVAL:
                    pending = get_pending_tweets(limit=1)
                    if pending:
                        self.log(f"[POLL] Found pending tweets, processing...")
                        self.process_pending_tweets()
                    last_poll = time.time()
                
                time.sleep(0.1)  # Small sleep to prevent CPU spinning
                
            except KeyboardInterrupt:
                self.log("Shutting down...")
                self.pubsub.close()
                break
            except Exception as e:
                self.log(f"[ERROR] {str(e)}")
                time.sleep(5)  # Wait before retry


if __name__ == "__main__":
    service = TriageService()
    service.run()
