# CATALOG: tweets/

The `tweets/` module manages all Twitter data collection. It handles keyword-based search, tweet storage in `tweets.db`, batch management, and provides the query builder API.

---

## tweets/main.py — Public API

**Purpose:** Public-facing functions for running tweet collection. Imported by `services/collector/main.py`.

### Functions

| Function | Purpose | Inputs | Outputs |
|---|---|---|---|
| `run_batch_collection(batch_name)` | Run one named keyword batch | `batch_name: str` | count saved |
| `run_all_batches()` | Run all 18 batches in sequence | — | total count |
| `run_priority_batches()` | Run high-priority batches only | — | count |
| `show_batches()` | Print all batch names and keyword counts | — | console output |
| `show_batch_status()` | Print last-run info per batch | — | console output |
| `run_early_project_search()` | Legacy: single hardcoded search | — | count |

---

## tweets/keywords.py — Keyword Batches

**Purpose:** Defines `KEYWORD_BATCHES` — 18 named keyword groups organized by signal type.

### Batch Names
| Batch | Signal Type |
|---|---|
| `pre_launch` | Pre-launch announcements |
| `launch_soon` | Imminent launch signals |
| `launch_timing` | Specific timing language |
| `launchpad` | Launchpad/IDO platform mentions |
| `tech_terms` | Technical crypto vocabulary |
| `early_stage` | Early project stage language |
| `token_signals` | Token-specific signals |
| `community` | Community building signals |
| `fresh_launches` | Just-launched projects |
| `new_projects` | New project announcements |
| `protocol_chains` | Protocol + chain combinations |
| `new_on_chains` | "New on X chain" language |
| `solana` | Solana-specific keywords |
| `megaeth` | MegaETH-specific |
| `monad` | Monad-specific |
| `bsc` | BSC-specific |
| `ethereum` | Ethereum-specific |
| `base` | Base chain specific |
| `other_chains` | Other/emerging chains |

### Functions

| Function | Purpose | Inputs | Outputs |
|---|---|---|---|
| `build_query_for_batch(batch_name, since_date)` | Build Twitter API query string | `batch_name: str, since_date: str` | `str` query |

**Query format:** Keywords joined with `OR`, appended with `-filter:replies -filter:retweets lang:en since:{DATE}`.

---

## tweets/api_client.py — Twitter Search Client

**Purpose:** `TwitterSearchClient` — HTTP client for the Twitter API search endpoint.

### Configuration
- `BASE_URL` — Twitter API base (twitterapi.io)
- `API_KEY` — from env var

### Class: `TwitterSearchClient`

| Method | Purpose | Inputs | Outputs |
|---|---|---|---|
| `__init__(api_key, verbose)` | Init with API key | `api_key: str, verbose: bool` | — |
| `search(query, cursor)` | Single-page search | `query: str, cursor: str` | `dict` with `tweets`, `next_cursor` |
| `search_with_pagination()` | Generator — yields tweets page by page, stops on seen tweet IDs | — | yields tweet dicts |
| `search_and_save(query, batch_name)` | Search all pages, save each new tweet | `query: str, batch_name: str` | count saved |

**Stop condition:** `search_with_pagination()` stops when a tweet ID was previously seen (dedup via `query_state` table).

---

## tweets/batch_collector.py — Batch Collector

**Purpose:** `BatchCollector` class. Manages full collection runs per keyword batch.

### Class: `BatchCollector`

| Method | Purpose | Inputs | Outputs |
|---|---|---|---|
| `__init__(api_key, verbose)` | Init | args | — |
| `collect_batch(batch_name)` | Run one batch: build query → paginate → save → record history | `batch_name: str` | count saved |
| `collect_all_batches()` | Run all batches in `KEYWORD_BATCHES` | — | `{batch_name: count}` dict |
| `collect_priority_batches()` | Run subset of high-priority batches | — | count |

**Stopping logic:** Stops pagination when it encounters a tweet ID that was seen on the previous run (stored in `query_state`). Saves run history in `collection_history`.

---

## tweets/query_builder.py — Query Builder

**Purpose:** `QueryBuilder` — fluent builder API for constructing Twitter search queries programmatically.

### Class: `QueryBuilder`

| Method | Purpose | Returns |
|---|---|---|
| `keywords(*terms)` | Add individual keywords (OR joined) | `self` |
| `keyword_phrases(*phrases)` | Add quoted phrases | `self` |
| `from_user(username)` | `from:{username}` filter | `self` |
| `exclude_replies()` | `-filter:replies` | `self` |
| `exclude_retweets()` | `-filter:retweets` | `self` |
| `min_likes(n)` | `min_faves:{n}` | `self` |
| `since(date_str)` | `since:{date}` | `self` |
| `language(lang)` | `lang:{lang}` | `self` |
| `build()` | Assemble final query string | `str` |

### Factory Functions

| Function | Purpose |
|---|---|
| `early_project_query(since_date)` | Pre-built early-stage project query |
| `crypto_launch_query(since_date)` | Pre-built launch-focused query |
| `custom_keywords_query(keywords, since_date)` | Build from custom keyword list |

---

## tweets/database.py — Tweets DB (tweets.db)

**Purpose:** All SQLite CRUD for `tweets.db`. Also handles Supabase dual-write.

### Database Tables

| Table | Purpose |
|---|---|
| `tweets` | Full tweet + author data (50+ columns) |
| `query_state` | Per-query dedup state — stores newest tweet ID per query |
| `quoted_tweets` | Quoted tweet references |
| `keyword_batches` | Batch configurations and last-run timestamps |
| `collection_history` | Audit trail of each batch collection run |

### Tweet Schema (key fields)
- `id` — Twitter tweet ID
- `text` — tweet body
- `author_id`, `author_username`, `author_name`
- `author_followers`, `author_following`, `author_tweet_count`
- `author_created_at`, `author_blue_verified`
- `author_description` — bio
- `author_location`, `author_profile_image_url`
- `created_at` — tweet timestamp
- `like_count`, `retweet_count`, `reply_count`, `view_count`
- `has_media`, `media_urls`
- `is_quote_tweet`, `quoted_tweet_id`
- `query_used`, `batch_name` — how this tweet was collected

### Key Functions

| Function | Purpose | Inputs | Outputs |
|---|---|---|---|
| `init_db()` | Create tables | — | — |
| `tweet_exists(tweet_id)` | Dedup check | `tweet_id: str` | `bool` |
| `save_tweet(tweet, query_used)` | Insert tweet + dual-write to Supabase | `tweet: dict, query_used: str` | `bool` |
| `get_pending_tweets(limit)` | Get tweets not yet in `processed_tweets` | `limit: int` | `list[dict]` |
| `get_query_state(query)` | Get most recent tweet ID seen for this query | `query: str` | `str` or `None` |
| `update_query_state(query, tweet_id)` | Save newest tweet ID for dedup | `query: str, tweet_id: str` | — |
| `save_collection_history(data)` | Record batch run audit | `data: dict` | — |
| `get_batch_stats(batch_name)` | Return stats for one batch | `batch_name: str` | `dict` |
