# tweets/batch_collector.py
"""
Batch collection for tweets using keyword batches.
Only fetches tweets from TODAY to avoid old garbage.
"""

import time
from datetime import datetime
from typing import Dict, Any, List, Optional


def parse_tweet_date(created_at: str) -> datetime:
    """Parse Twitter's createdAt format to datetime."""
    # Format: "Thu Dec 04 11:27:17 +0000 2025"
    try:
        return datetime.strptime(created_at, '%a %b %d %H:%M:%S %z %Y')
    except:
        return None


def is_tweet_from_today(created_at: str) -> bool:
    """Check if tweet is from today."""
    tweet_dt = parse_tweet_date(created_at)
    if tweet_dt:
        # Compare dates only (ignore time)
        return tweet_dt.date() == datetime.now().date()
    return True  # If we can't parse, assume it's OK

from .keywords import KEYWORD_BATCHES, build_query_for_batch, get_batch_names
from .api_client import TwitterSearchClient
from .database import (
    init_db,
    save_tweet,
    tweet_exists,
    save_batch_config,
    get_batch_config,
    update_batch_stats,
    save_collection_run,
    get_all_batch_configs,
    get_batch_stats
)

from config import MAX_PAGES


class BatchCollector:
    """Collect tweets using keyword batches."""
    
    def __init__(self, verbose: bool = True, max_pages: int = None):
        self.client = TwitterSearchClient(verbose=verbose)
        self.verbose = verbose
        self.max_pages = max_pages or MAX_PAGES
        init_db()
        self._init_batches()
    
    def _log(self, msg: str):
        if self.verbose:
            print(msg)
    
    def _init_batches(self):
        """Initialize batch configs in database."""
        for batch_name, config in KEYWORD_BATCHES.items():
            save_batch_config(
                batch_name=batch_name,
                keywords=config['keywords'],
                description=config.get('description', ''),
                priority=config.get('priority', 1)
            )
    
    def collect_batch(
        self,
        batch_name: str,
        max_pages: int = None
    ) -> Dict[str, Any]:
        """
        Collect tweets for a specific batch.
        
        Args:
            batch_name: Name of the batch to collect
            max_pages: Maximum pages to fetch (overrides default)
        
        Returns:
            Dict with collection results
        """
        max_pages = max_pages or self.max_pages
        
        self._log(f"\n[BATCH] {batch_name}")
        
        # Get batch config
        config = KEYWORD_BATCHES.get(batch_name)
        if not config:
            self._log(f"[ERROR] Batch '{batch_name}' not found")
            return {"error": f"Batch '{batch_name}' not found"}
        
        # Build query
        query = build_query_for_batch(batch_name)
        self._log(f"[QUERY] {query[:80]}...")
        
        start_time = time.time()
        
        # Track results
        tweets_found = 0
        new_tweets = 0
        pages_fetched = 0
        stopped_reason = "completed"
        first_tweet_id = None
        error_message = None
        
        # Get last seen tweet IDs for dedup
        batch_db = get_batch_config(batch_name)
        last_seen_id = batch_db.get('last_tweet_id') if batch_db else None
        
        try:
            cursor = ""
            
            for page in range(max_pages):
                pages_fetched += 1
                
                # Fetch page
                response = self.client.search(query=query, cursor=cursor)
                
                if "error" in response:
                    error_message = response.get("error", "Unknown error")
                    stopped_reason = "error"
                    self._log(f"[ERROR] {error_message[:50]}")
                    break
                
                tweets = response.get("tweets", [])
                
                if not tweets:
                    stopped_reason = "no_more_tweets"
                    self._log(f"[PAGE {page+1}] No tweets returned")
                    break
                
                self._log(f"[PAGE {page+1}] tweets={len(tweets)}")
                
                # Process tweets
                page_new = 0
                should_stop = False
                
                for tweet in tweets:
                    tweet_id = tweet.get('id', '')
                    tweet_created_at = tweet.get('createdAt', '')
                    tweets_found += 1
                    
                    # Save first tweet ID for next run
                    if first_tweet_id is None:
                        first_tweet_id = tweet_id
                    
                    # Check if tweet is from today (stop if older)
                    if tweet_created_at and not is_tweet_from_today(tweet_created_at):
                        stopped_reason = "old_tweet"
                        should_stop = True
                        self._log(f"[STOP] Reached old tweet from {tweet_created_at[:10]} - stopping")
                        break
                    
                    # Check if we've seen this tweet before
                    if last_seen_id and tweet_id == last_seen_id:
                        stopped_reason = "seen_tweet"
                        should_stop = True
                        self._log(f"[STOP] Reached previously seen tweet: {tweet_id}")
                        break
                    
                    # Save if new
                    if not tweet_exists(tweet_id):
                        saved = save_tweet(tweet, query_used=f"batch:{batch_name}")
                        if saved:
                            new_tweets += 1
                            page_new += 1
                
                self._log(f"[PAGE {page+1}] new={page_new}")
                
                if should_stop:
                    break
                
                # Check for more pages
                if not response.get("has_next_page"):
                    stopped_reason = "no_more_pages"
                    break
                
                cursor = response.get("next_cursor", "")
                if not cursor:
                    stopped_reason = "no_cursor"
                    break
                
                # Rate limiting
                time.sleep(1)
        
        except Exception as e:
            error_message = str(e)
            stopped_reason = "exception"
            self._log(f"[EXCEPTION] {error_message[:50]}")
        
        elapsed = time.time() - start_time
        
        # Update batch stats
        update_batch_stats(
            batch_name=batch_name,
            tweets_found=tweets_found,
            new_tweets=new_tweets,
            last_tweet_id=first_tweet_id
        )
        
        # Save run history
        save_collection_run(
            batch_name=batch_name,
            query_used=query,
            pages_fetched=pages_fetched,
            tweets_found=tweets_found,
            new_tweets=new_tweets,
            stopped_reason=stopped_reason,
            elapsed_time=elapsed,
            error_message=error_message
        )
        
        self._log(f"[DONE] found={tweets_found} | new={new_tweets} | pages={pages_fetched} | reason={stopped_reason} | time={elapsed:.2f}s")
        
        return {
            "batch_name": batch_name,
            "tweets_found": tweets_found,
            "new_tweets": new_tweets,
            "pages_fetched": pages_fetched,
            "stopped_reason": stopped_reason,
            "elapsed_time": elapsed,
            "error": error_message
        }
    
    def collect_all_batches(
        self,
        max_pages: int = None,
        delay_between: float = 2.0
    ) -> Dict[str, Any]:
        """
        Collect tweets from all batches.
        
        Args:
            max_pages: Maximum pages per batch
            delay_between: Delay between batches (seconds)
        
        Returns:
            Dict with aggregated results
        """
        max_pages = max_pages or self.max_pages
        batch_names = get_batch_names()
        
        self._log("\n" + "=" * 60)
        self._log(f"[RUN] tweets.batch_collector | batches={len(batch_names)} | max_pages={max_pages}")
        self._log("=" * 60)
        
        start_time = time.time()
        
        total_found = 0
        total_new = 0
        results = []
        
        for i, batch_name in enumerate(batch_names, 1):
            self._log(f"\n[{i}/{len(batch_names)}] Processing batch: {batch_name}")
            
            result = self.collect_batch(batch_name, max_pages=max_pages)
            results.append(result)
            
            total_found += result.get("tweets_found", 0)
            total_new += result.get("new_tweets", 0)
            
            if i < len(batch_names):
                time.sleep(delay_between)
        
        elapsed = time.time() - start_time
        
        self._log("\n" + "=" * 60)
        self._log(f"[ALL_DONE] batches={len(batch_names)} | total_found={total_found} | total_new={total_new} | time={elapsed:.2f}s")
        self._log("=" * 60)
        
        return {
            "batches_processed": len(batch_names),
            "total_found": total_found,
            "total_new": total_new,
            "elapsed_time": elapsed,
            "results": results
        }
    
    def collect_priority_batches(
        self,
        priority: int = 1,
        max_pages: int = None
    ) -> Dict[str, Any]:
        """Collect only batches with specified priority."""
        max_pages = max_pages or self.max_pages
        
        batch_names = [
            name for name, config in KEYWORD_BATCHES.items()
            if config.get('priority', 1) == priority
        ]
        
        self._log(f"\n[PRIORITY {priority}] batches={len(batch_names)}")
        
        results = []
        total_new = 0
        
        for batch_name in batch_names:
            result = self.collect_batch(batch_name, max_pages=max_pages)
            results.append(result)
            total_new += result.get("new_tweets", 0)
            time.sleep(1)
        
        return {
            "priority": priority,
            "batches_processed": len(batch_names),
            "total_new": total_new,
            "results": results
        }

