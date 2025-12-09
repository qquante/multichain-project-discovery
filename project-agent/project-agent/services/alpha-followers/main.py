"""
Service: alpha-followers
Fetches recent followings (pageSize=20) from a list of seed profiles every 12h,
deduplicates, and inserts new handles into triaged pipeline with discovery_source=alpha_followers.
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

from users.api_client import UserFollowingsClient
from users.database import (
    init_db,
    was_following_seen,
    mark_following_seen,
)
from agent.database import (
    save_triage_result,
    is_handle_triaged,
    is_handle_verified,
)

# Configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6388')
TWITTER_API_KEY = os.environ.get('TWITTER_API_KEY', '')
POLL_INTERVAL_HOURS = float(os.environ.get('ALPHA_FOLLOWERS_INTERVAL_HOURS', 12))
PAGE_SIZE = 20  # fixed as requested

# Redis channel: notify triage service of new pending items (same pattern as collector)
CHANNEL_NEW_TWEETS = 'tweets:new'

# Seeds list (provided)
SEED_HANDLES = [
    "afrectz",
    "mrrose__",
    "Cleary_77",
    "mikedemarais",
    "poett",
    "Beautrj",
    "nunooeu",
    "0xleonidas__",
    "EduRio_",
    "snkmaskot",
    "0xMoco",
    "requisiem",
    "katekate666888",
    "0xSunNFT",
    "UniswapVillain",
    "cryptosaddi",
    "0xValmir",
]


class AlphaFollowersService:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL)
        self.client = UserFollowingsClient(api_key=TWITTER_API_KEY, verbose=True)
        init_db()
    
    def log(self, msg: str):
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{ts}] [ALPHA-FOLLOWERS] {msg}", flush=True)
    
    def _publish_new_count(self, count: int):
        """Notify triage loop that there are new items (uses existing channel)."""
        if count <= 0:
            return
        message = {
            "batch": "alpha_followers",
            "new_tweets": count,
            "timestamp": datetime.now().isoformat()
        }
        self.redis.publish(CHANNEL_NEW_TWEETS, json.dumps(message))
        self.log(f"[NOTIFY] {CHANNEL_NEW_TWEETS} | new={count}")
    
    def _insert_triage_stub(self, handle: str, author_id: str, seed: str, follower_count: int = 0, bio: str = "") -> bool:
        """Insert a minimal triage record to be picked by verifier later."""
        triage_result = {
            "project": {},
            "launch": {},
            "signals": {},
            "mentions": {},
            "source": {
                "twitter_handle": f"@{handle}",
                "tweet_id": None,
                "tweet_date": None,
                "tweet_text_preview": f"Found via alpha followers @{seed}",
                "discovery_source": "alpha_followers",
                "discovery_keyword": f"@{seed}",
            }
        }
        # Save triage result only if not already triaged/verified
        if is_handle_triaged(handle) or is_handle_verified(handle):
            return False
        saved = save_triage_result(triage_result)
        return saved
    
    def process_seed(self, seed: str) -> int:
        """Process one seed, return number of new followings saved."""
        seed_norm = seed.lstrip('@')
        self.log(f"[SEED] @{seed_norm} | fetching followings...")
        
        try:
            resp = self.client.get_user_followings(user_name=seed_norm, page_size=PAGE_SIZE)
        except Exception as e:
            self.log(f"[ERROR] @{seed_norm} API error: {str(e)[:100]}")
            return 0
        
        followings = resp.get("followings", []) or []
        new_count = 0
        
        for f in followings:
            username = f.get("userName") or f.get("username") or ""
            user_id = f.get("id") or ""
            followers = f.get("followers", 0)
            bio = f.get("description", "") or ""
            
            if not username or not user_id:
                continue
            
            if was_following_seen(seed_norm, user_id):
                continue
            
            # Dedup by triage/verified as well
            if is_handle_triaged(username) or is_handle_verified(username):
                mark_following_seen(seed_norm, user_id, username)
                continue
            
            saved = self._insert_triage_stub(username, user_id, seed_norm, followers, bio)
            if saved:
                mark_following_seen(seed_norm, user_id, username)
                new_count += 1
        
        if new_count > 0:
            self.log(f"[NEW] @{seed_norm} -> {new_count} new followings added to triage")
        else:
            self.log(f"[NONE] @{seed_norm} -> no new followings")
        
        return new_count
    
    def run_cycle(self):
        total_new = 0
        for seed in SEED_HANDLES:
            total_new += self.process_seed(seed)
        self._publish_new_count(total_new)
        return total_new
    
    def run(self):
        interval_seconds = POLL_INTERVAL_HOURS * 3600
        self.log(f"Service started | interval={POLL_INTERVAL_HOURS}h | pageSize={PAGE_SIZE}")
        while True:
            try:
                self.run_cycle()
                next_run = datetime.now() + timedelta(seconds=interval_seconds)
                self.log(f"Next run at: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
                time.sleep(interval_seconds)
            except KeyboardInterrupt:
                self.log("Shutting down...")
                break
            except Exception as e:
                self.log(f"[ERROR] {str(e)[:200]}")
                time.sleep(60)


if __name__ == "__main__":
    service = AlphaFollowersService()
    service.run()

