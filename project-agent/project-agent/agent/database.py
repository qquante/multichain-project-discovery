# agent/database.py
import os
import sys
import sqlite3
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Support Docker environment variable for DB path
DB_DIR = os.environ.get('DB_PATH', '.')
DB_PATH = os.path.join(DB_DIR, 'agent.db') if DB_DIR != '.' else 'agent.db'
TWEETS_DB_PATH = os.path.join(DB_DIR, 'tweets.db') if DB_DIR != '.' else 'tweets.db'


# Supabase sync (import lazily to avoid circular imports)
def _sync_to_supabase(table: str, data: dict, upsert: bool = True) -> bool:
    """Sync data to Supabase (non-blocking, fails silently)."""
    try:
        from db.supabase_client import sync_to_supabase
        return sync_to_supabase(table, data, upsert)
    except Exception as e:
        # Silent fail - don't break local operations
        return False


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    # Apply sane defaults to reduce lock contention
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
    except Exception:
        pass
    return conn


def _run_migrations(conn, cur):
    """Add missing columns to existing tables (safe migrations)."""
    
    # Get existing columns in verified_projects
    try:
        cur.execute("PRAGMA table_info(verified_projects)")
        existing_cols = {row[1] for row in cur.fetchall()}
        
        # Add discovery_source if missing
        if 'discovery_source' not in existing_cols:
            cur.execute('ALTER TABLE verified_projects ADD COLUMN discovery_source TEXT')
            print("[MIGRATION] Added discovery_source to verified_projects")
        
        # Add discovery_keyword if missing  
        if 'discovery_keyword' not in existing_cols:
            cur.execute('ALTER TABLE verified_projects ADD COLUMN discovery_keyword TEXT')
            print("[MIGRATION] Added discovery_keyword to verified_projects")
            
        conn.commit()
    except Exception as e:
        # Table might not exist yet - that's ok
        pass
    
    # Get existing columns in triaged_projects
    try:
        cur.execute("PRAGMA table_info(triaged_projects)")
        existing_cols = {row[1] for row in cur.fetchall()}
        
        if 'discovery_source' not in existing_cols:
            cur.execute('ALTER TABLE triaged_projects ADD COLUMN discovery_source TEXT')
            print("[MIGRATION] Added discovery_source to triaged_projects")
        
        if 'discovery_keyword' not in existing_cols:
            cur.execute('ALTER TABLE triaged_projects ADD COLUMN discovery_keyword TEXT')
            print("[MIGRATION] Added discovery_keyword to triaged_projects")
            
        conn.commit()
    except Exception as e:
        pass


def init_db():
    """Initialize agent database with control tables."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Run migrations for existing tables (add missing columns)
    _run_migrations(conn, cur)
    
    # Processed tweets - tracks which tweets have been analyzed
    cur.execute('''
        CREATE TABLE IF NOT EXISTS processed_tweets (
            tweet_id TEXT PRIMARY KEY,
            processed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_project INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0,
            rejection_reason TEXT,
            raw_response TEXT
        )
    ''')
    
    # Triaged projects - unique projects identified (by twitter_handle)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS triaged_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            twitter_handle TEXT UNIQUE,
            author_id TEXT,
            author_followers INTEGER DEFAULT 0,
            
            -- Project info
            project_name TEXT,
            project_ticker TEXT,
            project_type TEXT,
            project_chain TEXT,
            has_ca INTEGER DEFAULT 0,
            ca_address TEXT,
            
            -- Launch info
            launch_status TEXT,
            launch_date TEXT,
            launch_time TEXT,
            launch_platform TEXT,
            
            -- Source
            source_tweet_id TEXT,
            tweet_date TEXT,
            tweet_text_preview TEXT,
            
            -- Discovery source (alphagate/collector)
            discovery_source TEXT,
            discovery_keyword TEXT,
            
            -- Mentions
            tagged_accounts TEXT,
            tagged_chains TEXT,
            tagged_platforms TEXT,
            
            -- Signals
            keywords_found TEXT,
            has_links INTEGER DEFAULT 0,
            links TEXT,
            has_telegram INTEGER DEFAULT 0,
            telegram_link TEXT,
            has_website INTEGER DEFAULT 0,
            website_link TEXT,
            
            -- Metadata
            confidence REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            raw_response TEXT
        )
    ''')
    
    # Verified projects - Stage 2 results
    cur.execute('''
        CREATE TABLE IF NOT EXISTS verified_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            twitter_handle TEXT UNIQUE,
            author_id TEXT,
            
            -- Verification result
            verification_status TEXT,
            verification_confidence REAL DEFAULT 0,
            rejection_reason TEXT,
            
            -- Project info (from Stage 1)
            project_name TEXT,
            project_ticker TEXT,
            project_type TEXT,
            project_chain TEXT,
            launch_platform TEXT,
            
            -- User profile analysis
            bio TEXT,
            bio_has_crypto_keywords INTEGER DEFAULT 0,
            bio_mentions_project INTEGER DEFAULT 0,
            has_website INTEGER DEFAULT 0,
            website_url TEXT,
            has_telegram INTEGER DEFAULT 0,
            telegram_url TEXT,
            has_discord INTEGER DEFAULT 0,
            discord_url TEXT,
            followers INTEGER DEFAULT 0,
            following INTEGER DEFAULT 0,
            account_created_at TEXT,
            account_age_days INTEGER DEFAULT 0,
            total_tweets INTEGER DEFAULT 0,
            media_count INTEGER DEFAULT 0,
            is_blue_verified INTEGER DEFAULT 0,
            pinned_tweet_ids TEXT,
            
            -- Tweet analysis
            tweets_analyzed INTEGER DEFAULT 0,
            crypto_related_count INTEGER DEFAULT 0,
            project_mention_count INTEGER DEFAULT 0,
            launch_announcement_count INTEGER DEFAULT 0,
            spam_score REAL DEFAULT 0,
            
            -- Verification signals
            consistent_project_messaging INTEGER DEFAULT 0,
            has_pinned_tweet_about_project INTEGER DEFAULT 0,
            multiple_launch_announcements INTEGER DEFAULT 0,
            bio_matches_tweets INTEGER DEFAULT 0,
            
            -- Source
            source_tweet_id TEXT,
            triage_id INTEGER,
            
            -- Discovery source (alphagate/collector)
            discovery_source TEXT,
            discovery_keyword TEXT,
            
            -- Website analysis
            site_url TEXT,
            site_accessible INTEGER DEFAULT 0,
            site_title TEXT,
            site_description TEXT,
            site_content_preview TEXT,
            site_has_whitepaper INTEGER DEFAULT 0,
            site_has_tokenomics INTEGER DEFAULT 0,
            site_has_roadmap INTEGER DEFAULT 0,
            site_has_team INTEGER DEFAULT 0,
            site_has_audit INTEGER DEFAULT 0,
            site_social_links TEXT,
            site_contract_found INTEGER DEFAULT 0,
            site_contract_address TEXT,
            site_analysis TEXT,
            site_checked_at TEXT,
            site_raw_content TEXT,
            
            -- AlphaGate enrichment data
            found_in_alphagate INTEGER DEFAULT 0,
            key_followers_count INTEGER DEFAULT 0,
            key_followers TEXT,
            alpha_hunters_count INTEGER DEFAULT 0,
            alpha_hunters TEXT,
            followers_when_found INTEGER DEFAULT 0,
            best_hunter_winrate REAL DEFAULT 0,
            alphagate_alerts TEXT,
            
            -- Monitoring (Stage 3)
            monitoring_status TEXT DEFAULT 'pending',
            last_monitored_at TEXT,
            monitor_count INTEGER DEFAULT 0,
            launch_urgency TEXT DEFAULT 'unknown',
            launch_date_announced TEXT,
            launch_date_detected_at TEXT,
            hours_until_launch INTEGER,
            priority TEXT DEFAULT 'low',
            ca_detected_at TEXT,
            ca_address TEXT,
            launch_detected_at TEXT,
            followers_initial INTEGER DEFAULT 0,
            followers_current INTEGER DEFAULT 0,
            followers_growth REAL DEFAULT 0,
            activity_score REAL DEFAULT 0,
            last_tweet_at TEXT,
            inactive_days INTEGER DEFAULT 0,
            
            -- Metadata
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            raw_user_info TEXT,
            raw_tweets_analyzed TEXT,
            raw_verification_response TEXT,
            
            FOREIGN KEY (triage_id) REFERENCES triaged_projects(id)
        )
    ''')
    
    # Monitoring history - Stage 3 tracking
    cur.execute('''
        CREATE TABLE IF NOT EXISTS monitoring_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            twitter_handle TEXT,
            monitored_at TEXT DEFAULT CURRENT_TIMESTAMP,
            
            -- Snapshot data
            followers INTEGER DEFAULT 0,
            followers_change INTEGER DEFAULT 0,
            new_tweets_count INTEGER DEFAULT 0,
            last_tweet_text TEXT,
            last_tweet_at TEXT,
            
            -- CA detection
            ca_mentioned INTEGER DEFAULT 0,
            ca_address TEXT,
            ca_source TEXT,
            
            -- Launch detection
            launch_mentioned INTEGER DEFAULT 0,
            launch_urgency TEXT,
            launch_date_detected TEXT,
            
            -- Site status
            site_accessible INTEGER DEFAULT 0,
            site_changed INTEGER DEFAULT 0,
            site_ca_found INTEGER DEFAULT 0,
            
            -- Profile changes
            bio_changed INTEGER DEFAULT 0,
            bio_new TEXT,
            pinned_changed INTEGER DEFAULT 0,
            pinned_new TEXT,
            
            -- Status
            status_before TEXT,
            status_after TEXT,
            priority_before TEXT,
            priority_after TEXT,
            
            -- Analysis
            changes_detected TEXT,
            ai_analysis TEXT,
            raw_response TEXT,
            
            -- AlphaGate data (added for tracking)
            found_in_alphagate INTEGER DEFAULT 0,
            key_followers_count INTEGER DEFAULT 0,
            key_followers TEXT,
            alpha_hunters_count INTEGER DEFAULT 0,
            alpha_hunters TEXT,
            followers_when_found INTEGER DEFAULT 0,
            best_hunter_winrate REAL DEFAULT 0.0,
            alphagate_alerts TEXT,
            alphagate_bio_changes INTEGER DEFAULT 0,
            alphagate_username_changes INTEGER DEFAULT 0,
            
            FOREIGN KEY (project_id) REFERENCES verified_projects(id)
        )
    ''')
    
    # Verification queue - tracks what needs to be verified
    cur.execute('''
        CREATE TABLE IF NOT EXISTS verification_queue (
            triage_id INTEGER PRIMARY KEY,
            twitter_handle TEXT,
            author_id TEXT,
            status TEXT DEFAULT 'pending',
            attempts INTEGER DEFAULT 0,
            last_attempt_at TEXT,
            error_message TEXT,
            FOREIGN KEY (triage_id) REFERENCES triaged_projects(id)
        )
    ''')
    
    # Decision fingerprints - audit trail for all AI decisions
    cur.execute('''
        CREATE TABLE IF NOT EXISTS decision_fingerprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            
            -- Identity
            twitter_handle TEXT NOT NULL,
            tweet_id TEXT,
            author_id TEXT,
            
            -- Stage info
            stage INTEGER NOT NULL,
            stage_name TEXT NOT NULL,
            
            -- Decision
            decision TEXT NOT NULL,
            confidence REAL DEFAULT 0,
            reason TEXT,
            
            -- Input summary
            input_type TEXT,
            input_summary TEXT,
            input_tweet_text TEXT,
            input_bio TEXT,
            input_followers INTEGER,
            input_tweets_count INTEGER,
            input_site_url TEXT,
            
            -- AI Analysis
            llm_reasoning TEXT,
            key_factors TEXT,
            
            -- Detected data
            project_name TEXT,
            project_chain TEXT,
            project_type TEXT,
            ca_detected INTEGER DEFAULT 0,
            ca_address TEXT,
            launch_urgency TEXT,
            launch_date TEXT,
            
            -- Raw data for debugging
            raw_input TEXT,
            raw_output TEXT,
            
            -- Metadata
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            model_used TEXT,
            tokens_used INTEGER,
            processing_time REAL
        )
    ''')
    
    # Mentions table - for tweets from influencers about projects
    cur.execute('''
        CREATE TABLE IF NOT EXISTS mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            
            -- Source (who posted - the influencer/shill)
            source_tweet_id TEXT NOT NULL,
            source_author_handle TEXT NOT NULL,
            source_author_id TEXT,
            source_author_followers INTEGER DEFAULT 0,
            source_tweet_text TEXT,
            source_tweet_date TEXT,
            
            -- Project mentioned (the REAL project handle)
            mentioned_handle TEXT,
            mentioned_handles_found TEXT,
            
            -- Info extracted about the project
            project_name_extracted TEXT,
            project_ticker_extracted TEXT,
            project_chain_extracted TEXT,
            project_type_extracted TEXT,
            
            -- Name/Ticker possibilities
            name_possibilities TEXT,
            ticker_possibilities TEXT,
            
            -- Launch info extracted
            launch_date_mentioned TEXT,
            launch_platform_mentioned TEXT,
            ca_mentioned TEXT,
            
            -- Classification
            mention_type TEXT,
            author_type TEXT,
            confidence REAL DEFAULT 0,
            
            -- Control
            investigated INTEGER DEFAULT 0,
            converted_to_project INTEGER DEFAULT 0,
            converted_project_id INTEGER,
            
            -- Metadata
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            raw_response TEXT,
            
            UNIQUE(source_tweet_id, mentioned_handle)
        )
    ''')
    
    # Favorites table (who liked a project)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS project_favorites (
            twitter_handle TEXT NOT NULL,
            user_id TEXT NOT NULL,
            username TEXT,
            chat_id TEXT,
            first_liked_at TEXT NOT NULL,
            PRIMARY KEY (twitter_handle, user_id)
        )
    ''')

    # Manual add state for /add command
    cur.execute('''
        CREATE TABLE IF NOT EXISTS add_requests (
            chat_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            step TEXT NOT NULL,
            twitter_handle TEXT,
            summary TEXT,
            monitor_level TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, user_id)
        )
    ''')

    # Indexes
    cur.execute('CREATE INDEX IF NOT EXISTS idx_processed_tweet_id ON processed_tweets(tweet_id)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_triaged_handle ON triaged_projects(twitter_handle)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_triaged_chain ON triaged_projects(project_chain)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_triaged_status ON triaged_projects(launch_status)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_verified_handle ON verified_projects(twitter_handle)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_verified_status ON verified_projects(verification_status)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_verified_monitoring ON verified_projects(monitoring_status)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_verified_priority ON verified_projects(priority)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_verified_last_monitored ON verified_projects(last_monitored_at)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_queue_status ON verification_queue(status)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_monitoring_project ON monitoring_history(project_id)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_monitoring_handle ON monitoring_history(twitter_handle)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_fingerprint_handle ON decision_fingerprints(twitter_handle)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_fingerprint_stage ON decision_fingerprints(stage)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_fingerprint_decision ON decision_fingerprints(decision)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_mentions_handle ON mentions(mentioned_handle)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_mentions_source ON mentions(source_author_handle)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_mentions_investigated ON mentions(investigated)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_mentions_converted ON mentions(converted_to_project)')
    
    # Launch calendar table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS launch_calendar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            twitter_handle TEXT NOT NULL UNIQUE,
            project_name TEXT,
            project_ticker TEXT,
            ticker_possibilities TEXT,
            chain TEXT NOT NULL DEFAULT 'unknown',
            launch_date TEXT,
            launch_time TEXT,
            launch_date_raw TEXT,
            launch_date_source TEXT,
            launch_date_confidence REAL DEFAULT 0.5,
            launch_urgency TEXT DEFAULT 'unknown',
            days_until_launch INTEGER,
            launch_platform TEXT,
            calendar_status TEXT DEFAULT 'pending',
            ca_address TEXT,
            alert_7d_sent INTEGER DEFAULT 0,
            alert_24h_sent INTEGER DEFAULT 0,
            alert_today_sent INTEGER DEFAULT 0,
            alert_imminent_sent INTEGER DEFAULT 0,
            last_analyzed_at TEXT,
            analysis_notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_calendar_date ON launch_calendar(launch_date)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_calendar_chain ON launch_calendar(chain)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_calendar_urgency ON launch_calendar(launch_urgency)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_calendar_status ON launch_calendar(calendar_status)')
    
    conn.commit()
    conn.close()


def is_tweet_processed(tweet_id: str) -> bool:
    """Check if tweet has already been processed."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT 1 FROM processed_tweets WHERE tweet_id = ?', (tweet_id,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def is_handle_triaged(twitter_handle: str) -> bool:
    """Check if twitter handle is already in triage."""
    conn = get_connection()
    cur = conn.cursor()
    # Normalize handle
    handle = twitter_handle.lstrip('@').lower()
    cur.execute('SELECT 1 FROM triaged_projects WHERE LOWER(twitter_handle) = ?', (handle,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def mark_tweet_processed(
    tweet_id: str,
    is_project: bool,
    confidence: float,
    rejection_reason: Optional[str],
    raw_response: str
):
    """Mark tweet as processed."""
    conn = get_connection()
    cur = conn.cursor()
    processed_at = datetime.now().isoformat()
    cur.execute('''
        INSERT OR REPLACE INTO processed_tweets 
        (tweet_id, processed_at, is_project, confidence, rejection_reason, raw_response)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        tweet_id,
        processed_at,
        1 if is_project else 0,
        confidence,
        rejection_reason,
        raw_response
    ))
    conn.commit()
    conn.close()
    
    # === DUAL-WRITE: Sync to Supabase ===
    _sync_to_supabase("processed_tweets", {
        "tweet_id": tweet_id,
        "processed_at": processed_at,
        "is_project": is_project,
        "confidence": confidence,
        "rejection_reason": rejection_reason,
        "raw_response": raw_response
    })


def save_triage_result(result: Dict[str, Any]) -> bool:
    """Save triaged project to database. Returns True if saved, False if duplicate."""
    
    twitter_handle = (result.get('source', {}).get('twitter_handle') or '').lstrip('@')
    
    if not twitter_handle:
        return False
    
    if is_handle_triaged(twitter_handle):
        return False
    
    conn = get_connection()
    cur = conn.cursor()
    
    project = result.get('project', {}) or {}
    launch = result.get('launch', {}) or {}
    source = result.get('source', {}) or {}
    mentions = result.get('mentions', {}) or {}
    signals = result.get('signals', {}) or {}
    
    created_at = datetime.now().isoformat()
    
    cur.execute('''
        INSERT INTO triaged_projects (
            twitter_handle, author_id, author_followers,
            project_name, project_ticker, project_type, project_chain, has_ca, ca_address,
            launch_status, launch_date, launch_time, launch_platform,
            source_tweet_id, tweet_date, tweet_text_preview,
            discovery_source, discovery_keyword,
            tagged_accounts, tagged_chains, tagged_platforms,
            keywords_found, has_links, links, has_telegram, telegram_link, has_website, website_link,
            confidence, raw_response
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        twitter_handle,
        source.get('author_id'),
        source.get('author_followers', 0),
        project.get('name'),
        project.get('ticker'),
        project.get('type'),
        project.get('chain'),
        1 if project.get('has_ca') else 0,
        project.get('ca_address'),
        launch.get('status'),
        launch.get('date'),
        launch.get('time'),
        launch.get('platform'),
        source.get('tweet_id'),
        source.get('tweet_date'),
        source.get('tweet_text_preview'),
        result.get('discovery_source', 'collector'),
        result.get('discovery_keyword'),
        json.dumps(mentions.get('tagged_accounts', [])),
        json.dumps(mentions.get('tagged_chains', [])),
        json.dumps(mentions.get('tagged_platforms', [])),
        json.dumps(signals.get('keywords_found', [])),
        1 if signals.get('has_links') else 0,
        json.dumps(signals.get('links', [])),
        1 if signals.get('has_telegram') else 0,
        signals.get('telegram_link'),
        1 if signals.get('has_website') else 0,
        signals.get('website_link'),
        result.get('confidence', 0),
        json.dumps(result)
    ))
    
    conn.commit()
    conn.close()
    
    # === DUAL-WRITE: Sync to Supabase ===
    _sync_to_supabase("triaged_projects", {
        "twitter_handle": twitter_handle,
        "author_id": source.get('author_id'),
        "author_followers": source.get('author_followers', 0),
        "project_name": project.get('name'),
        "project_ticker": project.get('ticker'),
        "project_type": project.get('type'),
        "project_chain": project.get('chain'),
        "has_ca": bool(project.get('has_ca')),
        "ca_address": project.get('ca_address'),
        "launch_status": launch.get('status'),
        "launch_date": launch.get('date'),
        "launch_time": launch.get('time'),
        "launch_platform": launch.get('platform'),
        "source_tweet_id": source.get('tweet_id'),
        "tweet_date": source.get('tweet_date'),
        "tweet_text_preview": source.get('tweet_text_preview'),
        "discovery_source": result.get('discovery_source', 'collector'),
        "discovery_keyword": result.get('discovery_keyword'),
        "tagged_accounts": mentions.get('tagged_accounts', []),
        "tagged_chains": mentions.get('tagged_chains', []),
        "tagged_platforms": mentions.get('tagged_platforms', []),
        "keywords_found": signals.get('keywords_found', []),
        "has_links": bool(signals.get('has_links')),
        "links": signals.get('links', []),
        "has_telegram": bool(signals.get('has_telegram')),
        "telegram_link": signals.get('telegram_link'),
        "has_website": bool(signals.get('has_website')),
        "website_link": signals.get('website_link'),
        "confidence": result.get('confidence', 0),
        "created_at": created_at,
        "updated_at": created_at,
        "raw_response": result
    })
    
    return True


# ============================================
# Favorites and manual add helpers
# ============================================

def add_project_favorite(twitter_handle: str, user_id: str, username: str = "", chat_id: str = "") -> bool:
    """Save a favorite entry; returns True if inserted, False if already exists."""
    if not twitter_handle or not user_id:
        return False
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            '''
            INSERT OR IGNORE INTO project_favorites
            (twitter_handle, user_id, username, chat_id, first_liked_at)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (twitter_handle.lstrip('@'), user_id, username, chat_id, datetime.now().isoformat())
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_project_favorites(twitter_handle: str) -> List[Dict[str, Any]]:
    """Return all favorites for a handle."""
    if not twitter_handle:
        return []
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        '''
        SELECT user_id, username, chat_id, first_liked_at
        FROM project_favorites
        WHERE LOWER(twitter_handle) = LOWER(?)
        ORDER BY first_liked_at DESC
        ''',
        (twitter_handle.lstrip('@'),)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_favorited_handles() -> List[str]:
    """Return all unique twitter handles that have been favorited by anyone."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT twitter_handle FROM project_favorites')
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows if row[0]]


def get_favorites_with_chain() -> List[Dict[str, Any]]:
    """Return favorited handles with chain info from launch_calendar (for calendar alerts)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT DISTINCT 
            pf.twitter_handle,
            lc.chain,
            lc.project_name,
            lc.project_ticker
        FROM project_favorites pf
        LEFT JOIN launch_calendar lc ON LOWER(pf.twitter_handle) = LOWER(lc.twitter_handle)
        WHERE lc.calendar_status NOT IN ('launched', 'cancelled') OR lc.twitter_handle IS NULL
    ''')
    rows = cur.fetchall()
    conn.close()
    return [
        {
            'twitter_handle': row[0],
            'chain': row[1] or 'unknown',
            'project_name': row[2],
            'project_ticker': row[3]
        }
        for row in rows if row[0]
    ]


def upsert_add_request(chat_id: str, user_id: str, step: str, twitter_handle: str = None, summary: str = None, monitor_level: str = None):
    """Store state for /add flow."""
    if not chat_id or not user_id:
        return
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        '''
        INSERT OR REPLACE INTO add_requests
        (chat_id, user_id, step, twitter_handle, summary, monitor_level, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''',
        (chat_id, user_id, step, twitter_handle, summary, monitor_level, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_add_request(chat_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    if not chat_id or not user_id:
        return None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        'SELECT * FROM add_requests WHERE chat_id = ? AND user_id = ?',
        (chat_id, user_id)
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def clear_add_request(chat_id: str, user_id: str):
    if not chat_id or not user_id:
        return
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        'DELETE FROM add_requests WHERE chat_id = ? AND user_id = ?',
        (chat_id, user_id)
    )
    conn.commit()
    conn.close()


def stop_monitoring_by_handle(twitter_handle: str) -> bool:
    """Mark project as removed from monitoring by handle.
    Also cancels it in launch_calendar so it won't appear in alerts.
    """
    if not twitter_handle:
        return False
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    handle = twitter_handle.lstrip('@')
    
    # 1. Mark as removed in verified_projects
    cur.execute(
        '''
        UPDATE verified_projects
        SET monitoring_status = 'removed', updated_at = ?
        WHERE LOWER(twitter_handle) = LOWER(?)
        ''',
        (now, handle)
    )
    changed_verified = cur.rowcount > 0
    
    # 2. Also cancel in launch_calendar (so it won't appear in alerts)
    cur.execute(
        '''
        UPDATE launch_calendar
        SET calendar_status = 'cancelled', updated_at = ?
        WHERE LOWER(twitter_handle) = LOWER(?)
        ''',
        (now, handle)
    )
    changed_calendar = cur.rowcount > 0
    
    conn.commit()
    conn.close()
    
    # Sync to Supabase
    if changed_calendar:
        _sync_to_supabase('launch_calendar', {
            'twitter_handle': handle,
            'calendar_status': 'cancelled',
            'updated_at': now
        })
    
    return changed_verified or changed_calendar


def get_pending_tweets(limit: int = 100) -> List[Dict[str, Any]]:
    """Get tweets from tweets.db that haven't been processed yet."""
    
    # Get processed tweet IDs
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT tweet_id FROM processed_tweets')
    processed_ids = set(row[0] for row in cur.fetchall())
    conn.close()
    
    # Get tweets from tweets.db
    tweets_conn = get_connection(TWEETS_DB_PATH)
    cur = tweets_conn.cursor()
    cur.execute('SELECT * FROM tweets ORDER BY captured_at DESC')
    rows = cur.fetchall()
    tweets_conn.close()
    
    # Filter unprocessed
    pending = []
    for row in rows:
        tweet = dict(row)
        if tweet['id'] not in processed_ids:
            pending.append(tweet)
            if len(pending) >= limit:
                break
    
    return pending


def get_triaged_projects(limit: int = 100) -> List[Dict[str, Any]]:
    """Get all triaged projects."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM triaged_projects ORDER BY created_at DESC LIMIT ?', (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_triage_stats() -> Dict[str, Any]:
    """Get statistics about triage."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT COUNT(*) FROM processed_tweets')
    total_processed = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM processed_tweets WHERE is_project = 1')
    total_projects = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM triaged_projects')
    total_triaged = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM triaged_projects WHERE has_ca = 0')
    pre_launch = cur.fetchone()[0]
    
    cur.execute('''
        SELECT project_chain, COUNT(*) as count 
        FROM triaged_projects 
        GROUP BY project_chain 
        ORDER BY count DESC
    ''')
    by_chain = {row[0]: row[1] for row in cur.fetchall()}
    
    conn.close()
    
    return {
        "total_processed": total_processed,
        "total_projects_found": total_projects,
        "total_triaged": total_triaged,
        "pre_launch_projects": pre_launch,
        "by_chain": by_chain
    }


# ============================================
# STAGE 2: Verification Functions
# ============================================

def get_pending_verifications(limit: int = 100) -> List[Dict[str, Any]]:
    """Get triaged projects that haven't been verified yet."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Get projects not in verified_projects
    cur.execute('''
        SELECT t.* FROM triaged_projects t
        LEFT JOIN verified_projects v ON LOWER(t.twitter_handle) = LOWER(v.twitter_handle)
        WHERE v.id IS NULL
        ORDER BY t.created_at DESC
        LIMIT ?
    ''', (limit,))
    
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def is_handle_verified(twitter_handle: str) -> bool:
    """Check if handle has been verified."""
    conn = get_connection()
    cur = conn.cursor()
    handle = twitter_handle.lstrip('@').lower()
    cur.execute('SELECT 1 FROM verified_projects WHERE LOWER(twitter_handle) = ?', (handle,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def save_verification_result(result: Dict[str, Any], triage_data: Dict[str, Any]) -> bool:
    """Save verification result to database."""
    
    twitter_handle = (result.get('twitter_handle') or '').lstrip('@')
    
    if not twitter_handle:
        return False
    
    if is_handle_verified(twitter_handle):
        return False
    
    conn = get_connection()
    cur = conn.cursor()
    
    user_profile = result.get('user_profile', {})
    tweet_analysis = result.get('tweet_analysis', {})
    signals = result.get('verification_signals', {})
    site_analysis = result.get('site_analysis', {})
    
    cur.execute('''
        INSERT INTO verified_projects (
            twitter_handle, author_id,
            verification_status, verification_confidence, rejection_reason,
            project_name, project_ticker, project_type, project_chain, launch_platform,
            bio, bio_has_crypto_keywords, bio_mentions_project,
            has_website, website_url, has_telegram, telegram_url, has_discord, discord_url,
            followers, following, account_created_at, account_age_days,
            total_tweets, media_count, is_blue_verified, pinned_tweet_ids,
            tweets_analyzed, crypto_related_count, project_mention_count,
            launch_announcement_count, spam_score,
            consistent_project_messaging, has_pinned_tweet_about_project,
            multiple_launch_announcements, bio_matches_tweets,
            source_tweet_id, triage_id,
            discovery_source, discovery_keyword,
            site_url, site_accessible, site_title, site_description, site_content_preview,
            site_has_whitepaper, site_has_tokenomics, site_has_roadmap, site_has_team, site_has_audit,
            site_social_links, site_contract_found, site_contract_address,
            site_analysis, site_checked_at, site_raw_content,
            found_in_alphagate, key_followers_count, key_followers,
            alpha_hunters_count, alpha_hunters, followers_when_found, best_hunter_winrate, alphagate_alerts,
            raw_user_info, raw_tweets_analyzed, raw_verification_response
        ) VALUES (
            ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?
        )
    ''', (
        twitter_handle,
        triage_data.get('author_id'),
        result.get('verification_status'),
        result.get('verification_confidence', 0),
        result.get('rejection_reason'),
        triage_data.get('project_name'),
        triage_data.get('project_ticker'),
        triage_data.get('project_type'),
        triage_data.get('project_chain'),
        triage_data.get('launch_platform'),
        user_profile.get('bio'),
        1 if user_profile.get('bio_has_crypto_keywords') else 0,
        1 if user_profile.get('bio_mentions_project') else 0,
        1 if user_profile.get('has_website') else 0,
        user_profile.get('website_url'),
        1 if user_profile.get('has_telegram') else 0,
        user_profile.get('telegram_url'),
        1 if user_profile.get('has_discord') else 0,
        user_profile.get('discord_url'),
        user_profile.get('followers', 0),
        user_profile.get('following', 0),
        user_profile.get('account_created_at'),
        user_profile.get('account_age_days', 0),
        user_profile.get('total_tweets', 0),
        user_profile.get('media_count', 0),
        1 if user_profile.get('is_blue_verified') else 0,
        json.dumps(user_profile.get('pinned_tweet_ids', [])),
        tweet_analysis.get('tweets_analyzed', 0),
        tweet_analysis.get('crypto_related_count', 0),
        tweet_analysis.get('project_mention_count', 0),
        tweet_analysis.get('launch_announcement_count', 0),
        tweet_analysis.get('spam_score', 0),
        1 if signals.get('consistent_project_messaging') else 0,
        1 if signals.get('has_pinned_tweet_about_project') else 0,
        1 if signals.get('multiple_launch_announcements') else 0,
        1 if signals.get('bio_matches_tweets') else 0,
        triage_data.get('source_tweet_id'),
        triage_data.get('id'),
        triage_data.get('discovery_source', 'collector'),
        triage_data.get('discovery_keyword'),
        site_analysis.get('url'),
        1 if site_analysis.get('accessible') else 0,
        site_analysis.get('title'),
        site_analysis.get('description'),
        site_analysis.get('content_preview'),
        1 if site_analysis.get('has_whitepaper') else 0,
        1 if site_analysis.get('has_tokenomics') else 0,
        1 if site_analysis.get('has_roadmap') else 0,
        1 if site_analysis.get('has_team') else 0,
        1 if site_analysis.get('has_audit') else 0,
        json.dumps(site_analysis.get('social_links', [])),
        1 if site_analysis.get('contract_found') else 0,
        site_analysis.get('contract_address'),
        site_analysis.get('analysis'),
        site_analysis.get('checked_at'),
        site_analysis.get('raw_content', '')[:5000] if site_analysis.get('raw_content') else None,
        # AlphaGate enrichment data
        1 if result.get('found_in_alphagate') else 0,
        result.get('key_followers_count', 0),
        json.dumps(result.get('key_followers', [])),
        result.get('alpha_hunters_count', 0),
        json.dumps(result.get('alpha_hunters', [])),
        result.get('followers_when_found', 0),
        result.get('best_hunter_winrate', 0.0),
        json.dumps(result.get('alphagate_data', {}).get('alerts', [])),
        # Raw data
        json.dumps(result.get('raw_user_info', {})),
        json.dumps(result.get('raw_tweets', [])),
        json.dumps(result)
    ))
    
    conn.commit()
    conn.close()
    
    # === DUAL-WRITE: Sync to Supabase ===
    created_at = datetime.now().isoformat()
    _sync_to_supabase("verified_projects", {
        "twitter_handle": twitter_handle,
        "author_id": triage_data.get('author_id'),
        "verification_status": result.get('verification_status'),
        "verification_confidence": result.get('verification_confidence', 0),
        "rejection_reason": result.get('rejection_reason'),
        "project_name": triage_data.get('project_name'),
        "project_ticker": triage_data.get('project_ticker'),
        "project_type": triage_data.get('project_type'),
        "project_chain": triage_data.get('project_chain'),
        "launch_platform": triage_data.get('launch_platform'),
        "bio": user_profile.get('bio'),
        "bio_has_crypto_keywords": bool(user_profile.get('bio_has_crypto_keywords')),
        "bio_mentions_project": bool(user_profile.get('bio_mentions_project')),
        "has_website": bool(user_profile.get('has_website')),
        "website_url": user_profile.get('website_url'),
        "has_telegram": bool(user_profile.get('has_telegram')),
        "telegram_url": user_profile.get('telegram_url'),
        "has_discord": bool(user_profile.get('has_discord')),
        "discord_url": user_profile.get('discord_url'),
        "followers": user_profile.get('followers', 0),
        "following": user_profile.get('following', 0),
        "account_created_at": user_profile.get('account_created_at'),
        "account_age_days": user_profile.get('account_age_days', 0),
        "total_tweets": user_profile.get('total_tweets', 0),
        "media_count": user_profile.get('media_count', 0),
        "is_blue_verified": bool(user_profile.get('is_blue_verified')),
        "pinned_tweet_ids": user_profile.get('pinned_tweet_ids', []),
        "tweets_analyzed": tweet_analysis.get('tweets_analyzed', 0),
        "crypto_related_count": tweet_analysis.get('crypto_related_count', 0),
        "project_mention_count": tweet_analysis.get('project_mention_count', 0),
        "launch_announcement_count": tweet_analysis.get('launch_announcement_count', 0),
        "spam_score": tweet_analysis.get('spam_score', 0),
        "consistent_project_messaging": bool(signals.get('consistent_project_messaging')),
        "has_pinned_tweet_about_project": bool(signals.get('has_pinned_tweet_about_project')),
        "multiple_launch_announcements": bool(signals.get('multiple_launch_announcements')),
        "bio_matches_tweets": bool(signals.get('bio_matches_tweets')),
        "source_tweet_id": triage_data.get('source_tweet_id'),
        "triage_id": triage_data.get('id'),
        "discovery_source": triage_data.get('discovery_source', 'collector'),
        "discovery_keyword": triage_data.get('discovery_keyword'),
        "site_url": site_analysis.get('url'),
        "site_accessible": bool(site_analysis.get('accessible')),
        "site_title": site_analysis.get('title'),
        "site_description": site_analysis.get('description'),
        "site_content_preview": site_analysis.get('content_preview'),
        "site_has_whitepaper": bool(site_analysis.get('has_whitepaper')),
        "site_has_tokenomics": bool(site_analysis.get('has_tokenomics')),
        "site_has_roadmap": bool(site_analysis.get('has_roadmap')),
        "site_has_team": bool(site_analysis.get('has_team')),
        "site_has_audit": bool(site_analysis.get('has_audit')),
        "site_social_links": site_analysis.get('social_links', []),
        "site_contract_found": bool(site_analysis.get('contract_found')),
        "site_contract_address": site_analysis.get('contract_address'),
        "site_analysis": site_analysis.get('analysis'),
        "site_checked_at": site_analysis.get('checked_at'),
        # AlphaGate enrichment
        "found_in_alphagate": bool(result.get('found_in_alphagate')),
        "key_followers_count": result.get('key_followers_count', 0),
        "key_followers": result.get('key_followers', []),
        "alpha_hunters_count": result.get('alpha_hunters_count', 0),
        "alpha_hunters": result.get('alpha_hunters', []),
        "followers_when_found": result.get('followers_when_found', 0),
        "best_hunter_winrate": result.get('best_hunter_winrate', 0.0),
        "alphagate_alerts": result.get('alphagate_data', {}).get('alerts', []),
        # Metadata
        "created_at": created_at,
        "updated_at": created_at,
        "raw_user_info": result.get('raw_user_info', {}),
        "raw_tweets_analyzed": result.get('raw_tweets', []),
        "raw_verification_response": result
    })
    
    return True


def get_verified_projects(status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Get verified projects, optionally filtered by status."""
    conn = get_connection()
    cur = conn.cursor()
    
    if status:
        cur.execute('''
            SELECT * FROM verified_projects 
            WHERE verification_status = ?
            ORDER BY created_at DESC LIMIT ?
        ''', (status, limit))
    else:
        cur.execute('SELECT * FROM verified_projects ORDER BY created_at DESC LIMIT ?', (limit,))
    
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_verification_stats() -> Dict[str, Any]:
    """Get verification statistics."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT COUNT(*) FROM triaged_projects')
    total_triaged = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM verified_projects')
    total_verified = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM verified_projects WHERE verification_status = 'confirmed'")
    confirmed = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM verified_projects WHERE verification_status = 'rejected'")
    rejected = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM verified_projects WHERE verification_status = 'pending'")
    pending = cur.fetchone()[0]
    
    cur.execute('''
        SELECT rejection_reason, COUNT(*) as count 
        FROM verified_projects 
        WHERE rejection_reason IS NOT NULL
        GROUP BY rejection_reason 
        ORDER BY count DESC
    ''')
    by_rejection = {row[0]: row[1] for row in cur.fetchall()}
    
    cur.execute('''
        SELECT project_chain, COUNT(*) as count 
        FROM verified_projects 
        WHERE verification_status = 'confirmed'
        GROUP BY project_chain 
        ORDER BY count DESC
    ''')
    confirmed_by_chain = {row[0]: row[1] for row in cur.fetchall()}
    
    conn.close()
    
    return {
        "total_triaged": total_triaged,
        "total_verified": total_verified,
        "pending_verification": total_triaged - total_verified,
        "confirmed": confirmed,
        "rejected": rejected,
        "pending": pending,
        "by_rejection_reason": by_rejection,
        "confirmed_by_chain": confirmed_by_chain
    }


# ============================================
# STAGE 3: Monitoring Functions
# ============================================

# Check intervals by priority (in hours)
MONITOR_INTERVALS = {
    "critical": 8,    # Launching soon
    "high": 12,       # This week
    "medium": 24,     # Scheduled date
    "low": 24         # Vague timeline
}


def get_projects_to_monitor(limit: int = 50) -> List[Dict[str, Any]]:
    """Get confirmed projects that need monitoring based on priority intervals."""
    conn = get_connection()
    cur = conn.cursor()
    
    now = datetime.now()
    projects = []
    
    # Get all confirmed projects with active monitoring
    cur.execute('''
        SELECT * FROM verified_projects 
        WHERE verification_status = 'confirmed'
        AND monitoring_status IN ('pending', 'active')
        ORDER BY 
            CASE priority 
                WHEN 'critical' THEN 1 
                WHEN 'high' THEN 2 
                WHEN 'medium' THEN 3 
                ELSE 4 
            END,
            last_monitored_at ASC NULLS FIRST
    ''')
    
    rows = cur.fetchall()
    conn.close()
    
    for row in rows:
        project = dict(row)
        priority = project.get('priority', 'low')
        interval_hours = MONITOR_INTERVALS.get(priority, 12)
        
        last_monitored = project.get('last_monitored_at')
        created_at = project.get('created_at')
        
        # Check if needs monitoring
        needs_check = False
        
        if not last_monitored:
            # First monitoring - use created_at as reference
            # Only monitor if enough time has passed since confirmation
            if created_at:
                try:
                    created_dt = datetime.fromisoformat(created_at)
                    hours_since_created = (now - created_dt).total_seconds() / 3600
                    if hours_since_created >= interval_hours:
                        needs_check = True
                    # else: not enough time since confirmation, skip
                except:
                    # If can't parse date, wait at least 8 hours
                    needs_check = False
            else:
                # No created_at, skip until next cycle
                needs_check = False
        else:
            # Regular monitoring - check interval since last monitor
            try:
                last_dt = datetime.fromisoformat(last_monitored)
                hours_since = (now - last_dt).total_seconds() / 3600
                if hours_since >= interval_hours:
                    needs_check = True
            except:
                needs_check = True
        
        if needs_check:
            projects.append(project)
            if len(projects) >= limit:
                break
    
    return projects


def update_project_monitoring(
    project_id: int,
    updates: Dict[str, Any]
) -> bool:
    """Update project monitoring fields."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Build dynamic update
    fields = []
    values = []
    
    allowed_fields = [
        'monitoring_status', 'last_monitored_at', 'monitor_count',
        'launch_urgency', 'launch_date_announced', 'launch_date_detected_at',
        'hours_until_launch', 'priority', 'ca_detected_at', 'ca_address',
        'launch_detected_at', 'followers_current', 'followers_growth',
        'activity_score', 'last_tweet_at', 'inactive_days', 'updated_at'
    ]
    
    for field in allowed_fields:
        if field in updates:
            fields.append(f'{field} = ?')
            values.append(updates[field])
    
    if not fields:
        conn.close()
        return False
    
    values.append(project_id)
    
    cur.execute(f'''
        UPDATE verified_projects 
        SET {', '.join(fields)}
        WHERE id = ?
    ''', values)
    
    conn.commit()
    
    # Get twitter_handle for Supabase update
    cur.execute('SELECT twitter_handle FROM verified_projects WHERE id = ?', (project_id,))
    row = cur.fetchone()
    twitter_handle = row[0] if row else None
    conn.close()
    
    # === DUAL-WRITE: Sync to Supabase ===
    if twitter_handle:
        # Convert booleans for Supabase
        supabase_updates = {}
        for field in allowed_fields:
            if field in updates:
                supabase_updates[field] = updates[field]
        supabase_updates['twitter_handle'] = twitter_handle
        _sync_to_supabase("verified_projects", supabase_updates)
    
    return True


def save_monitoring_history(
    project_id: int,
    twitter_handle: str,
    data: Dict[str, Any]
) -> int:
    """Save monitoring history entry with AlphaGate data."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        INSERT INTO monitoring_history (
            project_id, twitter_handle, monitored_at,
            followers, followers_change, new_tweets_count,
            last_tweet_text, last_tweet_at,
            ca_mentioned, ca_address, ca_source,
            launch_mentioned, launch_urgency, launch_date_detected,
            site_accessible, site_changed, site_ca_found,
            bio_changed, bio_new, pinned_changed, pinned_new,
            status_before, status_after, priority_before, priority_after,
            changes_detected, ai_analysis, raw_response,
            found_in_alphagate, key_followers_count, key_followers,
            alpha_hunters_count, alpha_hunters, followers_when_found,
            best_hunter_winrate, alphagate_alerts, alphagate_bio_changes,
            alphagate_username_changes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        project_id,
        twitter_handle,
        datetime.now().isoformat(),
        data.get('followers', 0),
        data.get('followers_change', 0),
        data.get('new_tweets_count', 0),
        data.get('last_tweet_text'),
        data.get('last_tweet_at'),
        1 if data.get('ca_mentioned') else 0,
        data.get('ca_address'),
        data.get('ca_source'),
        1 if data.get('launch_mentioned') else 0,
        data.get('launch_urgency'),
        data.get('launch_date_detected'),
        1 if data.get('site_accessible') else 0,
        1 if data.get('site_changed') else 0,
        1 if data.get('site_ca_found') else 0,
        1 if data.get('bio_changed') else 0,
        data.get('bio_new'),
        1 if data.get('pinned_changed') else 0,
        data.get('pinned_new'),
        data.get('status_before'),
        data.get('status_after'),
        data.get('priority_before'),
        data.get('priority_after'),
        json.dumps(data.get('changes_detected', [])),
        data.get('ai_analysis'),
        json.dumps(data.get('raw_response', {})),
        # AlphaGate data
        1 if data.get('found_in_alphagate') else 0,
        data.get('key_followers_count', 0),
        json.dumps(data.get('key_followers', [])),
        data.get('alpha_hunters_count', 0),
        json.dumps(data.get('alpha_hunters', [])),
        data.get('followers_when_found', 0),
        data.get('best_hunter_winrate', 0.0),
        json.dumps(data.get('alphagate_alerts', [])),
        data.get('alphagate_bio_changes', 0),
        data.get('alphagate_username_changes', 0)
    ))
    
    history_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    # === DUAL-WRITE: Sync to Supabase ===
    monitored_at = datetime.now().isoformat()
    _sync_to_supabase("monitoring_history", {
        "project_id": project_id,
        "twitter_handle": twitter_handle,
        "monitored_at": monitored_at,
        "followers": data.get('followers', 0),
        "followers_change": data.get('followers_change', 0),
        "new_tweets_count": data.get('new_tweets_count', 0),
        "last_tweet_text": data.get('last_tweet_text'),
        "last_tweet_at": data.get('last_tweet_at'),
        "ca_mentioned": bool(data.get('ca_mentioned')),
        "ca_address": data.get('ca_address'),
        "ca_source": data.get('ca_source'),
        "launch_mentioned": bool(data.get('launch_mentioned')),
        "launch_urgency": data.get('launch_urgency'),
        "launch_date_detected": data.get('launch_date_detected'),
        "site_accessible": bool(data.get('site_accessible')),
        "site_changed": bool(data.get('site_changed')),
        "site_ca_found": bool(data.get('site_ca_found')),
        "bio_changed": bool(data.get('bio_changed')),
        "bio_new": data.get('bio_new'),
        "pinned_changed": bool(data.get('pinned_changed')),
        "pinned_new": data.get('pinned_new'),
        "status_before": data.get('status_before'),
        "status_after": data.get('status_after'),
        "priority_before": data.get('priority_before'),
        "priority_after": data.get('priority_after'),
        "changes_detected": data.get('changes_detected', []),
        "ai_analysis": data.get('ai_analysis'),
        "raw_response": data.get('raw_response', {}),
        # AlphaGate data
        "found_in_alphagate": bool(data.get('found_in_alphagate')),
        "key_followers_count": data.get('key_followers_count', 0),
        "key_followers": data.get('key_followers', []),
        "alpha_hunters_count": data.get('alpha_hunters_count', 0),
        "alpha_hunters": data.get('alpha_hunters', []),
        "followers_when_found": data.get('followers_when_found', 0),
        "best_hunter_winrate": data.get('best_hunter_winrate', 0.0),
        "alphagate_alerts": data.get('alphagate_alerts', []),
        "alphagate_bio_changes": data.get('alphagate_bio_changes', 0),
        "alphagate_username_changes": data.get('alphagate_username_changes', 0)
    }, upsert=False)  # Insert only
    
    return history_id


def get_monitoring_history(
    twitter_handle: str = None,
    project_id: int = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Get monitoring history."""
    conn = get_connection()
    cur = conn.cursor()
    
    if twitter_handle:
        cur.execute('''
            SELECT * FROM monitoring_history 
            WHERE twitter_handle = ?
            ORDER BY monitored_at DESC LIMIT ?
        ''', (twitter_handle.lstrip('@'), limit))
    elif project_id:
        cur.execute('''
            SELECT * FROM monitoring_history 
            WHERE project_id = ?
            ORDER BY monitored_at DESC LIMIT ?
        ''', (project_id, limit))
    else:
        cur.execute('''
            SELECT * FROM monitoring_history 
            ORDER BY monitored_at DESC LIMIT ?
        ''', (limit,))
    
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_monitoring_stats() -> Dict[str, Any]:
    """Get monitoring statistics."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Projects by monitoring status
    cur.execute('''
        SELECT monitoring_status, COUNT(*) as count 
        FROM verified_projects 
        WHERE verification_status = 'confirmed'
        GROUP BY monitoring_status
    ''')
    by_status = {row[0] or 'pending': row[1] for row in cur.fetchall()}
    
    # Projects by priority
    cur.execute('''
        SELECT priority, COUNT(*) as count 
        FROM verified_projects 
        WHERE verification_status = 'confirmed'
        AND monitoring_status IN ('pending', 'active')
        GROUP BY priority
    ''')
    by_priority = {row[0] or 'low': row[1] for row in cur.fetchall()}
    
    # Total monitoring checks
    cur.execute('SELECT COUNT(*) FROM monitoring_history')
    total_checks = cur.fetchone()[0]
    
    # CA detected count
    cur.execute('''
        SELECT COUNT(*) FROM verified_projects 
        WHERE ca_address IS NOT NULL AND ca_address != ''
    ''')
    ca_detected = cur.fetchone()[0]
    
    # Launched count
    cur.execute('''
        SELECT COUNT(*) FROM verified_projects 
        WHERE monitoring_status = 'launched'
    ''')
    launched = cur.fetchone()[0]
    
    conn.close()
    
    return {
        "by_monitoring_status": by_status,
        "by_priority": by_priority,
        "total_monitoring_checks": total_checks,
        "ca_detected_count": ca_detected,
        "launched_count": launched
    }


def activate_monitoring_for_confirmed() -> int:
    """Activate monitoring for all confirmed projects that don't have it yet."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE verified_projects 
        SET monitoring_status = 'active',
            followers_initial = followers,
            followers_current = followers
        WHERE verification_status = 'confirmed'
        AND (monitoring_status IS NULL OR monitoring_status = 'pending')
    ''')
    
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


# ============================================
# FINGERPRINTS: Decision Audit Trail
# ============================================

def save_fingerprint(data: Dict[str, Any]) -> int:
    """Save a decision fingerprint for audit trail."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        INSERT INTO decision_fingerprints (
            twitter_handle, tweet_id, author_id,
            stage, stage_name, decision, confidence, reason,
            input_type, input_summary, input_tweet_text, input_bio,
            input_followers, input_tweets_count, input_site_url,
            llm_reasoning, key_factors,
            project_name, project_chain, project_type,
            ca_detected, ca_address, launch_urgency, launch_date,
            raw_input, raw_output,
            model_used, tokens_used, processing_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        (data.get('twitter_handle') or '').lstrip('@'),
        data.get('tweet_id'),
        data.get('author_id'),
        data.get('stage'),
        data.get('stage_name'),
        data.get('decision'),
        data.get('confidence', 0),
        data.get('reason'),
        data.get('input_type'),
        data.get('input_summary'),
        data.get('input_tweet_text'),
        data.get('input_bio'),
        data.get('input_followers'),
        data.get('input_tweets_count'),
        data.get('input_site_url'),
        data.get('llm_reasoning'),
        json.dumps(data.get('key_factors', {})),
        data.get('project_name'),
        data.get('project_chain'),
        data.get('project_type'),
        1 if data.get('ca_detected') else 0,
        data.get('ca_address'),
        data.get('launch_urgency'),
        data.get('launch_date'),
        json.dumps(data.get('raw_input', {})),
        json.dumps(data.get('raw_output', {})),
        data.get('model_used'),
        data.get('tokens_used'),
        data.get('processing_time')
    ))
    
    fingerprint_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    # === DUAL-WRITE: Sync to Supabase ===
    _sync_to_supabase("decision_fingerprints", {
        "twitter_handle": (data.get('twitter_handle') or '').lstrip('@'),
        "tweet_id": data.get('tweet_id'),
        "author_id": data.get('author_id'),
        "stage": data.get('stage'),
        "stage_name": data.get('stage_name'),
        "decision": data.get('decision'),
        "confidence": data.get('confidence', 0),
        "reason": data.get('reason'),
        "input_type": data.get('input_type'),
        "input_summary": data.get('input_summary'),
        "input_tweet_text": data.get('input_tweet_text'),
        "input_bio": data.get('input_bio'),
        "input_followers": data.get('input_followers'),
        "input_tweets_count": data.get('input_tweets_count'),
        "input_site_url": data.get('input_site_url'),
        "llm_reasoning": data.get('llm_reasoning'),
        "key_factors": data.get('key_factors', {}),
        "project_name": data.get('project_name'),
        "project_chain": data.get('project_chain'),
        "project_type": data.get('project_type'),
        "ca_detected": bool(data.get('ca_detected')),
        "ca_address": data.get('ca_address'),
        "launch_urgency": data.get('launch_urgency'),
        "launch_date": data.get('launch_date'),
        "raw_input": data.get('raw_input', {}),
        "raw_output": data.get('raw_output', {}),
        "model_used": data.get('model_used'),
        "tokens_used": data.get('tokens_used'),
        "processing_time": data.get('processing_time'),
        "created_at": datetime.now().isoformat()
    }, upsert=False)  # Insert only
    
    return fingerprint_id


def get_fingerprints(
    twitter_handle: str = None,
    stage: int = None,
    decision: str = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Get decision fingerprints with optional filters."""
    conn = get_connection()
    cur = conn.cursor()
    
    query = 'SELECT * FROM decision_fingerprints WHERE 1=1'
    params = []
    
    if twitter_handle:
        query += ' AND twitter_handle = ?'
        params.append(twitter_handle.lstrip('@'))
    
    if stage:
        query += ' AND stage = ?'
        params.append(stage)
    
    if decision:
        query += ' AND decision = ?'
        params.append(decision)
    
    query += ' ORDER BY created_at DESC LIMIT ?'
    params.append(limit)
    
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_project_journey(twitter_handle: str) -> Dict[str, Any]:
    """Get complete journey of a project through all stages."""
    conn = get_connection()
    cur = conn.cursor()
    
    handle = twitter_handle.lstrip('@')
    
    # Get all fingerprints for this project
    cur.execute('''
        SELECT * FROM decision_fingerprints 
        WHERE twitter_handle = ?
        ORDER BY stage, created_at
    ''', (handle,))
    fingerprints = [dict(row) for row in cur.fetchall()]
    
    # Get current status from each table
    cur.execute('SELECT * FROM triaged_projects WHERE twitter_handle = ?', (handle,))
    triage = cur.fetchone()
    
    cur.execute('SELECT * FROM verified_projects WHERE twitter_handle = ?', (handle,))
    verified = cur.fetchone()
    
    cur.execute('''
        SELECT * FROM monitoring_history 
        WHERE twitter_handle = ?
        ORDER BY monitored_at DESC LIMIT 10
    ''', (handle,))
    monitoring = [dict(row) for row in cur.fetchall()]
    
    conn.close()
    
    # Organize by stage
    journey = {
        "twitter_handle": handle,
        "stage_1_triage": {
            "fingerprints": [f for f in fingerprints if f['stage'] == 1],
            "current_data": dict(triage) if triage else None
        },
        "stage_2_verification": {
            "fingerprints": [f for f in fingerprints if f['stage'] == 2],
            "current_data": dict(verified) if verified else None
        },
        "stage_3_monitoring": {
            "fingerprints": [f for f in fingerprints if f['stage'] == 3],
            "history": monitoring
        },
        "total_fingerprints": len(fingerprints),
        "current_status": None
    }
    
    # Determine current status
    if verified:
        v = dict(verified)
        if v.get('monitoring_status') == 'launched':
            journey["current_status"] = "launched"
        elif v.get('verification_status') == 'confirmed':
            journey["current_status"] = "monitoring"
        elif v.get('verification_status') == 'rejected':
            journey["current_status"] = "rejected_stage2"
        else:
            journey["current_status"] = "pending_verification"
    elif triage:
        journey["current_status"] = "pending_verification"
    else:
        journey["current_status"] = "not_found"
    
    return journey


def get_fingerprint_stats() -> Dict[str, Any]:
    """Get statistics about fingerprints."""
    conn = get_connection()
    cur = conn.cursor()
    
    # By stage
    cur.execute('''
        SELECT stage, stage_name, COUNT(*) as count 
        FROM decision_fingerprints 
        GROUP BY stage
    ''')
    by_stage = {f"stage_{row[0]}_{row[1]}": row[2] for row in cur.fetchall()}
    
    # By decision
    cur.execute('''
        SELECT decision, COUNT(*) as count 
        FROM decision_fingerprints 
        GROUP BY decision
    ''')
    by_decision = {row[0]: row[1] for row in cur.fetchall()}
    
    # By stage + decision
    cur.execute('''
        SELECT stage, decision, COUNT(*) as count 
        FROM decision_fingerprints 
        GROUP BY stage, decision
    ''')
    by_stage_decision = {}
    for row in cur.fetchall():
        key = f"stage{row[0]}_{row[1]}"
        by_stage_decision[key] = row[2]
    
    # Total
    cur.execute('SELECT COUNT(*) FROM decision_fingerprints')
    total = cur.fetchone()[0]
    
    # Unique projects
    cur.execute('SELECT COUNT(DISTINCT twitter_handle) FROM decision_fingerprints')
    unique_projects = cur.fetchone()[0]
    
    conn.close()
    
    return {
        "total_fingerprints": total,
        "unique_projects": unique_projects,
        "by_stage": by_stage,
        "by_decision": by_decision,
        "by_stage_decision": by_stage_decision
    }


# ============================================
# MENTIONS: Influencer/Shill Tweet Tracking
# ============================================

def save_mention(data: Dict[str, Any]) -> int:
    """Save a mention (tweet from influencer about a project)."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Check if already exists
    cur.execute('''
        SELECT id FROM mentions 
        WHERE source_tweet_id = ? AND mentioned_handle = ?
    ''', (data.get('source_tweet_id'), (data.get('mentioned_handle') or '').lstrip('@')))
    
    existing = cur.fetchone()
    if existing:
        conn.close()
        return existing[0]
    
    cur.execute('''
        INSERT INTO mentions (
            source_tweet_id, source_author_handle, source_author_id,
            source_author_followers, source_tweet_text, source_tweet_date,
            mentioned_handle, mentioned_handles_found,
            project_name_extracted, project_ticker_extracted,
            project_chain_extracted, project_type_extracted,
            name_possibilities, ticker_possibilities,
            launch_date_mentioned, launch_platform_mentioned, ca_mentioned,
            mention_type, author_type, confidence, raw_response
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('source_tweet_id'),
        (data.get('source_author_handle') or '').lstrip('@'),
        data.get('source_author_id'),
        data.get('source_author_followers', 0),
        data.get('source_tweet_text'),
        data.get('source_tweet_date'),
        (data.get('mentioned_handle') or '').lstrip('@'),
        json.dumps(data.get('mentioned_handles_found', [])),
        data.get('project_name_extracted'),
        data.get('project_ticker_extracted'),
        data.get('project_chain_extracted'),
        data.get('project_type_extracted'),
        json.dumps(data.get('name_possibilities', [])),
        json.dumps(data.get('ticker_possibilities', [])),
        data.get('launch_date_mentioned'),
        data.get('launch_platform_mentioned'),
        data.get('ca_mentioned'),
        data.get('mention_type'),
        data.get('author_type'),
        data.get('confidence', 0),
        json.dumps(data.get('raw_response', {}))
    ))
    
    mention_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    # === DUAL-WRITE: Sync to Supabase ===
    _sync_to_supabase("mentions", {
        "source_tweet_id": data.get('source_tweet_id'),
        "source_author_handle": (data.get('source_author_handle') or '').lstrip('@'),
        "source_author_id": data.get('source_author_id'),
        "source_author_followers": data.get('source_author_followers', 0),
        "source_tweet_text": data.get('source_tweet_text'),
        "source_tweet_date": data.get('source_tweet_date'),
        "mentioned_handle": (data.get('mentioned_handle') or '').lstrip('@'),
        "mentioned_handles_found": data.get('mentioned_handles_found', []),
        "project_name_extracted": data.get('project_name_extracted'),
        "project_ticker_extracted": data.get('project_ticker_extracted'),
        "project_chain_extracted": data.get('project_chain_extracted'),
        "project_type_extracted": data.get('project_type_extracted'),
        "name_possibilities": data.get('name_possibilities', []),
        "ticker_possibilities": data.get('ticker_possibilities', []),
        "launch_date_mentioned": data.get('launch_date_mentioned'),
        "launch_platform_mentioned": data.get('launch_platform_mentioned'),
        "ca_mentioned": data.get('ca_mentioned'),
        "mention_type": data.get('mention_type'),
        "author_type": data.get('author_type'),
        "confidence": data.get('confidence', 0),
        "created_at": datetime.now().isoformat(),
        "raw_response": data.get('raw_response', {})
    }, upsert=False)  # Insert only
    
    return mention_id


def get_pending_mentions(limit: int = 100) -> List[Dict[str, Any]]:
    """Get mentions that haven't been investigated yet."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT * FROM mentions 
        WHERE investigated = 0 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (limit,))
    
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_mentions_by_handle(handle: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get all mentions of a specific project handle."""
    conn = get_connection()
    cur = conn.cursor()
    
    handle = handle.lstrip('@').lower()
    cur.execute('''
        SELECT * FROM mentions 
        WHERE LOWER(mentioned_handle) = ? 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (handle, limit))
    
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_handles_to_investigate(min_mentions: int = 2, limit: int = 50) -> List[Dict[str, Any]]:
    """Get project handles that have been mentioned multiple times and need investigation."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT 
            mentioned_handle,
            COUNT(*) as mention_count,
            MAX(source_author_followers) as max_source_followers,
            GROUP_CONCAT(DISTINCT project_name_extracted) as names_found,
            GROUP_CONCAT(DISTINCT project_ticker_extracted) as tickers_found,
            GROUP_CONCAT(DISTINCT project_chain_extracted) as chains_found,
            MAX(created_at) as last_mention
        FROM mentions 
        WHERE investigated = 0 
        AND mentioned_handle IS NOT NULL 
        AND mentioned_handle != ''
        GROUP BY LOWER(mentioned_handle)
        HAVING COUNT(*) >= ?
        ORDER BY COUNT(*) DESC, MAX(source_author_followers) DESC
        LIMIT ?
    ''', (min_mentions, limit))
    
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_mention_investigated(mention_id: int) -> bool:
    """Mark a mention as investigated."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE mentions 
        SET investigated = 1, updated_at = ?
        WHERE id = ?
    ''', (datetime.now().isoformat(), mention_id))
    
    success = cur.rowcount > 0
    conn.commit()
    conn.close()
    return success


def mark_mentions_investigated_by_handle(handle: str) -> int:
    """Mark all mentions of a handle as investigated."""
    conn = get_connection()
    cur = conn.cursor()
    
    handle = handle.lstrip('@').lower()
    cur.execute('''
        UPDATE mentions 
        SET investigated = 1, updated_at = ?
        WHERE LOWER(mentioned_handle) = ?
    ''', (datetime.now().isoformat(), handle))
    
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


def convert_mention_to_project(mention_id: int, project_id: int) -> bool:
    """Mark a mention as converted to a project."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE mentions 
        SET converted_to_project = 1, 
            converted_project_id = ?,
            investigated = 1,
            updated_at = ?
        WHERE id = ?
    ''', (project_id, datetime.now().isoformat(), mention_id))
    
    success = cur.rowcount > 0
    conn.commit()
    conn.close()
    return success


def get_mention_stats() -> Dict[str, Any]:
    """Get statistics about mentions."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Total mentions
    cur.execute('SELECT COUNT(*) FROM mentions')
    total = cur.fetchone()[0]
    
    # Pending investigation
    cur.execute('SELECT COUNT(*) FROM mentions WHERE investigated = 0')
    pending = cur.fetchone()[0]
    
    # Converted to projects
    cur.execute('SELECT COUNT(*) FROM mentions WHERE converted_to_project = 1')
    converted = cur.fetchone()[0]
    
    # Unique handles mentioned
    cur.execute('SELECT COUNT(DISTINCT mentioned_handle) FROM mentions')
    unique_handles = cur.fetchone()[0]
    
    # By mention type
    cur.execute('''
        SELECT mention_type, COUNT(*) as count 
        FROM mentions 
        GROUP BY mention_type
    ''')
    by_type = {row[0] or 'unknown': row[1] for row in cur.fetchall()}
    
    # Top mentioned handles
    cur.execute('''
        SELECT mentioned_handle, COUNT(*) as count 
        FROM mentions 
        WHERE mentioned_handle IS NOT NULL AND mentioned_handle != ''
        GROUP BY LOWER(mentioned_handle) 
        ORDER BY count DESC 
        LIMIT 10
    ''')
    top_handles = {row[0]: row[1] for row in cur.fetchall()}
    
    conn.close()
    
    return {
        "total_mentions": total,
        "pending_investigation": pending,
        "converted_to_projects": converted,
        "unique_handles_mentioned": unique_handles,
        "by_mention_type": by_type,
        "top_mentioned_handles": top_handles
    }


# ============================================
# LAUNCH CALENDAR
# ============================================

def init_calendar_table():
    """Initialize launch_calendar table."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS launch_calendar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            
            -- Project reference
            project_id INTEGER,
            twitter_handle TEXT NOT NULL UNIQUE,
            project_name TEXT,
            project_ticker TEXT,
            ticker_possibilities TEXT,
            
            -- Chain (for filtering)
            chain TEXT NOT NULL DEFAULT 'unknown',
            
            -- Launch date info
            launch_date TEXT,
            launch_time TEXT,
            launch_date_raw TEXT,
            launch_date_source TEXT,
            launch_date_confidence REAL DEFAULT 0.5,
            
            -- Urgency classification
            launch_urgency TEXT DEFAULT 'unknown',
            days_until_launch INTEGER,
            
            -- Platform
            launch_platform TEXT,
            
            -- Status
            calendar_status TEXT DEFAULT 'pending',
            ca_address TEXT,
            
            -- Alerts sent
            alert_7d_sent INTEGER DEFAULT 0,
            alert_24h_sent INTEGER DEFAULT 0,
            alert_today_sent INTEGER DEFAULT 0,
            alert_imminent_sent INTEGER DEFAULT 0,
            
            -- AI Analysis
            last_analyzed_at TEXT,
            analysis_notes TEXT,
            
            -- Timestamps
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Indexes for fast queries
    cur.execute('CREATE INDEX IF NOT EXISTS idx_calendar_date ON launch_calendar(launch_date)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_calendar_chain ON launch_calendar(chain)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_calendar_urgency ON launch_calendar(launch_urgency)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_calendar_status ON launch_calendar(calendar_status)')
    
    conn.commit()
    conn.close()


def save_to_calendar(data: Dict[str, Any]) -> int:
    """Save or update project in launch calendar."""
    conn = get_connection()
    cur = conn.cursor()
    
    twitter_handle = (data.get('twitter_handle') or '').lstrip('@')
    if not twitter_handle:
        conn.close()
        return 0
    
    # Check if exists
    cur.execute('SELECT id FROM launch_calendar WHERE twitter_handle = ?', (twitter_handle,))
    existing = cur.fetchone()
    
    now = datetime.now().isoformat()
    
    if existing:
        # Update
        cur.execute('''
            UPDATE launch_calendar SET
                project_name = COALESCE(?, project_name),
                project_ticker = COALESCE(?, project_ticker),
                ticker_possibilities = COALESCE(?, ticker_possibilities),
                chain = COALESCE(?, chain),
                launch_date = COALESCE(?, launch_date),
                launch_time = COALESCE(?, launch_time),
                launch_date_raw = COALESCE(?, launch_date_raw),
                launch_date_source = COALESCE(?, launch_date_source),
                launch_date_confidence = COALESCE(?, launch_date_confidence),
                launch_urgency = COALESCE(?, launch_urgency),
                days_until_launch = ?,
                launch_platform = COALESCE(?, launch_platform),
                calendar_status = COALESCE(?, calendar_status),
                ca_address = COALESCE(?, ca_address),
                last_analyzed_at = ?,
                analysis_notes = COALESCE(?, analysis_notes),
                updated_at = ?
            WHERE twitter_handle = ?
        ''', (
            data.get('project_name'),
            data.get('project_ticker'),
            data.get('ticker_possibilities'),
            data.get('chain'),
            data.get('launch_date'),
            data.get('launch_time'),
            data.get('launch_date_raw'),
            data.get('launch_date_source'),
            data.get('launch_date_confidence'),
            data.get('launch_urgency'),
            data.get('days_until_launch'),
            data.get('launch_platform'),
            data.get('calendar_status'),
            data.get('ca_address'),
            now,
            data.get('analysis_notes'),
            now,
            twitter_handle
        ))
        calendar_id = existing[0]
    else:
        # Insert
        cur.execute('''
            INSERT INTO launch_calendar (
                twitter_handle, project_id, project_name, project_ticker, ticker_possibilities, chain,
                launch_date, launch_time, launch_date_raw, launch_date_source,
                launch_date_confidence, launch_urgency, days_until_launch,
                launch_platform, calendar_status, ca_address,
                last_analyzed_at, analysis_notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            twitter_handle,
            data.get('project_id'),
            data.get('project_name'),
            data.get('project_ticker'),
            data.get('ticker_possibilities'),
            data.get('chain', 'unknown'),
            data.get('launch_date'),
            data.get('launch_time'),
            data.get('launch_date_raw'),
            data.get('launch_date_source'),
            data.get('launch_date_confidence', 0.5),
            data.get('launch_urgency', 'unknown'),
            data.get('days_until_launch'),
            data.get('launch_platform'),
            data.get('calendar_status', 'pending'),
            data.get('ca_address'),
            now,
            data.get('analysis_notes'),
            now,
            now
        ))
        calendar_id = cur.lastrowid
    
    conn.commit()
    conn.close()
    
    # Sync to Supabase
    supabase_data = {
        'twitter_handle': twitter_handle,
        'project_id': data.get('project_id'),
        'project_name': data.get('project_name'),
        'project_ticker': data.get('project_ticker'),
        'ticker_possibilities': data.get('ticker_possibilities'),
        'chain': data.get('chain', 'unknown'),
        'launch_date': data.get('launch_date'),
        'launch_time': data.get('launch_time'),
        'launch_date_raw': data.get('launch_date_raw'),
        'launch_date_source': data.get('launch_date_source'),
        'launch_date_confidence': data.get('launch_date_confidence'),
        'launch_urgency': data.get('launch_urgency'),
        'days_until_launch': data.get('days_until_launch'),
        'launch_platform': data.get('launch_platform'),
        'calendar_status': data.get('calendar_status', 'pending'),
        'ca_address': data.get('ca_address'),
        'last_analyzed_at': now,
        'analysis_notes': data.get('analysis_notes'),
        'updated_at': now
    }
    _sync_to_supabase('launch_calendar', supabase_data)
    
    return calendar_id


def get_calendar_by_date(date: str) -> List[Dict[str, Any]]:
    """Get projects launching on specific date."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT * FROM launch_calendar 
        WHERE launch_date = ? AND calendar_status NOT IN ('launched', 'cancelled')
        ORDER BY chain, launch_time
    ''', (date,))
    
    results = [dict(row) for row in cur.fetchall()]
    conn.close()
    return results


def get_calendar_today() -> List[Dict[str, Any]]:
    """Get projects launching today."""
    today = datetime.now().strftime('%Y-%m-%d')
    return get_calendar_by_date(today)


def get_calendar_upcoming(days: int = 7) -> List[Dict[str, Any]]:
    """Get projects launching in next X days."""
    conn = get_connection()
    cur = conn.cursor()
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    cur.execute('''
        SELECT * FROM launch_calendar 
        WHERE launch_date IS NOT NULL 
        AND launch_date >= ?
        AND launch_date <= date(?, '+' || ? || ' days')
        AND calendar_status NOT IN ('launched', 'cancelled')
        ORDER BY launch_date, chain, launch_time
    ''', (today, today, days))
    
    results = [dict(row) for row in cur.fetchall()]
    conn.close()
    return results


def get_calendar_by_chain(chain: str) -> List[Dict[str, Any]]:
    """Get all calendar entries for a chain."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT * FROM launch_calendar 
        WHERE chain = ? AND calendar_status NOT IN ('launched', 'cancelled')
        ORDER BY launch_date, launch_time
    ''', (chain.lower(),))
    
    results = [dict(row) for row in cur.fetchall()]
    conn.close()
    return results


def get_calendar_by_urgency(urgency: str) -> List[Dict[str, Any]]:
    """Get projects by urgency level."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT * FROM launch_calendar 
        WHERE launch_urgency = ? AND calendar_status NOT IN ('launched', 'cancelled')
        ORDER BY launch_date, chain
    ''', (urgency,))
    
    results = [dict(row) for row in cur.fetchall()]
    conn.close()
    return results


def get_calendar_pending_alerts(alert_type: str) -> List[Dict[str, Any]]:
    """Get projects that need alerts."""
    conn = get_connection()
    cur = conn.cursor()
    
    alert_column = f'alert_{alert_type}_sent'
    today = datetime.now().strftime('%Y-%m-%d')
    
    if alert_type == 'today':
        cur.execute(f'''
            SELECT * FROM launch_calendar 
            WHERE launch_date = ? 
            AND {alert_column} = 0
            AND calendar_status NOT IN ('launched', 'cancelled')
        ''', (today,))
    elif alert_type == '24h':
        cur.execute(f'''
            SELECT * FROM launch_calendar 
            WHERE launch_date = date(?, '+1 day')
            AND {alert_column} = 0
            AND calendar_status NOT IN ('launched', 'cancelled')
        ''', (today,))
    elif alert_type == '7d':
        cur.execute(f'''
            SELECT * FROM launch_calendar 
            WHERE launch_date = date(?, '+7 days')
            AND {alert_column} = 0
            AND calendar_status NOT IN ('launched', 'cancelled')
        ''', (today,))
    elif alert_type == 'imminent':
        cur.execute(f'''
            SELECT * FROM launch_calendar 
            WHERE launch_urgency = 'imminent'
            AND {alert_column} = 0
            AND calendar_status NOT IN ('launched', 'cancelled')
        ''')
    
    results = [dict(row) for row in cur.fetchall()]
    conn.close()
    return results


def mark_calendar_alert_sent(calendar_id: int, alert_type: str) -> bool:
    """Mark alert as sent."""
    conn = get_connection()
    cur = conn.cursor()
    
    alert_column = f'alert_{alert_type}_sent'
    
    cur.execute(f'''
        UPDATE launch_calendar 
        SET {alert_column} = 1, updated_at = ?
        WHERE id = ?
    ''', (datetime.now().isoformat(), calendar_id))
    
    conn.commit()
    success = cur.rowcount > 0
    conn.close()
    return success


def update_calendar_status(twitter_handle: str, status: str, ca_address: str = None) -> bool:
    """Update calendar status (e.g., when project launches)."""
    conn = get_connection()
    cur = conn.cursor()
    
    handle = twitter_handle.lstrip('@')
    
    if ca_address:
        cur.execute('''
            UPDATE launch_calendar 
            SET calendar_status = ?, ca_address = ?, updated_at = ?
            WHERE twitter_handle = ?
        ''', (status, ca_address, datetime.now().isoformat(), handle))
    else:
        cur.execute('''
            UPDATE launch_calendar 
            SET calendar_status = ?, updated_at = ?
            WHERE twitter_handle = ?
        ''', (status, datetime.now().isoformat(), handle))
    
    conn.commit()
    success = cur.rowcount > 0
    conn.close()
    
    # Sync to Supabase
    _sync_to_supabase('launch_calendar', {
        'twitter_handle': handle,
        'calendar_status': status,
        'ca_address': ca_address,
        'updated_at': datetime.now().isoformat()
    })
    
    return success


def get_calendar_stats() -> Dict[str, Any]:
    """Get calendar statistics."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Total
    cur.execute('SELECT COUNT(*) FROM launch_calendar')
    total = cur.fetchone()[0]
    
    # By status
    cur.execute('''
        SELECT calendar_status, COUNT(*) 
        FROM launch_calendar 
        GROUP BY calendar_status
    ''')
    by_status = {row[0] or 'unknown': row[1] for row in cur.fetchall()}
    
    # By chain
    cur.execute('''
        SELECT chain, COUNT(*) 
        FROM launch_calendar 
        WHERE calendar_status NOT IN ('launched', 'cancelled')
        GROUP BY chain
    ''')
    by_chain = {row[0] or 'unknown': row[1] for row in cur.fetchall()}
    
    # By urgency
    cur.execute('''
        SELECT launch_urgency, COUNT(*) 
        FROM launch_calendar 
        WHERE calendar_status NOT IN ('launched', 'cancelled')
        GROUP BY launch_urgency
    ''')
    by_urgency = {row[0] or 'unknown': row[1] for row in cur.fetchall()}
    
    # Launching today
    today = datetime.now().strftime('%Y-%m-%d')
    cur.execute('''
        SELECT COUNT(*) FROM launch_calendar 
        WHERE launch_date = ? AND calendar_status NOT IN ('launched', 'cancelled')
    ''', (today,))
    launching_today = cur.fetchone()[0]
    
    # Launching this week
    cur.execute('''
        SELECT COUNT(*) FROM launch_calendar 
        WHERE launch_date >= ? AND launch_date <= date(?, '+7 days')
        AND calendar_status NOT IN ('launched', 'cancelled')
    ''', (today, today))
    launching_week = cur.fetchone()[0]
    
    conn.close()
    
    return {
        'total': total,
        'by_status': by_status,
        'by_chain': by_chain,
        'by_urgency': by_urgency,
        'launching_today': launching_today,
        'launching_this_week': launching_week
    }

