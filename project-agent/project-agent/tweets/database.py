# tweets/database.py
import os
import sys
import sqlite3
import json
from typing import List, Set, Dict, Any
from datetime import datetime

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Support Docker environment variable for DB path
DB_DIR = os.environ.get('DB_PATH', '.')
DB_PATH = os.path.join(DB_DIR, 'tweets.db') if DB_DIR != '.' else 'tweets.db'

# Supabase sync (import lazily to avoid circular imports)
def _sync_to_supabase(table: str, data: dict, upsert: bool = True) -> bool:
    """Sync data to Supabase (non-blocking, fails silently)."""
    try:
        from db.supabase_client import sync_to_supabase
        return sync_to_supabase(table, data, upsert)
    except Exception as e:
        # Silent fail - don't break local operations
        return False


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
    except Exception:
        pass
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tweets (
            id TEXT PRIMARY KEY,
            type TEXT,
            url TEXT,
            twitter_url TEXT,
            text TEXT,
            source TEXT,
            retweet_count INTEGER DEFAULT 0,
            reply_count INTEGER DEFAULT 0,
            like_count INTEGER DEFAULT 0,
            quote_count INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            created_at TEXT,
            lang TEXT,
            bookmark_count INTEGER DEFAULT 0,
            is_reply INTEGER DEFAULT 0,
            in_reply_to_id TEXT,
            conversation_id TEXT,
            display_text_range TEXT,
            in_reply_to_user_id TEXT,
            in_reply_to_username TEXT,
            is_limited_reply INTEGER DEFAULT 0,
            author_id TEXT,
            author_username TEXT,
            author_name TEXT,
            author_url TEXT,
            author_twitter_url TEXT,
            author_is_verified INTEGER DEFAULT 0,
            author_is_blue_verified INTEGER DEFAULT 0,
            author_verified_type TEXT,
            author_profile_picture TEXT,
            author_cover_picture TEXT,
            author_description TEXT,
            author_location TEXT,
            author_followers INTEGER DEFAULT 0,
            author_following INTEGER DEFAULT 0,
            author_can_dm INTEGER DEFAULT 0,
            author_created_at TEXT,
            author_favourites_count INTEGER DEFAULT 0,
            author_media_count INTEGER DEFAULT 0,
            author_statuses_count INTEGER DEFAULT 0,
            author_is_automated INTEGER DEFAULT 0,
            author_profile_bio TEXT,
            entities_json TEXT,
            extended_entities_json TEXT,
            card_json TEXT,
            place_json TEXT,
            quoted_tweet_id TEXT,
            retweeted_tweet_id TEXT,
            captured_at TEXT DEFAULT CURRENT_TIMESTAMP,
            query_used TEXT,
            raw_json TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS query_state (
            query_hash TEXT PRIMARY KEY,
            query_text TEXT,
            last_tweet_ids TEXT,
            last_run_at TEXT,
            total_captured INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quoted_tweets (
            id TEXT PRIMARY KEY,
            parent_tweet_id TEXT,
            raw_json TEXT,
            FOREIGN KEY (parent_tweet_id) REFERENCES tweets(id)
        )
    ''')
    
    # Batch collection tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keyword_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_name TEXT UNIQUE NOT NULL,
            keywords TEXT NOT NULL,
            description TEXT,
            priority INTEGER DEFAULT 1,
            last_run_at TEXT,
            last_tweet_id TEXT,
            tweets_found INTEGER DEFAULT 0,
            new_tweets INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS collection_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_name TEXT NOT NULL,
            run_at TEXT DEFAULT CURRENT_TIMESTAMP,
            query_used TEXT,
            pages_fetched INTEGER DEFAULT 0,
            tweets_found INTEGER DEFAULT 0,
            new_tweets INTEGER DEFAULT 0,
            stopped_reason TEXT,
            elapsed_time REAL DEFAULT 0,
            error_message TEXT
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tweets_author_id ON tweets(author_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tweets_created_at ON tweets(created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tweets_captured_at ON tweets(captured_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tweets_author_username ON tweets(author_username)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_batch_name ON keyword_batches(batch_name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_collection_batch ON collection_history(batch_name)')
    
    conn.commit()
    conn.close()


def get_last_seen_ids(query_hash: str) -> Set[str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT last_tweet_ids FROM query_state WHERE query_hash = ?', (query_hash,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row['last_tweet_ids']:
        return set(json.loads(row['last_tweet_ids']))
    return set()


def update_query_state(query_hash: str, query_text: str, tweet_ids: List[str], total: int):
    conn = get_connection()
    cursor = conn.cursor()
    
    from config import LAST_IDS_TO_CHECK
    ids_to_save = tweet_ids[:LAST_IDS_TO_CHECK]
    
    cursor.execute('''
        INSERT OR REPLACE INTO query_state (query_hash, query_text, last_tweet_ids, last_run_at, total_captured)
        VALUES (?, ?, ?, ?, ?)
    ''', (query_hash, query_text, json.dumps(ids_to_save), datetime.now().isoformat(), total))
    
    conn.commit()
    conn.close()
    
    # === DUAL-WRITE: Sync to Supabase ===
    _sync_to_supabase("query_state", {
        "query_hash": query_hash,
        "query_text": query_text,
        "last_tweet_ids": ids_to_save,
        "last_run_at": datetime.now().isoformat(),
        "total_captured": total
    })


def tweet_exists(tweet_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM tweets WHERE id = ?', (tweet_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def save_tweet(tweet_data: Dict[str, Any], query_used: str = "") -> bool:
    if tweet_exists(tweet_data.get('id', '')):
        return False
    
    conn = get_connection()
    cursor = conn.cursor()
    
    author = tweet_data.get('author', {}) or {}
    entities = tweet_data.get('entities', {}) or {}
    extended_entities = tweet_data.get('extendedEntities', {}) or {}
    card = tweet_data.get('card', {}) or {}
    place = tweet_data.get('place', {}) or {}
    profile_bio = author.get('profile_bio', {}) or {}
    
    quoted_tweet = tweet_data.get('quoted_tweet')
    quoted_tweet_id = quoted_tweet.get('id') if quoted_tweet else None
    
    retweeted_tweet = tweet_data.get('retweeted_tweet')
    retweeted_tweet_id = retweeted_tweet.get('id') if retweeted_tweet else None
    
    cursor.execute('''
        INSERT OR IGNORE INTO tweets (
            id, type, url, twitter_url, text, source,
            retweet_count, reply_count, like_count, quote_count, view_count,
            created_at, lang, bookmark_count, is_reply,
            in_reply_to_id, conversation_id, display_text_range,
            in_reply_to_user_id, in_reply_to_username, is_limited_reply,
            author_id, author_username, author_name, author_url, author_twitter_url,
            author_is_verified, author_is_blue_verified, author_verified_type,
            author_profile_picture, author_cover_picture, author_description,
            author_location, author_followers, author_following, author_can_dm,
            author_created_at, author_favourites_count, author_media_count,
            author_statuses_count, author_is_automated, author_profile_bio,
            entities_json, extended_entities_json, card_json, place_json,
            quoted_tweet_id, retweeted_tweet_id, query_used, raw_json
        ) VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?
        )
    ''', (
        tweet_data.get('id'),
        tweet_data.get('type'),
        tweet_data.get('url'),
        tweet_data.get('twitterUrl'),
        tweet_data.get('text'),
        tweet_data.get('source'),
        tweet_data.get('retweetCount', 0),
        tweet_data.get('replyCount', 0),
        tweet_data.get('likeCount', 0),
        tweet_data.get('quoteCount', 0),
        tweet_data.get('viewCount', 0),
        tweet_data.get('createdAt'),
        tweet_data.get('lang'),
        tweet_data.get('bookmarkCount', 0),
        1 if tweet_data.get('isReply') else 0,
        tweet_data.get('inReplyToId'),
        tweet_data.get('conversationId'),
        json.dumps(tweet_data.get('displayTextRange', [])),
        tweet_data.get('inReplyToUserId'),
        tweet_data.get('inReplyToUsername'),
        1 if tweet_data.get('isLimitedReply') else 0,
        author.get('id'),
        author.get('userName'),
        author.get('name'),
        author.get('url'),
        author.get('twitterUrl'),
        1 if author.get('isVerified') else 0,
        1 if author.get('isBlueVerified') else 0,
        author.get('verifiedType'),
        author.get('profilePicture'),
        author.get('coverPicture'),
        author.get('description'),
        author.get('location'),
        author.get('followers', 0),
        author.get('following', 0),
        1 if author.get('canDm') else 0,
        author.get('createdAt'),
        author.get('favouritesCount', 0),
        author.get('mediaCount', 0),
        author.get('statusesCount', 0),
        1 if author.get('isAutomated') else 0,
        json.dumps(profile_bio) if profile_bio else None,
        json.dumps(entities) if entities else None,
        json.dumps(extended_entities) if extended_entities else None,
        json.dumps(card) if card else None,
        json.dumps(place) if place else None,
        quoted_tweet_id,
        retweeted_tweet_id,
        query_used,
        json.dumps(tweet_data)
    ))
    
    if quoted_tweet:
        cursor.execute('''
            INSERT OR IGNORE INTO quoted_tweets (id, parent_tweet_id, raw_json)
            VALUES (?, ?, ?)
        ''', (quoted_tweet.get('id'), tweet_data.get('id'), json.dumps(quoted_tweet)))
    
    conn.commit()
    conn.close()
    
    # === DUAL-WRITE: Sync to Supabase ===
    supabase_data = {
        "id": tweet_data.get('id'),
        "type": tweet_data.get('type'),
        "url": tweet_data.get('url'),
        "twitter_url": tweet_data.get('twitterUrl'),
        "text": tweet_data.get('text'),
        "source": tweet_data.get('source'),
        "retweet_count": tweet_data.get('retweetCount', 0),
        "reply_count": tweet_data.get('replyCount', 0),
        "like_count": tweet_data.get('likeCount', 0),
        "quote_count": tweet_data.get('quoteCount', 0),
        "view_count": tweet_data.get('viewCount', 0),
        "created_at": tweet_data.get('createdAt'),
        "lang": tweet_data.get('lang'),
        "bookmark_count": tweet_data.get('bookmarkCount', 0),
        "is_reply": bool(tweet_data.get('isReply')),
        "in_reply_to_id": tweet_data.get('inReplyToId'),
        "conversation_id": tweet_data.get('conversationId'),
        "display_text_range": tweet_data.get('displayTextRange', []),
        "in_reply_to_user_id": tweet_data.get('inReplyToUserId'),
        "in_reply_to_username": tweet_data.get('inReplyToUsername'),
        "is_limited_reply": bool(tweet_data.get('isLimitedReply')),
        "author_id": author.get('id'),
        "author_username": author.get('userName'),
        "author_name": author.get('name'),
        "author_url": author.get('url'),
        "author_twitter_url": author.get('twitterUrl'),
        "author_is_verified": bool(author.get('isVerified')),
        "author_is_blue_verified": bool(author.get('isBlueVerified')),
        "author_verified_type": author.get('verifiedType'),
        "author_profile_picture": author.get('profilePicture'),
        "author_cover_picture": author.get('coverPicture'),
        "author_description": author.get('description'),
        "author_location": author.get('location'),
        "author_followers": author.get('followers', 0),
        "author_following": author.get('following', 0),
        "author_can_dm": bool(author.get('canDm')),
        "author_created_at": author.get('createdAt'),
        "author_favourites_count": author.get('favouritesCount', 0),
        "author_media_count": author.get('mediaCount', 0),
        "author_statuses_count": author.get('statusesCount', 0),
        "author_is_automated": bool(author.get('isAutomated')),
        "author_profile_bio": profile_bio if profile_bio else None,
        "entities_json": entities if entities else None,
        "extended_entities_json": extended_entities if extended_entities else None,
        "card_json": card if card else None,
        "place_json": place if place else None,
        "quoted_tweet_id": quoted_tweet_id,
        "retweeted_tweet_id": retweeted_tweet_id,
        "query_used": query_used,
        "raw_json": tweet_data
    }
    _sync_to_supabase("tweets", supabase_data)
    
    # Sync quoted tweet if exists
    if quoted_tweet:
        _sync_to_supabase("quoted_tweets", {
            "id": quoted_tweet.get('id'),
            "parent_tweet_id": tweet_data.get('id'),
            "raw_json": quoted_tweet
        })
    
    return True


def get_all_tweets(limit: int = 100) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tweets ORDER BY captured_at DESC LIMIT ?', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_tweet_count() -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM tweets')
    count = cursor.fetchone()['count']
    conn.close()
    return count


def search_tweets(keyword: str, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM tweets WHERE text LIKE ? ORDER BY captured_at DESC LIMIT ?',
        (f'%{keyword}%', limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ============================================
# BATCH COLLECTION FUNCTIONS
# ============================================

def save_batch_config(batch_name: str, keywords: list, description: str = "", priority: int = 1):
    """Save or update batch configuration."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO keyword_batches 
        (batch_name, keywords, description, priority)
        VALUES (?, ?, ?, ?)
    ''', (batch_name, json.dumps(keywords), description, priority))
    
    conn.commit()
    conn.close()
    
    # === DUAL-WRITE: Sync to Supabase ===
    _sync_to_supabase("keyword_batches", {
        "batch_name": batch_name,
        "keywords": keywords,
        "description": description,
        "priority": priority
    })


def get_batch_config(batch_name: str) -> Dict[str, Any]:
    """Get batch configuration."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM keyword_batches WHERE batch_name = ?', (batch_name,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return {}


def get_all_batch_configs() -> List[Dict[str, Any]]:
    """Get all batch configurations."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM keyword_batches ORDER BY priority, batch_name')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_batch_stats(batch_name: str, tweets_found: int, new_tweets: int, last_tweet_id: str = None):
    """Update batch statistics after a run."""
    conn = get_connection()
    cursor = conn.cursor()
    
    updates = ['last_run_at = ?', 'tweets_found = tweets_found + ?', 'new_tweets = ?']
    values = [datetime.now().isoformat(), tweets_found, new_tweets]
    
    if last_tweet_id:
        updates.append('last_tweet_id = ?')
        values.append(last_tweet_id)
    
    values.append(batch_name)
    
    cursor.execute(f'''
        UPDATE keyword_batches 
        SET {', '.join(updates)}
        WHERE batch_name = ?
    ''', values)
    
    conn.commit()
    conn.close()
    
    # === DUAL-WRITE: Sync to Supabase (update via upsert) ===
    # Get current data to merge
    current = get_batch_config(batch_name)
    if current:
        _sync_to_supabase("keyword_batches", {
            "batch_name": batch_name,
            "keywords": json.loads(current.get('keywords', '[]')) if isinstance(current.get('keywords'), str) else current.get('keywords', []),
            "description": current.get('description', ''),
            "priority": current.get('priority', 1),
            "last_run_at": datetime.now().isoformat(),
            "tweets_found": current.get('tweets_found', 0) + tweets_found,
            "new_tweets": new_tweets,
            "last_tweet_id": last_tweet_id or current.get('last_tweet_id')
        })


def save_collection_run(
    batch_name: str,
    query_used: str,
    pages_fetched: int,
    tweets_found: int,
    new_tweets: int,
    stopped_reason: str,
    elapsed_time: float,
    error_message: str = None
) -> int:
    """Save collection run history."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO collection_history 
        (batch_name, query_used, pages_fetched, tweets_found, new_tweets, stopped_reason, elapsed_time, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (batch_name, query_used, pages_fetched, tweets_found, new_tweets, stopped_reason, elapsed_time, error_message))
    
    run_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # === DUAL-WRITE: Sync to Supabase ===
    _sync_to_supabase("collection_history", {
        "batch_name": batch_name,
        "query_used": query_used,
        "pages_fetched": pages_fetched,
        "tweets_found": tweets_found,
        "new_tweets": new_tweets,
        "stopped_reason": stopped_reason,
        "elapsed_time": elapsed_time,
        "error_message": error_message,
        "run_at": datetime.now().isoformat()
    }, upsert=False)  # Insert only, no upsert
    
    return run_id


def get_collection_history(batch_name: str = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Get collection history."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if batch_name:
        cursor.execute('''
            SELECT * FROM collection_history 
            WHERE batch_name = ?
            ORDER BY run_at DESC LIMIT ?
        ''', (batch_name, limit))
    else:
        cursor.execute('''
            SELECT * FROM collection_history 
            ORDER BY run_at DESC LIMIT ?
        ''', (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_batch_stats() -> Dict[str, Any]:
    """Get statistics about batches."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Total batches
    cursor.execute('SELECT COUNT(*) FROM keyword_batches')
    total_batches = cursor.fetchone()[0]
    
    # Total runs
    cursor.execute('SELECT COUNT(*) FROM collection_history')
    total_runs = cursor.fetchone()[0]
    
    # Total tweets collected via batches
    cursor.execute('SELECT SUM(tweets_found) FROM keyword_batches')
    total_tweets = cursor.fetchone()[0] or 0
    
    # By batch
    cursor.execute('''
        SELECT batch_name, tweets_found, new_tweets, last_run_at 
        FROM keyword_batches 
        ORDER BY priority
    ''')
    by_batch = {row[0]: {"found": row[1], "new": row[2], "last_run": row[3]} for row in cursor.fetchall()}
    
    # Recent runs
    cursor.execute('''
        SELECT batch_name, run_at, tweets_found, new_tweets, stopped_reason
        FROM collection_history
        ORDER BY run_at DESC LIMIT 10
    ''')
    recent_runs = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "total_batches": total_batches,
        "total_runs": total_runs,
        "total_tweets_collected": total_tweets,
        "by_batch": by_batch,
        "recent_runs": recent_runs
    }
