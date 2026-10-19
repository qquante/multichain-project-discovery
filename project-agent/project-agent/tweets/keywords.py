    # tweets/keywords.py
"""
Keyword batches for tweet collection.
Organized by category for efficient API queries.
"""

from datetime import datetime


def get_today_date() -> str:
    """Get today's date in YYYY-MM-DD format for Twitter API."""
    return datetime.now().strftime('%Y-%m-%d')


def get_since_date(hours_ago: int = 48) -> str:
    """Get date X hours ago in YYYY-MM-DD format for Twitter API."""
    from datetime import timedelta
    since = datetime.now() - timedelta(hours=hours_ago)
    return since.strftime('%Y-%m-%d')


# All keywords provided
ALL_KEYWORDS = [
    # Pre-launch signals (no CA)
    "not live yet", "not deployed", "no ca yet", "no token yet",
    "CA WILL BE DROPPED",
    
    # Launch signals
    "live soon", "launching soon", "launch soon",
    "fair launch", "no snipers", "launch will come soon",
    
    # Timing
    "launching in", "launching at", "launch in", "launch at",
    "tge is", "tge today", "TGE THIS WEEK",
    "launch time", "launching time", "launches on",
    "LAUNCH IN ONE HOUR",
    
    # Platform
    "launchpad", "platform goes live", "platform will be live",
    "token goes live", "deployed by",
    
    # Tech terms
    "Proof-of-Utility", "Proof of Utility",
    "Proof-of-stake", "Proof of stake",
    "Proof-of-work", "Proof of work",
    
    # Solana
    "built on solana", "built on sol", "built on @solana",
    "building on solana", "building on sol", "building on @solana",
    
    # MegaETH
    "built on Megaeth", "built on @Megaeth",
    "building on Megaeth", "building on @Megaeth",
    
    # Monad
    "built on Monad", "built on @Monad",
    "building on Monad", "building on @Monad",
    
    # BSC
    "built on Bsc", "built on @Bsc",
    "building on Bsc", "building on @Bsc",
    
    # Ethereum
    "built on ethereum", "built on @ethereum", "built on eth",
    "building on ethereum", "building on eth", "building on @ethereum",
    
    # Base
    "built on base", "built on @base",
    "building on base", "building on @base",
    
    # Other chains
    "built on arbitrum", "built on abstract",
]


# Organized into batches (max ~500 chars per query)
KEYWORD_BATCHES = {
    "pre_launch": {
        "keywords": [
            "not live yet",
            "not deployed",
            "no ca yet",
            "no token yet",
            "fair launch",
            "no snipers",
            "CA WILL BE DROPPED"
        ],
        "priority": 1,
        "description": "Pre-launch projects without CA"
    },
    
    "launch_soon": {
        "keywords": [
            "live soon",
            "launching soon",
            "launch soon",
            "token goes live",
            "platform goes live",
            "platform will be live",
            "launch will come soon"
        ],
        "priority": 1,
        "description": "Projects launching soon"
    },
    
    "launch_timing": {
        "keywords": [
            "launching in",
            "launching at",
            "launch in",
            "launch at",
            "tge is",
            "tge today",
            "TGE THIS WEEK",
            "launch time",
            "launching time",
            "launches on",
            "launches in",
            "LAUNCH IN ONE HOUR",
            "launching now",
            "launching today",
            "launching tomorrow",
            "launching this week",
            "launching this month",
            "live today"
        ],
        "priority": 1,
        "description": "Projects with specific launch timing"
    },
    
    "launchpad": {
        "keywords": [
            "launchpad",
            "deployed by",
            "fair launch"
        ],
        "priority": 2,
        "description": "Launchpad mentions"
    },
    
    "tech_terms": {
        "keywords": [
            "Proof-of-Utility",
            "Proof of Utility",
            "Proof-of-stake",
            "Proof of stake",
            "Proof-of-work",
            "Proof of work"
        ],
        "priority": 3,
        "description": "Technical consensus mechanisms"
    },
    
    "early_stage": {
        "keywords": [
            "building in public",
            "building something",
            "working on something",
            "stealth mode",
            "stealth project",
            "stealth launch"

        ],
        "priority": 1,
        "description": "Early stage projects"
    },
    
    "token_signals": {
        "keywords": [
            "token coming",
            "token dropping",
            "token announcement",
            "airdrop confirmed",
            "snapshot soon",
            "Main token is"
        ],
        "priority": 1,
        "description": "Token launch signals"
    },
    
    "community": {
        "keywords": [
            "early access",
            "beta testers",
            "whitelist open",
            "waitlist open",
            "founding members"
        ],
        "priority": 2,
        "description": "Community/early access signals"
    },
    
    "fresh_launches": {
        "keywords": [
            "fresh launch",
            "just deployed",
            "just launched",
            "going live",
            "live now"
        ],
        "priority": 1,
        "description": "Fresh/new launches"
    },
    
    "new_projects": {
        "keywords": [
            "new dapp",
            "dapp launching",
            "app launching",
            "platform launching",
            "protocol launching"
        ],
        "priority": 1,
        "description": "New dapps and platforms"
    },
    
    "protocol_chains": {
        "keywords": [
            "Protocol on base",
            "Protocol on solana",
            "Protocol on monad",
            "Protocol on megaeth"
        ],
        "priority": 2,
        "description": "Protocol on specific chains"
    },
    
    "new_on_chains": {
        "keywords": [
            "new on solana",
            "new on base",
            "launching on base",
            "launching on solana"
        ],
        "priority": 1,
        "description": "New projects on specific chains"
    },
    
    "solana": {
        "keywords": [
            "built on solana",
            "built on sol",
            "built on @solana",
            "building on solana",
            "building on sol",
            "building on @solana"
        ],
        "priority": 2,
        "description": "Solana chain projects"
    },
    
    "megaeth": {
        "keywords": [
            "built on Megaeth",
            "built on @Megaeth",
            "building on Megaeth",
            "building on @Megaeth"
        ],
        "priority": 2,
        "description": "MegaETH chain projects"
    },
    
    "monad": {
        "keywords": [
            "built on Monad",
            "built on @Monad",
            "building on Monad",
            "building on @Monad"
        ],
        "priority": 2,
        "description": "Monad chain projects"
    },
    
    "bsc": {
        "keywords": [
            "built on Bsc",
            "built on @Bsc",
            "building on Bsc",
            "building on @Bsc"
        ],
        "priority": 2,
        "description": "BSC chain projects"
    },
    
    "ethereum": {
        "keywords": [
            "built on ethereum",
            "built on @ethereum",
            "built on eth",
            "building on ethereum",
            "building on eth",
            "building on @ethereum"
        ],
        "priority": 2,
        "description": "Ethereum chain projects"
    },
    
    "base": {
        "keywords": [
            "built on base",
            "built on @base",
            "building on base",
            "building on @base"
        ],
        "priority": 2,
        "description": "Base chain projects"
    },
    
    "other_chains": {
        "keywords": [
            "built on arbitrum",
            "built on abstract"
        ],
        "priority": 3,
        "description": "Other chain projects"
    }
}


def get_batch_names() -> list:
    """Get all batch names sorted by priority."""
    return sorted(
        KEYWORD_BATCHES.keys(),
        key=lambda x: KEYWORD_BATCHES[x]['priority']
    )


def get_batch(name: str) -> dict:
    """Get a specific batch configuration."""
    return KEYWORD_BATCHES.get(name, {})


def build_query_for_batch(batch_name: str, lang: str = "en", since_hours: int = 48) -> str:
    """
    Build Twitter API query for a batch.
    Format: ("kw1" OR "kw2" OR ...) -filter:replies -filter:retweets lang:en since:YYYY-MM-DD
    
    Args:
        batch_name: Name of the keyword batch
        lang: Language filter (default: "en")
        since_hours: How many hours ago to start from (default: 48 = 2 days)
    """
    batch = KEYWORD_BATCHES.get(batch_name)
    if not batch:
        return ""
    
    keywords = batch['keywords']
    
    # Build OR query with quotes
    kw_parts = [f'"{kw}"' for kw in keywords]
    kw_query = " OR ".join(kw_parts)
    
    # Add filters
    query = f"({kw_query}) -filter:replies -filter:retweets"
    
    if lang:
        query += f" lang:{lang}"
    
    # Add since filter (48 hours ago by default)
    if since_hours > 0:
        since_date = get_since_date(since_hours)
        query += f" since:{since_date}"
    
    return query


def get_all_queries() -> dict:
    """Get all queries for all batches."""
    queries = {}
    for batch_name in KEYWORD_BATCHES:
        queries[batch_name] = build_query_for_batch(batch_name)
    return queries

