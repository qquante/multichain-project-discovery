"""
Alpha Hunter Service
Fetches tweets from known alpha callers and saves to tweets.db for triage processing.
"""

import os
import sys
import json
import asyncio
import redis.asyncio as redis
from datetime import datetime, timedelta
import httpx

# Add parent to path for imports
sys.path.insert(0, '/app')

# Import database functions
from tweets.database import init_db, save_tweet, tweet_exists

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6388')
TWITTER_API_KEY = os.getenv('TWITTER_API_KEY', '')
HUNT_INTERVAL_HOURS = int(os.getenv('HUNT_INTERVAL_HOURS', '12'))
TWEETS_PER_CALLER = int(os.getenv('TWEETS_PER_CALLER', '20'))

# Alpha callers - accounts that frequently tag new projects
ALPHA_CALLERS = os.getenv('ALPHA_CALLERS', 'AresLabs_xyz').split(',')

# Twitter API base URL
BASE_URL = "https://api.twitterapi.io"


def log(msg: str):
    """Log with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [ALPHA] {msg}", flush=True)


async def search_tweets(api_key: str, query: str, max_results: int = 20) -> list:
    """Search tweets using Twitter API."""
    url = f"{BASE_URL}/twitter/tweet/advanced_search"
    headers = {"X-API-Key": api_key}
    params = {"query": query, "queryType": "Latest"}
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            tweets = data.get("tweets", [])
            return tweets[:max_results]
        except Exception as e:
            log(f"API error: {e}")
            return []


async def get_user_tweets(api_key: str, username: str, count: int = 20) -> list:
    """Fetch recent tweets from a user."""
    try:
        # Use search to get tweets from user
        query = f"from:{username} -filter:replies -filter:retweets"
        
        # Add since filter (last 48 hours)
        since_date = (datetime.now() - timedelta(hours=48)).strftime('%Y-%m-%d')
        query += f" since:{since_date}"
        
        tweets = await search_tweets(api_key, query, count)
        return tweets
    except Exception as e:
        log(f"Error fetching tweets from @{username}: {e}")
        return []


def save_tweet_to_db(tweet: dict, source: str) -> bool:
    """
    Save tweet to tweets.db database.
    This is the CRITICAL fix - tweets must be in DB for Triage to process them.
    """
    try:
        tweet_id = tweet.get('id', '')
        
        # Check if already exists
        if tweet_exists(tweet_id):
            return False
        
        # Save to database using the existing function
        saved = save_tweet(tweet, query_used=f"alpha_hunter:{source}")
        
        if saved:
            author = tweet.get('author', {})
            log(f"Saved tweet {tweet_id} from @{author.get('userName', 'unknown')}")
        
        return saved
        
    except Exception as e:
        log(f"Error saving tweet to DB: {e}")
        return False


async def notify_triage(redis_client, source: str, new_count: int):
    """Notify triage service that new tweets are available."""
    try:
        message = {
            'batch': f'alpha_hunter:{source}',
            'new_tweets': new_count,
            'timestamp': datetime.now().isoformat()
        }
        await redis_client.publish('tweets:collected', json.dumps(message))
        log(f"Notified triage: {new_count} new tweets from {source}")
    except Exception as e:
        log(f"Error notifying triage: {e}")


async def hunt_alpha():
    """Main alpha hunting function."""
    log("=" * 60)
    log(f"Starting hunt at {datetime.now().isoformat()}")
    log(f"Callers: {ALPHA_CALLERS}")
    log(f"Tweets per caller: {TWEETS_PER_CALLER}")
    log("=" * 60)
    
    # Initialize database
    init_db()
    
    # Connect to Redis
    redis_client = await redis.from_url(REDIS_URL)
    
    total_found = 0
    total_saved = 0
    
    for caller in ALPHA_CALLERS:
        caller = caller.strip()
        if not caller:
            continue
            
        log(f"Fetching tweets from @{caller}...")
        
        tweets = await get_user_tweets(TWITTER_API_KEY, caller, TWEETS_PER_CALLER)
        
        if not tweets:
            log(f"No tweets found from @{caller}")
            continue
        
        log(f"Found {len(tweets)} tweets from @{caller}")
        total_found += len(tweets)
        
        caller_saved = 0
        
        for tweet in tweets:
            # Check if tweet has mentions (potential project tags) or urls
            entities = tweet.get('entities', {})
            mentions = entities.get('user_mentions', []) or entities.get('mentions', [])
            urls = entities.get('urls', [])
            
            # Only save tweets with mentions or urls (likely about projects)
            if mentions or urls:
                saved = save_tweet_to_db(tweet, caller)
                if saved:
                    caller_saved += 1
                    total_saved += 1
                    
                    # Log what was found
                    if mentions:
                        mentioned_handles = [
                            m.get('screen_name', '') or m.get('username', '') 
                            for m in mentions
                        ]
                        log(f"  -> Mentions: @{', @'.join(mentioned_handles)}")
        
        # Notify triage if we saved any tweets
        if caller_saved > 0:
            await notify_triage(redis_client, caller, caller_saved)
        
        log(f"Saved {caller_saved} tweets from @{caller}")
    
    log("=" * 60)
    log("Hunt complete!")
    log(f"Total tweets found: {total_found}")
    log(f"Total tweets saved: {total_saved}")
    log(f"Next hunt in {HUNT_INTERVAL_HOURS} hours")
    log("=" * 60)
    
    await redis_client.aclose()


async def main():
    """Main loop - runs hunt every HUNT_INTERVAL_HOURS."""
    log("Service starting...")
    log(f"Hunt interval: {HUNT_INTERVAL_HOURS} hours")
    log(f"Configured callers: {ALPHA_CALLERS}")
    
    while True:
        try:
            await hunt_alpha()
        except Exception as e:
            log(f"Error during hunt: {e}")
            import traceback
            traceback.print_exc()
        
        # Wait for next hunt
        wait_seconds = HUNT_INTERVAL_HOURS * 3600
        log(f"Sleeping for {HUNT_INTERVAL_HOURS} hours...")
        await asyncio.sleep(wait_seconds)


if __name__ == "__main__":
    asyncio.run(main())
