# users/database.py
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
DB_PATH = os.path.join(DB_DIR, 'users.db') if DB_DIR != '.' else 'users.db'


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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # User tweets table - all fields from API response
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_tweets (
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
            
            -- Author fields (complete)
            author_type TEXT,
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
            author_can_media_tag INTEGER DEFAULT 0,
            author_created_at TEXT,
            author_favourites_count INTEGER DEFAULT 0,
            author_has_custom_timelines INTEGER DEFAULT 0,
            author_is_translator INTEGER DEFAULT 0,
            author_media_count INTEGER DEFAULT 0,
            author_statuses_count INTEGER DEFAULT 0,
            author_withheld_in_countries TEXT,
            author_affiliates_highlighted_label TEXT,
            author_possibly_sensitive INTEGER DEFAULT 0,
            author_pinned_tweet_ids TEXT,
            author_is_automated INTEGER DEFAULT 0,
            author_automated_by TEXT,
            author_unavailable INTEGER DEFAULT 0,
            author_message TEXT,
            author_unavailable_reason TEXT,
            author_profile_bio_description TEXT,
            author_profile_bio_entities TEXT,
            
            -- Entities (JSON)
            entities_hashtags TEXT,
            entities_urls TEXT,
            entities_user_mentions TEXT,
            entities_symbols TEXT,
            
            -- Extended entities
            extended_entities_json TEXT,
            
            -- Card
            card_json TEXT,
            
            -- Place
            place_json TEXT,
            
            -- Related tweets
            quoted_tweet_id TEXT,
            quoted_tweet_json TEXT,
            retweeted_tweet_id TEXT,
            retweeted_tweet_json TEXT,
            
            -- Metadata
            captured_at TEXT DEFAULT CURRENT_TIMESTAMP,
            fetched_by_user_id TEXT,
            fetched_by_username TEXT,
            include_replies INTEGER DEFAULT 0,
            raw_json TEXT
        )
    ''')
    
    # Pagination state per user
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_fetch_state (
            user_identifier TEXT PRIMARY KEY,
            user_id TEXT,
            user_name TEXT,
            last_tweet_ids TEXT,
            last_run_at TEXT,
            total_captured INTEGER DEFAULT 0
        )
    ''')
    
    # Indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_tweets_author_id ON user_tweets(author_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_tweets_author_username ON user_tweets(author_username)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_tweets_created_at ON user_tweets(created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_tweets_fetched_by ON user_tweets(fetched_by_user_id)')
    
    conn.commit()
    conn.close()


def get_last_seen_ids(user_identifier: str) -> Set[str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT last_tweet_ids FROM user_fetch_state WHERE user_identifier = ?', (user_identifier,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row['last_tweet_ids']:
        return set(json.loads(row['last_tweet_ids']))
    return set()


def update_fetch_state(user_identifier: str, user_id: str, user_name: str, tweet_ids: List[str], total: int):
    conn = get_connection()
    cursor = conn.cursor()
    
    from config import LAST_IDS_TO_CHECK
    ids_to_save = tweet_ids[:LAST_IDS_TO_CHECK]
    last_run_at = datetime.now().isoformat()
    
    cursor.execute('''
        INSERT OR REPLACE INTO user_fetch_state (user_identifier, user_id, user_name, last_tweet_ids, last_run_at, total_captured)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_identifier, user_id, user_name, json.dumps(ids_to_save), last_run_at, total))
    
    conn.commit()
    conn.close()
    
    # === DUAL-WRITE: Sync to Supabase ===
    _sync_to_supabase("user_fetch_state", {
        "user_identifier": user_identifier,
        "user_id": user_id,
        "user_name": user_name,
        "last_tweet_ids": ids_to_save,
        "last_run_at": last_run_at,
        "total_captured": total
    })


def tweet_exists(tweet_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM user_tweets WHERE id = ?', (tweet_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def save_user_tweet(
    tweet_data: Dict[str, Any],
    fetched_by_user_id: str = "",
    fetched_by_username: str = "",
    include_replies: bool = False
) -> bool:
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
    
    # Extract entities
    hashtags = entities.get('hashtags', [])
    urls = entities.get('urls', [])
    user_mentions = entities.get('user_mentions', [])
    symbols = entities.get('symbols', [])
    
    # Handle quoted/retweeted
    quoted_tweet = tweet_data.get('quoted_tweet')
    retweeted_tweet = tweet_data.get('retweeted_tweet')
    
    cursor.execute('''
        INSERT OR IGNORE INTO user_tweets (
            id, type, url, twitter_url, text, source,
            retweet_count, reply_count, like_count, quote_count, view_count,
            created_at, lang, bookmark_count, is_reply,
            in_reply_to_id, conversation_id, display_text_range,
            in_reply_to_user_id, in_reply_to_username, is_limited_reply,
            author_type, author_id, author_username, author_name,
            author_url, author_twitter_url,
            author_is_verified, author_is_blue_verified, author_verified_type,
            author_profile_picture, author_cover_picture, author_description,
            author_location, author_followers, author_following,
            author_can_dm, author_can_media_tag, author_created_at,
            author_favourites_count, author_has_custom_timelines, author_is_translator,
            author_media_count, author_statuses_count,
            author_withheld_in_countries, author_affiliates_highlighted_label,
            author_possibly_sensitive, author_pinned_tweet_ids,
            author_is_automated, author_automated_by,
            author_unavailable, author_message, author_unavailable_reason,
            author_profile_bio_description, author_profile_bio_entities,
            entities_hashtags, entities_urls, entities_user_mentions, entities_symbols,
            extended_entities_json, card_json, place_json,
            quoted_tweet_id, quoted_tweet_json,
            retweeted_tweet_id, retweeted_tweet_json,
            fetched_by_user_id, fetched_by_username, include_replies, raw_json
        ) VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?,
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
        author.get('type'),
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
        1 if author.get('canMediaTag') else 0,
        author.get('createdAt'),
        author.get('favouritesCount', 0),
        1 if author.get('hasCustomTimelines') else 0,
        1 if author.get('isTranslator') else 0,
        author.get('mediaCount', 0),
        author.get('statusesCount', 0),
        json.dumps(author.get('withheldInCountries', [])),
        json.dumps(author.get('affiliatesHighlightedLabel', {})),
        1 if author.get('possiblySensitive') else 0,
        json.dumps(author.get('pinnedTweetIds', [])),
        1 if author.get('isAutomated') else 0,
        author.get('automatedBy'),
        1 if author.get('unavailable') else 0,
        author.get('message'),
        author.get('unavailableReason'),
        profile_bio.get('description'),
        json.dumps(profile_bio.get('entities', {})),
        json.dumps(hashtags),
        json.dumps(urls),
        json.dumps(user_mentions),
        json.dumps(symbols),
        json.dumps(extended_entities) if extended_entities else None,
        json.dumps(card) if card else None,
        json.dumps(place) if place else None,
        quoted_tweet.get('id') if quoted_tweet else None,
        json.dumps(quoted_tweet) if quoted_tweet else None,
        retweeted_tweet.get('id') if retweeted_tweet else None,
        json.dumps(retweeted_tweet) if retweeted_tweet else None,
        fetched_by_user_id,
        fetched_by_username,
        1 if include_replies else 0,
        json.dumps(tweet_data)
    ))
    
    conn.commit()
    conn.close()
    
    # === DUAL-WRITE: Sync to Supabase ===
    quoted_tweet = tweet_data.get('quoted_tweet')
    retweeted_tweet = tweet_data.get('retweeted_tweet')
    
    _sync_to_supabase("user_tweets", {
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
        "author_type": author.get('type'),
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
        "author_can_media_tag": bool(author.get('canMediaTag')),
        "author_created_at": author.get('createdAt'),
        "author_favourites_count": author.get('favouritesCount', 0),
        "author_has_custom_timelines": bool(author.get('hasCustomTimelines')),
        "author_is_translator": bool(author.get('isTranslator')),
        "author_media_count": author.get('mediaCount', 0),
        "author_statuses_count": author.get('statusesCount', 0),
        "author_withheld_in_countries": author.get('withheldInCountries', []),
        "author_affiliates_highlighted_label": author.get('affiliatesHighlightedLabel', {}),
        "author_possibly_sensitive": bool(author.get('possiblySensitive')),
        "author_pinned_tweet_ids": author.get('pinnedTweetIds', []),
        "author_is_automated": bool(author.get('isAutomated')),
        "author_automated_by": author.get('automatedBy'),
        "author_unavailable": bool(author.get('unavailable')),
        "author_message": author.get('message'),
        "author_unavailable_reason": author.get('unavailableReason'),
        "author_profile_bio_description": profile_bio.get('description'),
        "author_profile_bio_entities": profile_bio.get('entities', {}),
        "entities_hashtags": hashtags,
        "entities_urls": urls,
        "entities_user_mentions": user_mentions,
        "entities_symbols": symbols,
        "extended_entities_json": extended_entities if extended_entities else None,
        "card_json": card if card else None,
        "place_json": place if place else None,
        "quoted_tweet_id": quoted_tweet.get('id') if quoted_tweet else None,
        "quoted_tweet_json": quoted_tweet,
        "retweeted_tweet_id": retweeted_tweet.get('id') if retweeted_tweet else None,
        "retweeted_tweet_json": retweeted_tweet,
        "fetched_by_user_id": fetched_by_user_id,
        "fetched_by_username": fetched_by_username,
        "include_replies": include_replies,
        "captured_at": datetime.now().isoformat(),
        "raw_json": tweet_data
    })
    
    return True


def get_user_tweets(user_identifier: str, limit: int = 100) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM user_tweets 
        WHERE author_id = ? OR author_username = ? OR fetched_by_user_id = ? OR fetched_by_username = ?
        ORDER BY created_at DESC LIMIT ?
    ''', (user_identifier, user_identifier, user_identifier, user_identifier, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_user_tweet_count(user_identifier: str = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    
    if user_identifier:
        cursor.execute('''
            SELECT COUNT(*) as count FROM user_tweets 
            WHERE author_id = ? OR author_username = ?
        ''', (user_identifier, user_identifier))
    else:
        cursor.execute('SELECT COUNT(*) as count FROM user_tweets')
    
    count = cursor.fetchone()['count']
    conn.close()
    return count


def search_user_tweets(keyword: str, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM user_tweets WHERE text LIKE ? ORDER BY created_at DESC LIMIT ?',
        (f'%{keyword}%', limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

