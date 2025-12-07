# tweets/main.py
import sys
sys.path.append('..')

import time
from .database import (
    init_db, get_tweet_count, get_all_tweets, search_tweets,
    get_all_batch_configs, get_collection_history, get_batch_stats
)
from .api_client import TwitterSearchClient
from .query_builder import QueryBuilder, early_project_query, custom_keywords_query
from .batch_collector import BatchCollector
from .keywords import KEYWORD_BATCHES, get_batch_names, build_query_for_batch


# ============================================
# BATCH COLLECTION (Stage 0)
# ============================================

def run_batch_collection(batch_name: str = None, max_pages: int = 5, verbose: bool = True) -> dict:
    """
    Run batch collection for a specific batch or all batches.
    
    Args:
        batch_name: Specific batch to run, or None for all batches
        max_pages: Maximum pages per batch
        verbose: Print output
    
    Returns:
        Collection results
    """
    init_db()
    collector = BatchCollector(verbose=verbose, max_pages=max_pages)
    
    if batch_name:
        return collector.collect_batch(batch_name, max_pages=max_pages)
    else:
        return collector.collect_all_batches(max_pages=max_pages)


def run_all_batches(max_pages: int = 5, verbose: bool = True) -> dict:
    """Run collection for all keyword batches."""
    return run_batch_collection(batch_name=None, max_pages=max_pages, verbose=verbose)


def run_priority_batches(priority: int = 1, max_pages: int = 5, verbose: bool = True) -> dict:
    """Run collection for batches with specific priority."""
    init_db()
    collector = BatchCollector(verbose=verbose, max_pages=max_pages)
    return collector.collect_priority_batches(priority=priority, max_pages=max_pages)


def show_batches():
    """Show all configured keyword batches."""
    init_db()
    
    print(f"\n[KEYWORD BATCHES] count={len(KEYWORD_BATCHES)}")
    print("-" * 60)
    
    for name in get_batch_names():
        config = KEYWORD_BATCHES[name]
        kw_count = len(config['keywords'])
        priority = config.get('priority', 1)
        desc = config.get('description', '')
        
        print(f"\n  [{name}] priority={priority} | keywords={kw_count}")
        print(f"  Description: {desc}")
        print(f"  Keywords: {', '.join(config['keywords'][:3])}...")
        
        # Show query
        query = build_query_for_batch(name)
        print(f"  Query: {query[:60]}...")


def show_batch_status():
    """Show status of all batches."""
    init_db()
    stats = get_batch_stats()
    
    print(f"\n[BATCH STATUS]")
    print("-" * 60)
    print(f"  Total batches: {stats['total_batches']}")
    print(f"  Total runs: {stats['total_runs']}")
    print(f"  Total tweets collected: {stats['total_tweets_collected']}")
    
    print(f"\n  By Batch:")
    for name, data in stats['by_batch'].items():
        last_run = data['last_run'][:16] if data['last_run'] else 'Never'
        print(f"    {name:<16} | found={data['found']:>5} | new={data['new']:>5} | last={last_run}")


def show_collection_history_report(batch_name: str = None, limit: int = 10):
    """Show collection history."""
    init_db()
    history = get_collection_history(batch_name=batch_name, limit=limit)
    
    label = f"batch={batch_name}" if batch_name else "all"
    print(f"\n[COLLECTION HISTORY] {label} | count={len(history)}")
    print("-" * 60)
    
    for h in history:
        run_time = h['run_at'][:16] if h['run_at'] else ''
        print(f"  [{run_time}] {h['batch_name']:<16} | found={h['tweets_found']:>4} | new={h['new_tweets']:>4} | pages={h['pages_fetched']} | reason={h['stopped_reason']}")


# ============================================
# LEGACY FUNCTIONS
# ============================================

def run_early_project_search(verbose: bool = True) -> dict:
    init_db()
    client = TwitterSearchClient(verbose=verbose)
    query = early_project_query()
    
    if verbose:
        print(f"\n{'='*60}")
        print("[RUN] tweets.early_project_search")
        print(f"{'='*60}")
    
    stats = client.search_and_save(
        query=query,
        query_type="Latest",
        max_pages=5,
        stop_on_seen=True,
        delay_between_pages=1.0
    )
    
    if verbose:
        print(f"[DB] total_tweets={get_tweet_count()}")
    
    return stats


def run_custom_search(keywords: list[str], max_pages: int = 5, verbose: bool = True) -> dict:
    init_db()
    client = TwitterSearchClient(verbose=verbose)
    query = custom_keywords_query(*keywords)
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"[RUN] tweets.custom_search | keywords={keywords}")
        print(f"{'='*60}")
    
    return client.search_and_save(
        query=query,
        query_type="Latest",
        max_pages=max_pages,
        stop_on_seen=True
    )


def run_raw_query(query_string: str, max_pages: int = 5, verbose: bool = True) -> dict:
    init_db()
    client = TwitterSearchClient(verbose=verbose)
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"[RUN] tweets.raw_query")
        print(f"{'='*60}")
    
    return client.search_and_save(
        query=query_string,
        query_type="Latest",
        max_pages=max_pages,
        stop_on_seen=True
    )


def show_recent_tweets(limit: int = 10):
    tweets = get_all_tweets(limit)
    
    print(f"\n[RECENT] count={len(tweets)}")
    print("-" * 60)
    
    for i, t in enumerate(tweets, 1):
        text_preview = t['text'][:60].replace('\n', ' ') if t['text'] else ''
        print(f"{i:2}. @{t['author_username']:<16} | followers={t['author_followers']:>7} | likes={t['like_count']:>4} | {text_preview}...")


def search_in_db(keyword: str, limit: int = 20):
    tweets = search_tweets(keyword, limit)
    print(f"\n[DB_SEARCH] keyword='{keyword}' | results={len(tweets)}")
    
    for t in tweets:
        text_preview = t['text'][:50].replace('\n', ' ') if t['text'] else ''
        print(f"  @{t['author_username']}: {text_preview}...")


if __name__ == "__main__":
    start = time.time()
    run_early_project_search()
    show_recent_tweets(10)
    print(f"\n[TOTAL_TIME] {time.time() - start:.2f}s")
