
-- ============================================
-- TWEETS DATABASE TABLES
-- ============================================

-- Main tweets table
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
    is_reply BOOLEAN DEFAULT FALSE,
    in_reply_to_id TEXT,
    conversation_id TEXT,
    display_text_range TEXT,
    in_reply_to_user_id TEXT,
    in_reply_to_username TEXT,
    is_limited_reply BOOLEAN DEFAULT FALSE,
    author_id TEXT,
    author_username TEXT,
    author_name TEXT,
    author_url TEXT,
    author_twitter_url TEXT,
    author_is_verified BOOLEAN DEFAULT FALSE,
    author_is_blue_verified BOOLEAN DEFAULT FALSE,
    author_verified_type TEXT,
    author_profile_picture TEXT,
    author_cover_picture TEXT,
    author_description TEXT,
    author_location TEXT,
    author_followers INTEGER DEFAULT 0,
    author_following INTEGER DEFAULT 0,
    author_can_dm BOOLEAN DEFAULT FALSE,
    author_created_at TEXT,
    author_favourites_count INTEGER DEFAULT 0,
    author_media_count INTEGER DEFAULT 0,
    author_statuses_count INTEGER DEFAULT 0,
    author_is_automated BOOLEAN DEFAULT FALSE,
    author_profile_bio JSONB,
    entities_json JSONB,
    extended_entities_json JSONB,
    card_json JSONB,
    place_json JSONB,
    quoted_tweet_id TEXT,
    retweeted_tweet_id TEXT,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    query_used TEXT,
    raw_json JSONB
);

-- Query state table
CREATE TABLE IF NOT EXISTS query_state (
    query_hash TEXT PRIMARY KEY,
    query_text TEXT,
    last_tweet_ids JSONB,
    last_run_at TEXT,
    total_captured INTEGER DEFAULT 0
);

-- Quoted tweets table
CREATE TABLE IF NOT EXISTS quoted_tweets (
    id TEXT PRIMARY KEY,
    parent_tweet_id TEXT REFERENCES tweets(id),
    raw_json JSONB
);

-- Keyword batches table
CREATE TABLE IF NOT EXISTS keyword_batches (
    id SERIAL PRIMARY KEY,
    batch_name TEXT UNIQUE NOT NULL,
    keywords JSONB NOT NULL,
    description TEXT,
    priority INTEGER DEFAULT 1,
    last_run_at TEXT,
    last_tweet_id TEXT,
    tweets_found INTEGER DEFAULT 0,
    new_tweets INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Collection history table
CREATE TABLE IF NOT EXISTS collection_history (
    id SERIAL PRIMARY KEY,
    batch_name TEXT NOT NULL,
    run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    query_used TEXT,
    pages_fetched INTEGER DEFAULT 0,
    tweets_found INTEGER DEFAULT 0,
    new_tweets INTEGER DEFAULT 0,
    stopped_reason TEXT,
    elapsed_time REAL DEFAULT 0,
    error_message TEXT
);

-- Indexes for tweets
CREATE INDEX IF NOT EXISTS idx_tweets_author_id ON tweets(author_id);
CREATE INDEX IF NOT EXISTS idx_tweets_created_at ON tweets(created_at);
CREATE INDEX IF NOT EXISTS idx_tweets_captured_at ON tweets(captured_at);
CREATE INDEX IF NOT EXISTS idx_tweets_author_username ON tweets(author_username);



-- ============================================
-- AGENT DATABASE TABLES
-- ============================================

-- Processed tweets tracking
CREATE TABLE IF NOT EXISTS processed_tweets (
    tweet_id TEXT PRIMARY KEY,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_project BOOLEAN DEFAULT FALSE,
    confidence REAL DEFAULT 0,
    rejection_reason TEXT,
    raw_response TEXT
);

-- Triaged projects
CREATE TABLE IF NOT EXISTS triaged_projects (
    id SERIAL PRIMARY KEY,
    twitter_handle TEXT UNIQUE,
    author_id TEXT,
    author_followers INTEGER DEFAULT 0,
    project_name TEXT,
    project_ticker TEXT,
    project_type TEXT,
    project_chain TEXT,
    has_ca BOOLEAN DEFAULT FALSE,
    ca_address TEXT,
    launch_status TEXT,
    launch_date TEXT,
    launch_time TEXT,
    launch_platform TEXT,
    source_tweet_id TEXT,
    tweet_date TEXT,
    tweet_text_preview TEXT,
    discovery_source TEXT,
    discovery_keyword TEXT,
    tagged_accounts JSONB,
    tagged_chains JSONB,
    tagged_platforms JSONB,
    keywords_found JSONB,
    has_links BOOLEAN DEFAULT FALSE,
    links JSONB,
    has_telegram BOOLEAN DEFAULT FALSE,
    telegram_link TEXT,
    has_website BOOLEAN DEFAULT FALSE,
    website_link TEXT,
    confidence REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_response JSONB
);

-- Verified projects
CREATE TABLE IF NOT EXISTS verified_projects (
    id SERIAL PRIMARY KEY,
    twitter_handle TEXT UNIQUE,
    author_id TEXT,
    verification_status TEXT,
    verification_confidence REAL DEFAULT 0,
    rejection_reason TEXT,
    project_name TEXT,
    project_ticker TEXT,
    project_type TEXT,
    project_chain TEXT,
    launch_platform TEXT,
    bio TEXT,
    bio_has_crypto_keywords BOOLEAN DEFAULT FALSE,
    bio_mentions_project BOOLEAN DEFAULT FALSE,
    has_website BOOLEAN DEFAULT FALSE,
    website_url TEXT,
    has_telegram BOOLEAN DEFAULT FALSE,
    telegram_url TEXT,
    has_discord BOOLEAN DEFAULT FALSE,
    discord_url TEXT,
    followers INTEGER DEFAULT 0,
    following INTEGER DEFAULT 0,
    account_created_at TEXT,
    account_age_days INTEGER DEFAULT 0,
    total_tweets INTEGER DEFAULT 0,
    media_count INTEGER DEFAULT 0,
    is_blue_verified BOOLEAN DEFAULT FALSE,
    pinned_tweet_ids JSONB,
    tweets_analyzed INTEGER DEFAULT 0,
    crypto_related_count INTEGER DEFAULT 0,
    project_mention_count INTEGER DEFAULT 0,
    launch_announcement_count INTEGER DEFAULT 0,
    spam_score REAL DEFAULT 0,
    consistent_project_messaging BOOLEAN DEFAULT FALSE,
    has_pinned_tweet_about_project BOOLEAN DEFAULT FALSE,
    multiple_launch_announcements BOOLEAN DEFAULT FALSE,
    bio_matches_tweets BOOLEAN DEFAULT FALSE,
    source_tweet_id TEXT,
    triage_id INTEGER,
    discovery_source TEXT,
    discovery_keyword TEXT,
    site_url TEXT,
    site_accessible BOOLEAN DEFAULT FALSE,
    site_title TEXT,
    site_description TEXT,
    site_content_preview TEXT,
    site_has_whitepaper BOOLEAN DEFAULT FALSE,
    site_has_tokenomics BOOLEAN DEFAULT FALSE,
    site_has_roadmap BOOLEAN DEFAULT FALSE,
    site_has_team BOOLEAN DEFAULT FALSE,
    site_has_audit BOOLEAN DEFAULT FALSE,
    site_social_links JSONB,
    site_contract_found BOOLEAN DEFAULT FALSE,
    site_contract_address TEXT,
    site_analysis TEXT,
    site_checked_at TEXT,
    site_raw_content TEXT,
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_user_info JSONB,
    raw_tweets_analyzed JSONB,
    raw_verification_response JSONB
);

-- Monitoring history
CREATE TABLE IF NOT EXISTS monitoring_history (
    id SERIAL PRIMARY KEY,
    project_id INTEGER,
    twitter_handle TEXT,
    monitored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    followers INTEGER DEFAULT 0,
    followers_change INTEGER DEFAULT 0,
    new_tweets_count INTEGER DEFAULT 0,
    last_tweet_text TEXT,
    last_tweet_at TEXT,
    ca_mentioned BOOLEAN DEFAULT FALSE,
    ca_address TEXT,
    ca_source TEXT,
    launch_mentioned BOOLEAN DEFAULT FALSE,
    launch_urgency TEXT,
    launch_date_detected TEXT,
    site_accessible BOOLEAN DEFAULT FALSE,
    site_changed BOOLEAN DEFAULT FALSE,
    site_ca_found BOOLEAN DEFAULT FALSE,
    bio_changed BOOLEAN DEFAULT FALSE,
    bio_new TEXT,
    pinned_changed BOOLEAN DEFAULT FALSE,
    pinned_new TEXT,
    status_before TEXT,
    status_after TEXT,
    priority_before TEXT,
    priority_after TEXT,
    changes_detected JSONB,
    ai_analysis TEXT,
    raw_response JSONB
);

-- Verification queue
CREATE TABLE IF NOT EXISTS verification_queue (
    triage_id INTEGER PRIMARY KEY,
    twitter_handle TEXT,
    author_id TEXT,
    status TEXT DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    last_attempt_at TEXT,
    error_message TEXT
);

-- Decision fingerprints
CREATE TABLE IF NOT EXISTS decision_fingerprints (
    id SERIAL PRIMARY KEY,
    twitter_handle TEXT NOT NULL,
    tweet_id TEXT,
    author_id TEXT,
    stage INTEGER NOT NULL,
    stage_name TEXT NOT NULL,
    decision TEXT NOT NULL,
    confidence REAL DEFAULT 0,
    reason TEXT,
    input_type TEXT,
    input_summary TEXT,
    input_tweet_text TEXT,
    input_bio TEXT,
    input_followers INTEGER,
    input_tweets_count INTEGER,
    input_site_url TEXT,
    llm_reasoning TEXT,
    key_factors JSONB,
    project_name TEXT,
    project_chain TEXT,
    project_type TEXT,
    ca_detected BOOLEAN DEFAULT FALSE,
    ca_address TEXT,
    launch_urgency TEXT,
    launch_date TEXT,
    raw_input JSONB,
    raw_output JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    model_used TEXT,
    tokens_used INTEGER,
    processing_time REAL
);

-- Mentions table
CREATE TABLE IF NOT EXISTS mentions (
    id SERIAL PRIMARY KEY,
    source_tweet_id TEXT NOT NULL,
    source_author_handle TEXT NOT NULL,
    source_author_id TEXT,
    source_author_followers INTEGER DEFAULT 0,
    source_tweet_text TEXT,
    source_tweet_date TEXT,
    mentioned_handle TEXT,
    mentioned_handles_found JSONB,
    project_name_extracted TEXT,
    project_ticker_extracted TEXT,
    project_chain_extracted TEXT,
    project_type_extracted TEXT,
    name_possibilities JSONB,
    ticker_possibilities JSONB,
    launch_date_mentioned TEXT,
    launch_platform_mentioned TEXT,
    ca_mentioned TEXT,
    mention_type TEXT,
    author_type TEXT,
    confidence REAL DEFAULT 0,
    investigated BOOLEAN DEFAULT FALSE,
    converted_to_project BOOLEAN DEFAULT FALSE,
    converted_project_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_response JSONB,
    UNIQUE(source_tweet_id, mentioned_handle)
);

-- Indexes for agent tables
CREATE INDEX IF NOT EXISTS idx_processed_tweet_id ON processed_tweets(tweet_id);
CREATE INDEX IF NOT EXISTS idx_triaged_handle ON triaged_projects(twitter_handle);
CREATE INDEX IF NOT EXISTS idx_triaged_chain ON triaged_projects(project_chain);
CREATE INDEX IF NOT EXISTS idx_triaged_status ON triaged_projects(launch_status);
CREATE INDEX IF NOT EXISTS idx_verified_handle ON verified_projects(twitter_handle);
CREATE INDEX IF NOT EXISTS idx_verified_status ON verified_projects(verification_status);
CREATE INDEX IF NOT EXISTS idx_verified_monitoring ON verified_projects(monitoring_status);
CREATE INDEX IF NOT EXISTS idx_verified_priority ON verified_projects(priority);
CREATE INDEX IF NOT EXISTS idx_verified_last_monitored ON verified_projects(last_monitored_at);
CREATE INDEX IF NOT EXISTS idx_queue_status ON verification_queue(status);
CREATE INDEX IF NOT EXISTS idx_monitoring_project ON monitoring_history(project_id);
CREATE INDEX IF NOT EXISTS idx_monitoring_handle ON monitoring_history(twitter_handle);
CREATE INDEX IF NOT EXISTS idx_fingerprint_handle ON decision_fingerprints(twitter_handle);
CREATE INDEX IF NOT EXISTS idx_fingerprint_stage ON decision_fingerprints(stage);
CREATE INDEX IF NOT EXISTS idx_fingerprint_decision ON decision_fingerprints(decision);
CREATE INDEX IF NOT EXISTS idx_mentions_handle ON mentions(mentioned_handle);
CREATE INDEX IF NOT EXISTS idx_mentions_source ON mentions(source_author_handle);
CREATE INDEX IF NOT EXISTS idx_mentions_investigated ON mentions(investigated);
CREATE INDEX IF NOT EXISTS idx_mentions_converted ON mentions(converted_to_project);



-- ============================================
-- USERS DATABASE TABLES
-- ============================================

-- User tweets table
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
    is_reply BOOLEAN DEFAULT FALSE,
    in_reply_to_id TEXT,
    conversation_id TEXT,
    display_text_range TEXT,
    in_reply_to_user_id TEXT,
    in_reply_to_username TEXT,
    is_limited_reply BOOLEAN DEFAULT FALSE,
    author_type TEXT,
    author_id TEXT,
    author_username TEXT,
    author_name TEXT,
    author_url TEXT,
    author_twitter_url TEXT,
    author_is_verified BOOLEAN DEFAULT FALSE,
    author_is_blue_verified BOOLEAN DEFAULT FALSE,
    author_verified_type TEXT,
    author_profile_picture TEXT,
    author_cover_picture TEXT,
    author_description TEXT,
    author_location TEXT,
    author_followers INTEGER DEFAULT 0,
    author_following INTEGER DEFAULT 0,
    author_can_dm BOOLEAN DEFAULT FALSE,
    author_can_media_tag BOOLEAN DEFAULT FALSE,
    author_created_at TEXT,
    author_favourites_count INTEGER DEFAULT 0,
    author_has_custom_timelines BOOLEAN DEFAULT FALSE,
    author_is_translator BOOLEAN DEFAULT FALSE,
    author_media_count INTEGER DEFAULT 0,
    author_statuses_count INTEGER DEFAULT 0,
    author_withheld_in_countries JSONB,
    author_affiliates_highlighted_label JSONB,
    author_possibly_sensitive BOOLEAN DEFAULT FALSE,
    author_pinned_tweet_ids JSONB,
    author_is_automated BOOLEAN DEFAULT FALSE,
    author_automated_by TEXT,
    author_unavailable BOOLEAN DEFAULT FALSE,
    author_message TEXT,
    author_unavailable_reason TEXT,
    author_profile_bio_description TEXT,
    author_profile_bio_entities JSONB,
    entities_hashtags JSONB,
    entities_urls JSONB,
    entities_user_mentions JSONB,
    entities_symbols JSONB,
    extended_entities_json JSONB,
    card_json JSONB,
    place_json JSONB,
    quoted_tweet_id TEXT,
    quoted_tweet_json JSONB,
    retweeted_tweet_id TEXT,
    retweeted_tweet_json JSONB,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fetched_by_user_id TEXT,
    fetched_by_username TEXT,
    include_replies BOOLEAN DEFAULT FALSE,
    raw_json JSONB
);

-- User fetch state
CREATE TABLE IF NOT EXISTS user_fetch_state (
    user_identifier TEXT PRIMARY KEY,
    user_id TEXT,
    user_name TEXT,
    last_tweet_ids JSONB,
    last_run_at TEXT,
    total_captured INTEGER DEFAULT 0
);

-- Indexes for user tweets
CREATE INDEX IF NOT EXISTS idx_user_tweets_author_id ON user_tweets(author_id);
CREATE INDEX IF NOT EXISTS idx_user_tweets_author_username ON user_tweets(author_username);
CREATE INDEX IF NOT EXISTS idx_user_tweets_created_at ON user_tweets(created_at);
CREATE INDEX IF NOT EXISTS idx_user_tweets_fetched_by ON user_tweets(fetched_by_user_id);


-- ============================================
-- LAUNCH CALENDAR
-- ============================================

CREATE TABLE IF NOT EXISTS launch_calendar (
    id SERIAL PRIMARY KEY,
    project_id INTEGER,
    twitter_handle TEXT NOT NULL UNIQUE,
    project_name TEXT,
    project_ticker TEXT,
    ticker_possibilities JSONB,
    chain TEXT NOT NULL DEFAULT 'unknown',
    launch_date DATE,
    launch_time TEXT,
    launch_date_raw TEXT,
    launch_date_source TEXT,
    launch_date_confidence REAL DEFAULT 0.5,
    launch_urgency TEXT DEFAULT 'unknown',
    days_until_launch INTEGER,
    launch_platform TEXT,
    calendar_status TEXT DEFAULT 'pending',
    ca_address TEXT,
    alert_7d_sent BOOLEAN DEFAULT FALSE,
    alert_24h_sent BOOLEAN DEFAULT FALSE,
    alert_today_sent BOOLEAN DEFAULT FALSE,
    alert_imminent_sent BOOLEAN DEFAULT FALSE,
    last_analyzed_at TIMESTAMP,
    analysis_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for calendar
CREATE INDEX IF NOT EXISTS idx_calendar_date ON launch_calendar(launch_date);
CREATE INDEX IF NOT EXISTS idx_calendar_chain ON launch_calendar(chain);
CREATE INDEX IF NOT EXISTS idx_calendar_urgency ON launch_calendar(launch_urgency);
CREATE INDEX IF NOT EXISTS idx_calendar_status ON launch_calendar(calendar_status);