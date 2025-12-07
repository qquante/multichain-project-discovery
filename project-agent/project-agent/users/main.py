# users/main.py
import sys
sys.path.append('..')

import time
from typing import Optional
from .database import init_db, get_user_tweets, get_user_tweet_count, search_user_tweets
from .api_client import UserTweetsClient


def fetch_user_tweets(
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
    include_replies: bool = False,
    max_pages: int = 5,
    verbose: bool = True
) -> dict:
    """
    Fetch tweets from a specific user.
    
    Args:
        user_id: User ID (recommended, more stable)
        user_name: Screen name (@handle without @)
        include_replies: Include reply tweets
        max_pages: Maximum pages to fetch
        verbose: Print logs
    
    Returns:
        Stats dict with total, saved, duplicates, user_id, user_name
    """
    init_db()
    client = UserTweetsClient(verbose=verbose)
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"[RUN] users.fetch_user_tweets | user_id={user_id} | user_name={user_name}")
        print(f"{'='*60}")
    
    stats = client.fetch_and_save(
        user_id=user_id,
        user_name=user_name,
        include_replies=include_replies,
        max_pages=max_pages,
        stop_on_seen=True,
        delay_between_pages=1.0
    )
    
    if verbose:
        identifier = user_id or user_name
        print(f"[DB] user_tweets_count={get_user_tweet_count(identifier)}")
    
    return stats


def fetch_by_user_id(user_id: str, include_replies: bool = False, max_pages: int = 5, verbose: bool = True) -> dict:
    """Convenience function to fetch by user ID."""
    return fetch_user_tweets(user_id=user_id, include_replies=include_replies, max_pages=max_pages, verbose=verbose)


def fetch_by_username(user_name: str, include_replies: bool = False, max_pages: int = 5, verbose: bool = True) -> dict:
    """Convenience function to fetch by username."""
    return fetch_user_tweets(user_name=user_name, include_replies=include_replies, max_pages=max_pages, verbose=verbose)


def show_user_tweets(user_identifier: str, limit: int = 10):
    """Show recent tweets from a user."""
    tweets = get_user_tweets(user_identifier, limit)
    
    print(f"\n[USER_TWEETS] user={user_identifier} | count={len(tweets)}")
    print("-" * 60)
    
    for i, t in enumerate(tweets, 1):
        text_preview = t['text'][:60].replace('\n', ' ') if t['text'] else ''
        print(f"{i:2}. likes={t['like_count']:>4} | rt={t['retweet_count']:>4} | views={t['view_count']:>6} | {text_preview}...")


def search_in_user_tweets(keyword: str, limit: int = 20):
    """Search in captured user tweets."""
    tweets = search_user_tweets(keyword, limit)
    print(f"\n[SEARCH] keyword='{keyword}' | results={len(tweets)}")
    
    for t in tweets:
        text_preview = t['text'][:50].replace('\n', ' ') if t['text'] else ''
        print(f"  @{t['author_username']}: {text_preview}...")


if __name__ == "__main__":
    start = time.time()
    
    # Example: fetch tweets from a user
    # fetch_by_username("elonmusk", max_pages=2)
    # fetch_by_user_id("44196397", max_pages=2)
    
    print("[INFO] Usage:")
    print("  fetch_user_tweets(user_id='123', max_pages=5)")
    print("  fetch_user_tweets(user_name='username', include_replies=True)")
    print("  fetch_by_user_id('44196397')")
    print("  fetch_by_username('elonmusk')")
    
    print(f"\n[TOTAL_TIME] {time.time() - start:.2f}s")

