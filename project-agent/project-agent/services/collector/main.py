# services/collector/main.py
"""
Stage 0: Tweet Collector Service
Runs every 3 hours, collects tweets from all batches.
Publishes EACH tweet collected to Telegram.
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

from tweets.batch_collector import BatchCollector
from tweets.database import init_db, get_tweet_count, get_all_tweets

# Configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
COLLECTION_INTERVAL_HOURS = int(os.environ.get('COLLECTION_INTERVAL_HOURS', 3))
MAX_PAGES_PER_BATCH = 5

# Redis channels
CHANNEL_TWEET_COLLECTED = 'tweets:collected'
CHANNEL_NEW_TWEETS = 'tweets:new'


class CollectorService:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL)
        self.collector = BatchCollector(verbose=True, max_pages=MAX_PAGES_PER_BATCH)
        init_db()
        self.tweets_before = set()
        
    def log(self, msg: str):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [COLLECTOR] {msg}", flush=True)
    
    def get_existing_tweet_ids(self) -> set:
        """Get all existing tweet IDs before collection."""
        tweets = get_all_tweets(limit=10000)
        return {t.get('id') for t in tweets if t.get('id')}
    
    def publish_tweet_collected(self, tweet: dict, batch_name: str):
        """Publish individual collected tweet to Redis for Telegram."""
        message = {
            # Tweet info
            "id": tweet.get('id'),
            "url": tweet.get('url'),
            "text": tweet.get('text', ''),
            "created_at": tweet.get('createdAt'),
            "lang": tweet.get('lang'),
            
            # Engagement
            "view_count": tweet.get('viewCount', 0),
            "like_count": tweet.get('likeCount', 0),
            "retweet_count": tweet.get('retweetCount', 0),
            "reply_count": tweet.get('replyCount', 0),
            "quote_count": tweet.get('quoteCount', 0),
            
            # Author info
            "author_id": (tweet.get('author') or {}).get('id', ''),
            "author_username": (tweet.get('author') or {}).get('userName', ''),
            "author_name": (tweet.get('author') or {}).get('name', ''),
            "author_followers": (tweet.get('author') or {}).get('followers', 0),
            "author_following": (tweet.get('author') or {}).get('following', 0),
            "author_description": (tweet.get('author') or {}).get('description', ''),
            "author_is_blue_verified": (tweet.get('author') or {}).get('isBlueVerified', False),
            "author_created_at": (tweet.get('author') or {}).get('createdAt', ''),
            "author_statuses_count": (tweet.get('author') or {}).get('statusesCount', 0),
            "author_media_count": (tweet.get('author') or {}).get('mediaCount', 0),
            
            # Batch info
            "batch_name": batch_name,
            "query_used": batch_name,
            
            # Discovery source tracking
            "discovery_source": "collector",
            "discovery_keyword": batch_name,
            
            "timestamp": datetime.now().isoformat()
        }
        
        self.redis.publish(CHANNEL_TWEET_COLLECTED, json.dumps(message))
        self.log(f"[PUBLISH] {CHANNEL_TWEET_COLLECTED} | @{(tweet.get('author') or {}).get('userName', '?')} | {tweet.get('id', '?')}")
    
    def publish_new_tweets(self, batch_name: str, new_count: int):
        """Publish notification of new tweets to Redis (for triage to start)."""
        if new_count > 0:
            message = {
                "batch": batch_name,
                "new_tweets": new_count,
                "timestamp": datetime.now().isoformat()
            }
            self.redis.publish(CHANNEL_NEW_TWEETS, json.dumps(message))
            self.log(f"[NOTIFY] {CHANNEL_NEW_TWEETS} | batch={batch_name} | new={new_count}")
    
    def run_collection_cycle(self):
        """Run one full collection cycle, publishing each new tweet."""
        self.log("=" * 60)
        self.log("Starting collection cycle")
        
        start_time = time.time()
        
        # Get existing tweet IDs before collection
        self.tweets_before = self.get_existing_tweet_ids()
        self.log(f"[DB] tweets_before={len(self.tweets_before)}")
        
        total_new = 0
        
        try:
            # Run all batches with callback for each tweet
            from tweets.keywords import KEYWORD_BATCHES
            from tweets.batch_collector import BatchCollector
            
            collector = BatchCollector(verbose=True, max_pages=MAX_PAGES_PER_BATCH)
            
            for batch_name, batch_config in KEYWORD_BATCHES.items():
                self.log(f"\n[BATCH] {batch_name}")
                
                batch_new = 0
                
                # Collect batch (keywords already loaded from KEYWORD_BATCHES inside collect_batch)
                result = collector.collect_batch(
                    batch_name,
                    max_pages=MAX_PAGES_PER_BATCH
                )
                
                # Get new tweets by comparing with before
                tweets_after = self.get_existing_tweet_ids()
                new_ids = tweets_after - self.tweets_before
                
                if new_ids:
                    # Fetch and publish each new tweet
                    all_tweets = get_all_tweets(limit=len(new_ids) + 100)
                    for tweet in all_tweets:
                        if tweet.get('id') in new_ids:
                            # Convert DB row to dict for publishing
                            tweet_data = {
                                'id': tweet.get('id'),
                                'url': tweet.get('url'),
                                'text': tweet.get('text'),
                                'createdAt': tweet.get('created_at'),
                                'lang': tweet.get('lang'),
                                'viewCount': tweet.get('view_count', 0),
                                'likeCount': tweet.get('like_count', 0),
                                'retweetCount': tweet.get('retweet_count', 0),
                                'replyCount': tweet.get('reply_count', 0),
                                'quoteCount': tweet.get('quote_count', 0),
                                'author': {
                                    'id': tweet.get('author_id'),
                                    'userName': tweet.get('author_username'),
                                    'name': tweet.get('author_name'),
                                    'followers': tweet.get('author_followers', 0),
                                    'following': tweet.get('author_following', 0),
                                    'description': tweet.get('author_description', ''),
                                    'isBlueVerified': tweet.get('author_is_blue_verified', False),
                                    'createdAt': tweet.get('author_created_at', ''),
                                    'statusesCount': tweet.get('author_statuses_count', 0),
                                    'mediaCount': tweet.get('author_media_count', 0)
                                }
                            }
                            self.publish_tweet_collected(tweet_data, batch_name)
                            batch_new += 1
                    
                    # Update tweets_before for next batch
                    self.tweets_before = tweets_after
                
                total_new += batch_new
                
                # Notify triage service
                if batch_new > 0:
                    self.publish_new_tweets(batch_name, batch_new)
                
                time.sleep(2)  # Delay between batches
            
            elapsed = time.time() - start_time
            
            self.log(f"\n{'='*60}")
            self.log(f"Collection complete | total_new={total_new} | time={elapsed:.1f}s")
            self.log(f"[DB] total_tweets={get_tweet_count()}")
            
        except Exception as e:
            self.log(f"[ERROR] Collection failed: {str(e)}")
        
        return total_new
    
    def run(self):
        """Main loop: run collection every N hours."""
        self.log(f"Service started | interval={COLLECTION_INTERVAL_HOURS}h")
        self.log(f"Redis: {REDIS_URL}")
        self.log(f"[DB] initial_tweets={get_tweet_count()}")
        
        interval_seconds = COLLECTION_INTERVAL_HOURS * 3600
        
        while True:
            try:
                # Run collection
                self.run_collection_cycle()
                
                # Wait for next cycle
                next_run = datetime.now().timestamp() + interval_seconds
                next_run_str = datetime.fromtimestamp(next_run).strftime('%Y-%m-%d %H:%M:%S')
                self.log(f"Next collection at: {next_run_str}")
                
                time.sleep(interval_seconds)
                
            except KeyboardInterrupt:
                self.log("Shutting down...")
                break
            except Exception as e:
                self.log(f"[ERROR] {str(e)}")
                time.sleep(60)  # Wait 1 min on error before retry


if __name__ == "__main__":
    service = CollectorService()
    service.run()
