# tweets/api_client.py
import sys
sys.path.append('..')

import requests
import time
import hashlib
from typing import Dict, Any, List, Generator, Set
from urllib.parse import urlencode

from config import API_KEY, BASE_URL, MAX_PAGES
from .query_builder import QueryBuilder
from .database import get_last_seen_ids, update_query_state, save_tweet


class TwitterSearchClient:
    
    def __init__(self, api_key: str = API_KEY, verbose: bool = True):
        self.api_key = api_key
        self.base_url = f"{BASE_URL}/twitter/tweet/advanced_search"
        self.headers = {"X-API-Key": api_key}
        self.verbose = verbose
    
    def _log(self, msg: str):
        if self.verbose:
            print(msg)
    
    def search(
        self,
        query: str | QueryBuilder,
        query_type: str = "Latest",
        cursor: str = ""
    ) -> Dict[str, Any]:
        
        query_str = query.build() if isinstance(query, QueryBuilder) else query
        params = {"query": query_str, "queryType": query_type}
        if cursor:
            params["cursor"] = cursor
        
        url = f"{self.base_url}?{urlencode(params)}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def search_with_pagination(
        self,
        query: str | QueryBuilder,
        query_type: str = "Latest",
        max_pages: int = MAX_PAGES,
        stop_on_seen: bool = True,
        delay_between_pages: float = 1.0
    ) -> Generator[Dict[str, Any], None, None]:
        
        start_time = time.time()
        
        if isinstance(query, QueryBuilder):
            query_str = query.build()
            query_hash = query.get_hash()
        else:
            query_str = query
            query_hash = hashlib.md5(query_str.encode()).hexdigest()[:16]
        
        last_seen_ids: Set[str] = get_last_seen_ids(query_hash) if stop_on_seen else set()
        
        self._log(f"[SEARCH] query={query_str[:80]}{'...' if len(query_str) > 80 else ''}")
        self._log(f"[CONFIG] max_pages={max_pages} | cached_ids={len(last_seen_ids)} | stop_on_seen={stop_on_seen}")
        
        cursor = ""
        page = 0
        all_tweet_ids: List[str] = []
        total_yielded = 0
        should_stop = False
        
        while page < max_pages and not should_stop:
            page += 1
            page_start = time.time()
            
            try:
                response = self.search(query_str, query_type, cursor)
            except requests.exceptions.RequestException as e:
                self._log(f"[ERROR] page={page} | {e}")
                break
            
            tweets = response.get("tweets", [])
            has_next = response.get("has_next_page", False)
            next_cursor = response.get("next_cursor", "")
            page_time = time.time() - page_start
            
            self._log(f"[PAGE {page}/{max_pages}] tweets={len(tweets)} | time={page_time:.2f}s")
            
            if not tweets:
                break
            
            for tweet in tweets:
                tweet_id = tweet.get("id", "")
                
                if stop_on_seen and tweet_id in last_seen_ids:
                    self._log(f"[STOP] found_cached_id={tweet_id}")
                    should_stop = True
                    break
                
                all_tweet_ids.append(tweet_id)
                total_yielded += 1
                yield tweet
            
            if should_stop:
                break
            
            if has_next and next_cursor:
                cursor = next_cursor
                if page < max_pages:
                    time.sleep(delay_between_pages)
            else:
                break
        
        if all_tweet_ids:
            update_query_state(query_hash, query_str, all_tweet_ids, total_yielded)
        
        total_time = time.time() - start_time
        self._log(f"[DONE] total={total_yielded} | pages={page} | time={total_time:.2f}s")
    
    def search_and_save(
        self,
        query: str | QueryBuilder,
        query_type: str = "Latest",
        max_pages: int = MAX_PAGES,
        stop_on_seen: bool = True,
        delay_between_pages: float = 1.0
    ) -> Dict[str, int]:
        
        start_time = time.time()
        query_str = query.build() if isinstance(query, QueryBuilder) else query
        
        stats = {"total": 0, "saved": 0, "duplicates": 0}
        
        for tweet in self.search_with_pagination(
            query, query_type, max_pages, stop_on_seen, delay_between_pages
        ):
            stats["total"] += 1
            if save_tweet(tweet, query_str):
                stats["saved"] += 1
            else:
                stats["duplicates"] += 1
        
        total_time = time.time() - start_time
        self._log(f"[SAVED] new={stats['saved']} | duplicates={stats['duplicates']} | total={stats['total']} | time={total_time:.2f}s")
        
        return stats
