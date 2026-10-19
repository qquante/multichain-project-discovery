# users/api_client.py
import sys
sys.path.append('..')

import requests
import time
import hashlib
from typing import Dict, Any, List, Generator, Set, Optional
from urllib.parse import urlencode

from config import API_KEY, BASE_URL, MAX_PAGES
from .database import get_last_seen_ids, update_fetch_state, save_user_tweet


class UserInfoClient:
    """Client for GET /twitter/user/batch_info_by_ids endpoint."""
    
    def __init__(self, api_key: str = API_KEY, verbose: bool = True):
        self.api_key = api_key
        self.base_url = f"{BASE_URL}/twitter/user/batch_info_by_ids"
        self.headers = {"X-API-Key": api_key}
        self.verbose = verbose
    
    def _log(self, msg: str):
        if self.verbose:
            print(msg)
    
    def get_users_by_ids(
        self,
        user_ids: List[str],
        retries: int = 3,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """
        Get user info by user IDs (batch).
        
        Args:
            user_ids: List of user IDs
            retries: Number of retries
            timeout: Request timeout
        
        Returns:
            API response with users array, status, msg
        """
        if not user_ids:
            return {"users": [], "status": "success", "msg": "No user IDs provided"}
        
        # Join IDs with comma
        ids_param = ",".join(user_ids)
        url = f"{self.base_url}?userIds={ids_param}"
        
        last_error = None
        
        for attempt in range(retries):
            try:
                start_time = time.time()
                response = requests.get(url, headers=self.headers, timeout=timeout)
                elapsed = time.time() - start_time
                
                if response.status_code != 200:
                    self._log(f"[API_ERROR] status={response.status_code} | body={response.text[:200]}")
                    return {"error": response.text, "status_code": response.status_code}
                
                result = response.json()
                users = result.get("users", [])
                
                self._log(f"[USER_INFO] users_requested={len(user_ids)} | users_returned={len(users)} | time={elapsed:.2f}s")
                
                return {
                    "users": users,
                    "status": result.get("status", "success"),
                    "msg": result.get("msg", "")
                }
                
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                self._log(f"[RETRY] attempt={attempt+1}/{retries} | error={last_error[:50]}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        
        return {"error": last_error, "users": [], "status": "error"}
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get single user info by ID."""
        result = self.get_users_by_ids([user_id])
        users = result.get("users", [])
        return users[0] if users else None


class UserTweetsClient:
    """Client for GET /twitter/user/last_tweets endpoint."""
    
    def __init__(self, api_key: str = API_KEY, verbose: bool = True):
        self.api_key = api_key
        self.base_url = f"{BASE_URL}/twitter/user/last_tweets"
        self.headers = {"X-API-Key": api_key}
        self.verbose = verbose
    
    def _log(self, msg: str):
        if self.verbose:
            print(msg)
    
    def get_user_tweets(
        self,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        cursor: str = "",
        include_replies: bool = False
    ) -> Dict[str, Any]:
        """
        Single request to get user tweets.
        
        Args:
            user_id: User ID (recommended, more stable)
            user_name: Screen name (@handle without @)
            cursor: Pagination cursor
            include_replies: Include reply tweets
        
        Returns:
            API response with tweets, has_next_page, next_cursor, status, message
        """
        if not user_id and not user_name:
            raise ValueError("Either user_id or user_name must be provided")
        
        params = {}
        if user_id:
            params["userId"] = user_id
        elif user_name:
            params["userName"] = user_name
        
        if cursor:
            params["cursor"] = cursor
        
        params["includeReplies"] = str(include_replies).lower()
        
        url = f"{self.base_url}?{urlencode(params)}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        
        raw = response.json()
        
        # API returns nested structure: {status, code, msg, data: {pin_tweet, tweets}}
        # Normalize to flat structure
        data = raw.get("data", {})
        return {
            "status": raw.get("status", ""),
            "code": raw.get("code", 0),
            "message": raw.get("msg", ""),
            "pin_tweet": data.get("pin_tweet"),
            "tweets": data.get("tweets", []),
            "has_next_page": data.get("has_next_page", False),
            "next_cursor": data.get("next_cursor", "")
        }
    
    def get_user_tweets_paginated(
        self,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        include_replies: bool = False,
        max_pages: int = MAX_PAGES,
        stop_on_seen: bool = True,
        delay_between_pages: float = 1.0
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Get user tweets with automatic pagination.
        
        Args:
            user_id: User ID (recommended)
            user_name: Screen name
            include_replies: Include replies
            max_pages: Max pages to fetch
            stop_on_seen: Stop if we find already captured tweet
            delay_between_pages: Delay between requests
        
        Yields:
            Each tweet dict
        """
        start_time = time.time()
        
        user_identifier = user_id or user_name
        if not user_identifier:
            raise ValueError("Either user_id or user_name must be provided")
        
        last_seen_ids: Set[str] = get_last_seen_ids(user_identifier) if stop_on_seen else set()
        
        self._log(f"[USER_TWEETS] user_id={user_id} | user_name={user_name} | include_replies={include_replies}")
        self._log(f"[CONFIG] max_pages={max_pages} | cached_ids={len(last_seen_ids)} | stop_on_seen={stop_on_seen}")
        
        cursor = ""
        page = 0
        all_tweet_ids: List[str] = []
        total_yielded = 0
        should_stop = False
        resolved_user_id = user_id or ""
        resolved_user_name = user_name or ""
        
        while page < max_pages and not should_stop:
            page += 1
            page_start = time.time()
            
            try:
                response = self.get_user_tweets(
                    user_id=user_id,
                    user_name=user_name,
                    cursor=cursor,
                    include_replies=include_replies
                )
            except requests.exceptions.RequestException as e:
                self._log(f"[ERROR] page={page} | {e}")
                break
            
            # Check status
            status = response.get("status", "")
            message = response.get("message", "")
            
            if status == "error":
                self._log(f"[API_ERROR] status={status} | message={message}")
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
                
                # Resolve user info from first tweet
                author = tweet.get("author", {})
                if author and not resolved_user_id:
                    resolved_user_id = author.get("id", "")
                if author and not resolved_user_name:
                    resolved_user_name = author.get("userName", "")
                
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
            update_fetch_state(
                user_identifier=user_identifier,
                user_id=resolved_user_id,
                user_name=resolved_user_name,
                tweet_ids=all_tweet_ids,
                total=total_yielded
            )
        
        total_time = time.time() - start_time
        self._log(f"[DONE] total={total_yielded} | pages={page} | time={total_time:.2f}s")
    
    def fetch_and_save(
        self,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        include_replies: bool = False,
        max_pages: int = MAX_PAGES,
        stop_on_seen: bool = True,
        delay_between_pages: float = 1.0
    ) -> Dict[str, Any]:
        """
        Fetch user tweets and save to database.
        
        Returns:
            Dict with stats: total, saved, duplicates, user_id, user_name
        """
        start_time = time.time()
        
        stats = {
            "total": 0,
            "saved": 0,
            "duplicates": 0,
            "user_id": user_id or "",
            "user_name": user_name or ""
        }
        
        for tweet in self.get_user_tweets_paginated(
            user_id=user_id,
            user_name=user_name,
            include_replies=include_replies,
            max_pages=max_pages,
            stop_on_seen=stop_on_seen,
            delay_between_pages=delay_between_pages
        ):
            stats["total"] += 1
            
            # Update user info from tweet
            author = tweet.get("author", {})
            if author:
                if not stats["user_id"]:
                    stats["user_id"] = author.get("id", "")
                if not stats["user_name"]:
                    stats["user_name"] = author.get("userName", "")
            
            if save_user_tweet(
                tweet_data=tweet,
                fetched_by_user_id=user_id or "",
                fetched_by_username=user_name or "",
                include_replies=include_replies
            ):
                stats["saved"] += 1
            else:
                stats["duplicates"] += 1
        
        total_time = time.time() - start_time
        self._log(f"[SAVED] new={stats['saved']} | duplicates={stats['duplicates']} | total={stats['total']} | time={total_time:.2f}s")
        
        return stats


class UserFollowingsClient:
    """Client for GET /twitter/user/followings endpoint."""
    
    def __init__(self, api_key: str = API_KEY, verbose: bool = True):
        self.api_key = api_key
        self.base_url = f"{BASE_URL}/twitter/user/followings"
        self.headers = {"X-API-Key": api_key}
        self.verbose = verbose
    
    def _log(self, msg: str):
        if self.verbose:
            print(msg)
    
    def get_user_followings(
        self,
        user_name: str,
        page_size: int = 20,
        cursor: str = ""
    ) -> Dict[str, Any]:
        """
        Get user followings (most recent first).
        Only the first page is used by the alpha-followers service.
        """
        params = {
            "userName": user_name,
            "pageSize": page_size
        }
        if cursor:
            params["cursor"] = cursor
        
        url = f"{self.base_url}?{urlencode(params)}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        data = response.json()
        
        # Normalize keys defensively
        return {
            "followings": data.get("followings", []),
            "has_next_page": data.get("has_next_page", False),
            "next_cursor": data.get("next_cursor", ""),
            "status": data.get("status", ""),
            "message": data.get("message", "")
        }


class TweetsByIdClient:
    """Client for GET /twitter/tweets endpoint - fetch tweets by IDs."""
    
    def __init__(self, api_key: str = API_KEY, verbose: bool = True):
        self.api_key = api_key
        self.base_url = f"{BASE_URL}/twitter/tweets"
        self.headers = {"X-API-Key": api_key}
        self.verbose = verbose
    
    def _log(self, msg: str):
        if self.verbose:
            print(msg)
    
    def get_tweets_by_ids(
        self,
        tweet_ids: List[str],
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Fetch tweets by their IDs.
        
        Args:
            tweet_ids: List of tweet IDs to fetch
            timeout: Request timeout in seconds
        
        Returns:
            Dict with 'tweets' list and 'status'
        """
        if not tweet_ids:
            return {"tweets": [], "status": "success", "msg": "No tweet IDs provided"}
        
        # Join IDs with comma
        ids_param = ",".join(tweet_ids)
        url = f"{self.base_url}?tweet_ids={ids_param}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=timeout)
            
            if response.status_code != 200:
                self._log(f"[API_ERROR] status={response.status_code} | body={response.text[:200]}")
                return {"tweets": [], "status": "error", "error": response.text}
            
            data = response.json()
            tweets = data.get("tweets", [])
            
            self._log(f"[TWEETS_BY_ID] requested={len(tweet_ids)} | returned={len(tweets)}")
            
            return {
                "tweets": tweets,
                "status": "success"
            }
            
        except Exception as e:
            self._log(f"[ERROR] get_tweets_by_ids: {str(e)[:50]}")
            return {"tweets": [], "status": "error", "error": str(e)}
    
    def get_tweet_by_id(self, tweet_id: str) -> Optional[Dict[str, Any]]:
        """Get a single tweet by ID."""
        result = self.get_tweets_by_ids([tweet_id])
        tweets = result.get("tweets", [])
        return tweets[0] if tweets else None
