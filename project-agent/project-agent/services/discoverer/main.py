# services/discoverer/main.py
"""
Project Discoverer Service
Runs periodically to investigate handles mentioned by influencers.
Publishes discovered projects to Redis for Telegram notification.
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

from agent.discoverer import ProjectDiscoverer
from agent.database import init_db, get_mention_stats, get_handles_to_investigate

# Configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6388')
DISCOVERY_INTERVAL = int(os.environ.get('DISCOVERY_INTERVAL', 1800))  # 30 min default
MIN_MENTIONS = int(os.environ.get('MIN_MENTIONS', 1))  # Minimum mentions to investigate
BATCH_LIMIT = int(os.environ.get('BATCH_LIMIT', 20))  # Max handles per cycle

# Redis channels
CHANNEL_DISCOVERY_COMPLETE = 'discovery:complete'
CHANNEL_FINGERPRINT = 'fingerprint:new'


class DiscovererService:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL)
        self.discoverer = ProjectDiscoverer(verbose=True)
        init_db()
        
    def log(self, msg: str):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [DISCOVERER] {msg}", flush=True)
    
    def publish_discovery(self, result: dict):
        """Publish discovery result to Redis for Telegram."""
        message = {
            "handle": result.get('handle'),
            "twitter_handle": result.get('handle'),
            "status": result.get('status'),
            "discovery_status": result.get('status'),
            "confidence": result.get('confidence', 0),
            "project_name": result.get('project_name'),
            "project_chain": result.get('project_chain'),
            "reasoning": result.get('reasoning', ''),
            "timestamp": datetime.now().isoformat()
        }
        
        self.redis.publish(CHANNEL_DISCOVERY_COMPLETE, json.dumps(message))
        self.log(f"[PUBLISH] {CHANNEL_DISCOVERY_COMPLETE} | @{result.get('handle')} | status={result.get('status')}")
    
    def run_discovery_cycle(self):
        """Run one discovery cycle."""
        self.log("=" * 60)
        self.log("Starting discovery cycle")
        
        start_time = time.time()
        
        # Check if there are handles to investigate
        handles = get_handles_to_investigate(min_mentions=MIN_MENTIONS, limit=1)
        if not handles:
            self.log("[IDLE] No handles to investigate")
            return
        
        # Run discovery
        results = self.discoverer.run_discovery_cycle(
            min_mentions=MIN_MENTIONS,
            limit=BATCH_LIMIT
        )
        
        elapsed = time.time() - start_time
        
        self.log(f"Cycle complete | investigated={results.get('investigated', 0)} | "
                 f"confirmed={results.get('confirmed', 0)} | rejected={results.get('rejected', 0)} | "
                 f"time={elapsed:.1f}s")
        
        # Show stats
        stats = get_mention_stats()
        self.log(f"[STATS] pending={stats.get('pending_investigation', 0)} | "
                 f"converted={stats.get('converted_to_projects', 0)} | "
                 f"unique_handles={stats.get('unique_handles_mentioned', 0)}")
    
    def run(self):
        """Main loop: run discovery periodically."""
        self.log(f"Service started | interval={DISCOVERY_INTERVAL}s ({DISCOVERY_INTERVAL/60:.0f}min)")
        self.log(f"Redis: {REDIS_URL}")
        self.log(f"Min mentions: {MIN_MENTIONS} | Batch limit: {BATCH_LIMIT}")
        
        # Show initial stats
        stats = get_mention_stats()
        self.log(f"[STATS] total_mentions={stats.get('total_mentions', 0)} | "
                 f"pending={stats.get('pending_investigation', 0)}")
        
        while True:
            try:
                # Run discovery cycle
                self.run_discovery_cycle()
                
                # Wait for next cycle
                next_run = datetime.now().timestamp() + DISCOVERY_INTERVAL
                next_run_str = datetime.fromtimestamp(next_run).strftime('%Y-%m-%d %H:%M:%S')
                self.log(f"Next discovery at: {next_run_str}")
                
                time.sleep(DISCOVERY_INTERVAL)
                
            except KeyboardInterrupt:
                self.log("Shutting down...")
                break
            except Exception as e:
                self.log(f"[ERROR] {str(e)}")
                time.sleep(60)  # Wait 1 min on error


if __name__ == "__main__":
    service = DiscovererService()
    service.run()

