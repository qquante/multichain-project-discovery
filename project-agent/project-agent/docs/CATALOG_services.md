# CATALOG: services/

The `services/` directory contains all long-running Docker microservices. Each service subscribes to Redis channels and/or polls databases, then publishes results downstream.

---

## Overview: Service Map

| Service | Role | Input | Output |
|---|---|---|---|
| `collector` | Fetch tweets from Twitter API | keyword batches | `tweets:collected`, `tweets:new` |
| `triage` | Stage 1: classify tweets | `tweets:new`, DB poll | `projects:triaged`, `triage:rejected`, `mentions:new`, `fingerprint:new` |
| `verifier` | Stage 2: deep-verify projects | `projects:triaged`, DB poll | `projects:confirmed`, `projects:rejected`, `fingerprint:new` |
| `monitor` | Stage 3: watch verified projects | `projects:confirmed`, DB poll | `projects:launched`, `projects:abandoned`, `projects:alert`, `projects:monitored` |
| `discoverer` | Investigate influencer mentions | DB poll (mentions table) | `discovery:complete` |
| `alphagate` | Fetch pre-filtered projects from AlphaGate API | timer (every 2h) | `projects:triaged` |
| `alpha-followers` | Fetch followings of seed accounts | timer (every 12h) | `tweets:new` (triage stub) |
| `alpha-hunter` | Fetch tweets from alpha callers | timer (every 12h) | `tweets:collected` |
| `abandoned-checker` | Check abandoned projects for reactivation | timer (every 7d) | `projects:reactivated`, `projects:removed` |
| `calendar-alerter` | Send launch alerts from calendar | timer (every 60m) | Telegram direct HTTP + `calendar:alert:{type}` |
| `telegram-low` | Bot 1: Stage 0/1 + fingerprints | `tweets:collected`, `projects:triaged`, `triage:rejected`, `fingerprint:new` | Telegram messages |
| `telegram-high` | Bot 2: Stage 2/3 + mentions | `projects:confirmed`, `projects:rejected`, `projects:monitored`, etc. | Telegram messages |
| `telegram-chains` | Send confirmed/monitored to chain-specific groups | `projects:confirmed:{chain}`, `projects:monitored:{chain}` | Telegram messages |
| `telegram-chains-callback` | Handle Favorite/Stop buttons on chain bot messages | Telegram long-poll | DB writes, message edits |
| `telegram-bot` | Interactive `/add` command bot | Telegram long-poll | DB writes, triage stubs |

---

## services/collector/main.py — Tweet Collector

**Purpose:** `CollectorService`. Polls Twitter API with keyword batches every `COLLECTION_INTERVAL_HOURS` (default 3h).

### Configuration
- `COLLECTION_INTERVAL_HOURS` — env var, default `3`
- `BATCH_SIZE` — tweets per batch (default large)

### Class: `CollectorService`

| Method | Purpose | Inputs | Outputs |
|---|---|---|---|
| `__init__()` | Init Redis, `BatchCollector` | — | — |
| `run()` | Main loop: iterate keyword batches, collect, publish | — | publishes to `tweets:collected`, `tweets:new` |

**Flow per batch:** `BatchCollector.collect_batch(batch_name)` → for each NEW tweet → publish to `tweets:collected` → after batch → publish batch notification to `tweets:new`.

---

## services/triage/main.py — Triage Service (Stage 1)

**Purpose:** `TriageService`. Subscribes to `tweets:new` and polls every 10s. Processes ALL pending tweets through `TweetAnalyzer`.

### Configuration
- `BATCH_SIZE = 999999` — no limit, process everything
- `POLL_INTERVAL = 10` seconds
- `DELAY_BETWEEN_TWEETS = 1.0` seconds between LLM calls

### Redis Channels
| Direction | Channel |
|---|---|
| Subscribe | `tweets:new` |
| Publish | `projects:triaged` |
| Publish | `triage:rejected` |
| Publish | `mentions:new` |
| Publish | `fingerprint:new` |

### Class: `TriageService`

| Method | Purpose |
|---|---|
| `process_pending_tweets()` | Get all pending from DB, run `TweetAnalyzer.analyze_tweet()` on each |
| `publish_triaged_project(result, tweet)` | Publish confirmed project to `projects:triaged` |
| `publish_rejected(result, tweet)` | Publish rejected tweet to `triage:rejected` |
| `publish_mention(result, tweet)` | Publish influencer mention to `mentions:new` (one message per mentioned handle) |
| `publish_fingerprint(tweet)` | Always publish latest fingerprint to `fingerprint:new` |
| `handle_new_tweets_notification(message)` | React to `tweets:new` by calling `process_pending_tweets()` |
| `run()` | Main loop: subscribe + poll + process |

---

## services/verifier/main.py — Verifier Service (Stage 2)

**Purpose:** `VerifierService`. Subscribes to `projects:triaged`, polls every 30s. Runs `ProjectVerifier` on each pending project.

### Redis Channels
| Direction | Channel |
|---|---|
| Subscribe | `projects:triaged` |
| Publish | `projects:confirmed` |
| Publish | `projects:confirmed:{chain}` (chain-specific) |
| Publish | `projects:rejected` |
| Publish | `fingerprint:new` |

### Class: `VerifierService`

| Method | Purpose |
|---|---|
| `process_pending_verifications()` | Get pending from queue, run `ProjectVerifier.verify_project()` |
| `post_verification(result)` | After verification: run `CalendarAgent.analyze_and_save()`, generate PT-BR summary, publish result |
| `run()` | Main loop |

**After confirmed:** Also calls `CalendarAgent` to extract launch date and `generate_project_summary()` for the AI blurb.

---

## services/monitor/main.py — Monitor Service (Stage 3)

**Purpose:** `MonitorService`. Watches verified projects on a priority schedule. Also handles delete requests.

### Redis Channels
| Direction | Channel |
|---|---|
| Subscribe | `projects:confirmed` |
| Subscribe | `monitor:delete` |
| Publish | `projects:launched` |
| Publish | `projects:abandoned` |
| Publish | `projects:alert` |
| Publish | `projects:monitored` |
| Publish | `projects:monitored:{chain}` (chain-specific) |

### Class: `MonitorService`

| Method | Purpose |
|---|---|
| `process_monitoring_queue()` | Check interval, call `ProjectMonitor.monitor_project()` for due projects |
| `handle_confirmed(data)` | Add new confirmed project to monitoring |
| `handle_delete(data)` | Remove project from monitoring |
| `run()` | Main loop |

**CA detection in monitoring:** When CA is found, silently updates `launch_calendar` — does NOT publish a separate Telegram alert (the `projects:launched` message covers it).

---

## services/discoverer/main.py — Discoverer Service

**Purpose:** `DiscovererService`. Runs every 1800s (30 min). Calls `ProjectDiscoverer.run_discovery_cycle()` to investigate influencer-mentioned handles.

### Redis Channels
| Direction | Channel |
|---|---|
| Publish | `discovery:complete` |

### Class: `DiscovererService`

| Method | Purpose |
|---|---|
| `run()` | Loop every 30min, call `run_discovery_cycle()`, publish results |

---

## services/alphagate/main.py — AlphaGate Collector

**Purpose:** Fetches pre-filtered projects directly from AlphaGate API. These skip Stage 1 LLM analysis and go straight to `triaged_projects`.

**Pipeline difference:** `AlphaGate API → triaged_projects → Verifier → Monitor` (no Triage LLM step)

### Configuration
- `ALPHAGATE_INTERVAL_HOURS = 2` — fetch every 2 hours
- `ALPHAGATE_MAX_FOLLOWERS = 50000` — filter cap
- `ALPHAGATE_MIN_KEY_FOLLOWERS = 1` — must have ≥1 key follower
- `ALPHAGATE_PAGES = 5` — pages to fetch per cycle
- Excludes projects tagged `Launched`

### Functions

| Function | Purpose |
|---|---|
| `fetch_alphagate_page(page)` | Fetch one page of projects from API |
| `convert_alphagate_to_triage(project)` | Convert AlphaGate format → internal triage format |
| `process_alphagate_project(redis_client, project)` | Save to DB, publish to `projects:triaged` if new |
| `collect_alphagate()` | Full collection cycle |
| `main()` | Loop every `ALPHAGATE_INTERVAL_HOURS` |

---

## services/alpha-followers/main.py — Alpha Followers Service

**Purpose:** Fetches the 20 most recent followings from a fixed list of 17 seed alpha traders every 12 hours. New followings are inserted as triage stubs.

### Configuration
- `POLL_INTERVAL_HOURS = 12`
- `PAGE_SIZE = 20` per seed
- `SEED_HANDLES` — 17 hardcoded trader handles

### Class: `AlphaFollowersService`

| Method | Purpose |
|---|---|
| `process_seed(seed)` | Fetch followings, dedup, insert triage stubs | 
| `_insert_triage_stub(handle, author_id, seed, followers, bio)` | Create minimal triage record for the handle |
| `run_cycle()` | Process all seeds, notify triage |
| `run()` | Main loop every 12h |

**Dedup strategy:** Checks `was_following_seen(seed, user_id)` in `users.db` AND `is_handle_triaged/verified` in `agent.db`.

---

## services/alpha-hunter/main.py — Alpha Hunter Service

**Purpose:** Fetches tweets from configurable alpha caller accounts every 12h, saves only tweets with mentions or URLs to `tweets.db` for Triage processing.

### Configuration
- `HUNT_INTERVAL_HOURS = 12`
- `TWEETS_PER_CALLER = 20` per caller
- `ALPHA_CALLERS` — env var, default `"AresLabs_xyz"`
- Fetches last 48 hours of tweets per caller

### Functions

| Function | Purpose |
|---|---|
| `get_user_tweets(api_key, username, count)` | Search Twitter for `from:{username}` last 48h |
| `save_tweet_to_db(tweet, source)` | Save to `tweets.db`, skip if exists |
| `notify_triage(redis_client, source, count)` | Publish to `tweets:collected` |
| `hunt_alpha()` | Full hunt cycle for all callers |
| `main()` | Async loop every 12h |

---

## services/abandoned-checker/main.py — Abandoned Checker

**Purpose:** Checks all `abandoned` projects every 7 days. Promotes back to `active` if they posted recently, or moves to `removed` after 30 days of silence.

### Configuration
- `CHECK_INTERVAL_DAYS = 7`
- `DAYS_TO_REMOVE = 30` — silence threshold

### Redis Channels
| Direction | Channel |
|---|---|
| Publish | `projects:reactivated` |
| Publish | `projects:removed` |

### Class: `AbandonedChecker`

| Method | Purpose |
|---|---|
| `get_abandoned_projects()` | Query DB for all `monitoring_status = 'abandoned'` |
| `check_latest_tweet(handle)` | Fetch latest tweet via `twitter_cache` |
| `calculate_days_inactive(last_tweet_at)` | Parse date and return days since |
| `check_project(project)` | Apply logic: remove / reactivate / keep abandoned |
| `run_check_cycle()` | Process all abandoned projects |
| `run()` | Main loop every 7 days |

---

## services/calendar-alerter/main.py — Calendar Alerter

**Purpose:** Checks `launch_calendar` table every hour and sends Telegram alerts for imminent, today, 24h, and 7d launches. Groups by chain, shows time remaining, highlights favorites.

### Alert Types (in priority order)
1. `imminent` — launching now
2. `today` — launching today
3. `24h` — launching in 24 hours
4. `7d` — launching in 7 days

### Functions

| Function | Purpose |
|---|---|
| `calculate_time_remaining(launch_date, launch_time)` | Human-readable countdown string |
| `group_by_chain(projects)` | Group project list into `{chain: [projects]}` dict |
| `get_possible_tickers(project)` | Infer ticker possibilities if no confirmed ticker |
| `format_alert_message(alert_type, projects, favorites_handles)` | Build full HTML Telegram message |
| `send_telegram_alert(message)` | POST to Telegram Bot API |
| `check_and_send_alerts(redis_client)` | Check all 4 alert types, send, mark sent |
| `main()` | Async loop every `CHECK_INTERVAL_MINUTES` (default 60) |

---

## services/telegram-low/main.py — Telegram Bot Low Priority

**Purpose:** `TelegramLow` class. Handles Stage 0 (collected), Stage 1 (triaged/rejected), and fingerprint messages. Can drop messages under load (queue maxlen=100).

### Subscribed Channels
- `tweets:collected` → Topic: STAGE_0
- `projects:triaged` → Topic: STAGE_1
- `triage:rejected` → Topic: STAGE_1
- `fingerprint:new` → Topic: FINGERPRINTS

### Class: `TelegramLow`

| Method | Purpose |
|---|---|
| `drain_redis()` | Pull all pending messages from pubsub into deque |
| `can_send()` | Rate limit check (1s between sends) |
| `send_message(topic_id, text, buttons)` | POST to Telegram with retry (up to 3x) + 429 backoff |
| `format_message(channel, data)` | Route to correct formatter |
| `process_one()` | Pop one item from queue and send |
| `run()` | Main 50ms tick loop: drain + send |

---

## services/telegram-high/main.py — Telegram Bot High Priority

**Purpose:** `TelegramHigh` class. Handles Stage 2/3 and mentions. **NEVER drops messages** — uses unlimited deque. Re-queues on 429.

### Subscribed Channels
- `projects:confirmed` → Topic: STAGE_2
- `projects:rejected` → Topic: STAGE_2
- `projects:monitored` → Topic: STAGE_3
- `projects:alert` → Topic: STAGE_3
- `projects:launched` → Topic: STAGE_3
- `projects:abandoned` → Topic: STAGE_3
- `projects:removed` → Topic: STAGE_3
- `projects:reactivated` → Topic: STAGE_3
- `mentions:new` → Topic: MENTIONS
- `discovery:complete` → Topic: MENTIONS

### Class: `TelegramHigh`

| Method | Purpose |
|---|---|
| `drain_redis()` | Pull all pubsub messages into unlimited deque |
| `send_message(topic_id, text, buttons, max_retries)` | POST with up to 3 retries + 429 handling |
| `format_message(channel, data)` | Route to correct formatter, return `(topic_id, text, buttons)` |
| `process_one()` | Pop and send; re-queue on rate limit |
| `run()` | Main 50ms tick loop |

---

## services/telegram-chains/main.py — Telegram Chains Bot

**Purpose:** Sends project confirmations and monitoring updates to chain-specific Telegram groups. Two-queue system.

### Routing
- `projects:confirmed:{chain}` → **ALL channel** (new projects to everyone)
- `projects:monitored:{chain}` → **UPDATES channel** (dedicated channel)

### Class: `ChainMessageSender`

| Method | Purpose |
|---|---|
| `add_message(msg_type, message, buttons)` | Queue message to `confirmed` or `monitored` queue |
| `send_message(chat_id, message, buttons)` | POST to Telegram |
| `process_queues()` | Drain queues at 1s rate limit per queue |
| `start()` | Start sender thread |

### Message Format
- **Confirmed:** Full project card with: source badge, chain, handle, followers, account date, KF stats, bio, token info, launch date, AI summary
- **Monitored (Update):** Compact update card with status, launch info, changes summary

### Key Functions

| Function | Purpose |
|---|---|
| `format_message(data, channel)` | Route to confirmed or monitored template |
| `format_token_info(data)` | Show `Name $TICKER` or `Name (Possible: $X, $Y)` |
| `format_launch_info(data)` | Show `"Dec 14, 2025 (3 days)"` with platform |
| `format_discovery_source(data)` | Badge: `🎯 ALPHAGATE`, `👤 ALPHA FOLLOWERS`, `🔍 COLLECTOR` |
| `create_buttons(handle)` | 4-button keyboard: Profile, Alphagate, LIKE, Stop Track |

---

## services/telegram-chains-callback/main.py — Chains Callback Receiver

**Purpose:** Long-polls Telegram for button callbacks and commands on chain bot messages. Handles Favorite toggle and Stop Monitoring.

### Handlers

| Handler | Trigger | Action |
|---|---|---|
| `handle_favorite(cb, handle)` | `fav:{handle}` callback | Toggle like in DB, update message text with liked-by list |
| `handle_stop(cb, handle)` | `stop:{handle}` callback | Call `stop_monitoring_by_handle(handle)`, confirm in chat |
| `handle_command(message)` | `/likes`, `/remove` commands | Placeholder (not fully implemented) |

### Functions

| Function | Purpose |
|---|---|
| `build_likes_line(favorites)` | Format `"❤️ Liked by @user1, @user2"` |
| `update_likes_in_text(text, favorites)` | Splice likes line into existing message text |
| `poll()` | Main long-poll loop with consecutive-error backoff |

---

## services/telegram-bot/main.py — Interactive Bot

**Purpose:** Multi-step `/add` command for manually adding projects to the monitoring pipeline. Also handles `fav:` and `stop:` callbacks.

### Handlers

| Command/Callback | Action |
|---|---|
| `/add` | Step 1: ask for Twitter handle |
| (handle input) | Step 2: ask for summary |
| (summary input) | Step 3: ask for monitor level |
| `level:{level}` | Save: create triage stub, add to monitoring |
| `fav:{handle}` | Add to favorites DB |
| `stop:{handle}` | Stop monitoring this handle |

### State Machine
Uses `add_requests` table in `agent.db` (keyed by `chat_id + user_id`):
- `upsert_add_request(chat_id, user_id, step, ...)` — save state
- `get_add_request(chat_id, user_id)` — retrieve state
- `clear_add_request(chat_id, user_id)` — clean up after completion

### Functions

| Function | Purpose |
|---|---|
| `poll()` | Main long-poll loop |
| `handle_callback(cb)` | Route `fav:` / `stop:` / `level:` callbacks |
| `handle_message(message)` | Route text input through `/add` state machine |

---

## services/telegram/main.py — Legacy Unified Telegram Service

**Purpose:** Original single-service Telegram notifier (before the split into `telegram-high`/`telegram-low`/`telegram-chains`). Subscribes to all 14 channels. Still operational as fallback or parallel sender.

### Queue Priority
- `high_queue` — **unlimited**, never drop: confirmed, rejected, monitored, alert, launched, abandoned, mentions, discovery
- `low_queue` — **maxlen=50**, can drop: collected, triaged, fingerprints

### Class: `TelegramNotifier`

| Method | Purpose |
|---|---|
| `run()` | Main 50ms drain-then-send loop |
| `drain_redis()` | Pull all pubsub messages into appropriate queue |
| `send_message(text, buttons)` | POST to Telegram with 429 rate-limit handling |
| `format_message(channel, data)` | Route to formatter |

---

## services/telegram/formatter.py — Message Formatter

**Purpose:** All Telegram message formatters. Returns `(text: str, buttons: list)` tuples.

### Functions

| Function | Channel | Output |
|---|---|---|
| `format_tweet_collected(data)` | `tweets:collected` | Stage 0 collection notification |
| `format_project_triaged(data)` | `projects:triaged` | Stage 1 confirmation |
| `format_tweet_rejected(data)` | `triage:rejected` | Rejection with reason |
| `format_mention_detected(data)` | `mentions:new` | Influencer mention card |
| `format_project_discovered(data)` | `discovery:complete` | Discovery result card |
| `format_project_confirmed(data)` | `projects:confirmed` | Stage 2 full verification card |
| `format_project_rejected_verification(data)` | `projects:rejected` | Stage 2 rejection |
| `format_project_monitored(data)` | `projects:monitored` | Stage 3 routine update |
| `format_launch_alert(data)` | `projects:alert` | Urgent launch warning |
| `format_project_launched(data)` | `projects:launched` | CA detected announcement |
| `format_project_abandoned(data)` | `projects:abandoned` | Inactivity warning |
| `format_project_removed(data)` | `projects:removed` | Final removal notice |
| `format_project_reactivated(data)` | `projects:reactivated` | Reactivation notice |
| `format_fingerprint(data)` | `fingerprint:new` | AI decision audit record |

All messages use HTML parse mode. Buttons are inline keyboard arrays using Telegram Bot API format.
