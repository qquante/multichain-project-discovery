import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

# Reuse the users.db location for cache to stay close to tweet/user data
try:
    from users.database import DB_PATH as USERS_DB_PATH
except Exception:
    USERS_DB_PATH = os.environ.get("DB_PATH", "users.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(USERS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_cache_tables():
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS twitter_cache (
            cache_key TEXT NOT NULL,
            cache_type TEXT NOT NULL, -- 'tweets' | 'user_info'
            data TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (cache_key, cache_type)
        )
        """
    )
    conn.commit()
    conn.close()


# Initialize tables on import
_init_cache_tables()


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _is_fresh(fetched_at: str, ttl_hours: int) -> bool:
    try:
        fetched_dt = datetime.fromisoformat(fetched_at)
        return datetime.utcnow() - fetched_dt <= timedelta(hours=ttl_hours)
    except Exception:
        return False


def _normalize_handle(handle: Optional[str]) -> str:
    return (handle or "").strip().lstrip("@").lower()


def _make_key(handle: Optional[str], author_id: Optional[str]) -> Optional[str]:
    if author_id:
        return f"id:{author_id}"
    norm = _normalize_handle(handle)
    return f"handle:{norm}" if norm else None


def get_cached(cache_key: str, cache_type: str, ttl_hours: int = 6) -> Optional[Dict[str, Any]]:
    if not cache_key:
        return None
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT data, fetched_at FROM twitter_cache WHERE cache_key = ? AND cache_type = ?",
        (cache_key, cache_type),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    data_json, fetched_at = row["data"], row["fetched_at"]
    if not _is_fresh(fetched_at, ttl_hours):
        return None

    try:
        return json.loads(data_json)
    except Exception:
        return None


def set_cached(cache_key: str, cache_type: str, data: Dict[str, Any]):
    if not cache_key or data is None:
        return
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO twitter_cache (cache_key, cache_type, data, fetched_at)
        VALUES (?, ?, ?, ?)
        """,
        (cache_key, cache_type, json.dumps(data), _now_iso()),
    )
    conn.commit()
    conn.close()


def get_or_fetch_user_tweets(
    user_tweets_client,
    handle: Optional[str] = None,
    author_id: Optional[str] = None,
    include_replies: bool = False,
    ttl_hours: int = 6,
) -> Dict[str, Any]:
    """
    Fetch user tweets with cache (TTL hours). Returns the same structure as UserTweetsClient.get_user_tweets.
    """
    cache_key = _make_key(handle, author_id)
    if cache_key:
        cached = get_cached(cache_key, "tweets", ttl_hours)
        if cached:
            return cached

    # Fallback: fetch from API
    if author_id:
        response = user_tweets_client.get_user_tweets(
            user_id=author_id,
            include_replies=include_replies,
        )
    else:
        response = user_tweets_client.get_user_tweets(
            user_name=_normalize_handle(handle),
            include_replies=include_replies,
        )

    # Save to cache (also store under author_id if we discover it)
    if cache_key:
        set_cached(cache_key, "tweets", response)

    # If we have an author_id inside the response, store an additional cache entry
    try:
        tweets = response.get("tweets") or []
        if tweets:
            author = tweets[0].get("author", {}) or {}
            discovered_id = author.get("id")
            if discovered_id:
                alt_key = _make_key(None, discovered_id)
                if alt_key and alt_key != cache_key:
                    set_cached(alt_key, "tweets", response)
    except Exception:
        pass

    return response


def get_or_fetch_user_info(
    user_info_client,
    author_id: Optional[str] = None,
    handle: Optional[str] = None,
    ttl_hours: int = 6,
) -> Optional[Dict[str, Any]]:
    """
    Fetch user info with cache (TTL hours). Returns a user dict or None.
    """
    cache_key = _make_key(handle, author_id)
    if cache_key:
        cached = get_cached(cache_key, "user_info", ttl_hours)
        if cached:
            return cached

    if not author_id:
        return None

    # Fetch from API
    result = user_info_client.get_users_by_ids([author_id])
    users = result.get("users", []) if isinstance(result, dict) else []
    user = users[0] if users else None

    if cache_key and user:
        set_cached(cache_key, "user_info", user)

    return user

