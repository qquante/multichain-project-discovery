# CATALOG: users/

The `users/` module manages Twitter user data — fetching profiles, tweets, and followings from the Twitter API, and caching them in `users.db`.

---

## users/api_client.py — Twitter User API Clients

**Purpose:** Three specialized HTTP clients for different user data endpoints on the twitterapi.io service.

### Class: `UserInfoClient`

Fetches batch profile information by user ID.

| Method | Purpose | Inputs | Outputs |
|---|---|---|---|
| `__init__(api_key, verbose)` | Init | args | — |
| `get_users_info(user_ids)` | Batch fetch profiles by list of IDs | `user_ids: list[str]` | `list[dict]` user objects |
| `get_user_info(user_id)` | Single user info | `user_id: str` | `dict` or `None` |
| `get_user_info_by_username(username)` | Fetch by handle | `username: str` | `dict` or `None` |

**Endpoint:** `POST /twitter/user/batch_info_by_ids`

### Class: `UserTweetsClient`

Fetches a user's recent tweets, including their pinned tweet.

| Method | Purpose | Inputs | Outputs |
|---|---|---|---|
| `__init__(api_key, verbose)` | Init | args | — |
| `get_user_tweets(user_id, username, include_replies, cursor)` | Fetch one page of tweets | args | `dict` with `pin_tweet`, `tweets`, `next_cursor` |
| `get_all_user_tweets(user_id, username, max_pages, include_replies)` | Paginate all tweets up to `max_pages` | args | `dict` with `pin_tweet`, `tweets` |

**Endpoint:** `GET /twitter/user/last_tweets`  
**Response includes:** `pin_tweet` (pinned tweet object) + `tweets` (list)

### Class: `UserFollowingsClient`

Fetches accounts that a user follows, with pagination.

| Method | Purpose | Inputs | Outputs |
|---|---|---|---|
| `__init__(api_key, verbose)` | Init | args | — |
| `get_user_followings(user_name, page_size, cursor)` | Fetch one page of followings | `user_name: str, page_size: int, cursor: str` | `dict` with `followings`, `next_cursor` |

**Endpoint:** `GET /twitter/user/followings`  
**Stop condition:** Uses stop-on-seen logic with cursor pagination.

---

## users/database.py — Users DB (users.db)

**Purpose:** All SQLite CRUD for `users.db`. Stores cached user tweets and alpha-following dedup state. Also handles Supabase dual-write.

### Database Tables

| Table | Purpose |
|---|---|
| `user_tweets` | Cached user tweets with full schema (60+ columns) |
| `user_fetch_state` | Per-user pagination state (last seen tweet ID, cursor) |
| `alpha_followings` | Dedup table for alpha-followers service |
| `twitter_cache` | TTL-based cache for API responses (used by `agent/twitter_cache.py`) |

### user_tweets Schema (key fields)
Mirrors `tweets.db` tweet schema:
- `id` — tweet ID
- `text`, `created_at`
- `author_id`, `author_username`, `author_name`
- `author_followers`, `author_following`
- `author_description` — bio snapshot at time of cache
- `like_count`, `retweet_count`, `reply_count`, `view_count`
- `is_pinned` — whether this was the pinned tweet

### twitter_cache Schema
- `cache_key` — `id:{user_id}` or `handle:{username}`
- `cache_type` — `tweets` or `user_info`
- `data` — JSON blob
- `cached_at` — ISO timestamp
- `expires_at` — ISO timestamp (cache_at + TTL hours)

### Key Functions

| Function | Purpose | Inputs | Outputs |
|---|---|---|---|
| `init_db()` | Create all tables | — | — |
| `save_user_tweets(user_id, handle, tweets, is_pinned_included)` | Bulk insert tweets to `user_tweets` | args | count saved |
| `get_cached_tweets(user_id, handle)` | Retrieve cached tweets | args | `list[dict]` |
| `update_user_fetch_state(user_id, handle, last_tweet_id, cursor)` | Save pagination state | args | — |
| `get_user_fetch_state(user_id, handle)` | Retrieve pagination state | args | `dict` |
| `was_following_seen(seed_handle, user_id)` | Dedup check for alpha-followers | `seed_handle: str, user_id: str` | `bool` |
| `mark_following_seen(seed_handle, user_id, username)` | Record that this following was processed | args | — |
| `save_twitter_cache(cache_key, cache_type, data, ttl_hours)` | Write cache entry | args | — |
| `get_twitter_cache(cache_key, cache_type)` | Read cache if not expired | args | `dict` or `None` |

---

## users/main.py — Users Public API

**Purpose:** Public entry points for user data operations. Thin wrapper around `UserTweetsClient` and `UserInfoClient`.

### Functions

| Function | Purpose | Inputs | Outputs |
|---|---|---|---|
| `fetch_user_tweets(handle, author_id, max_pages)` | Fetch and save user tweets | args | `dict` result |
| `fetch_user_info(user_id, handle)` | Fetch and cache user profile | args | `dict` result |
| `show_user_stats(handle)` | Print cached tweet stats for a handle | `handle: str` | console output |
