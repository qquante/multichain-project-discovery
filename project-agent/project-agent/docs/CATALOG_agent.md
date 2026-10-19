# CATALOG: agent/

The `agent/` module is the AI brain of the system. It contains all LLM-powered analysis logic, database operations, and shared utilities used across the 3-stage pipeline.

---

## agent/main.py — CLI Entry Point

**Purpose:** Command-line runner and display utility for all 3 pipeline stages. Also defines `MONITOR_INTERVALS` used by `agent/database.py`.

### Functions

| Function | Purpose | Inputs | Outputs |
|---|---|---|---|
| `run_analysis()` | Run Stage 1 (Triage) batch | none | processes pending tweets |
| `run_verification()` | Run Stage 2 (Verification) batch | none | processes pending verifications |
| `run_monitoring()` | Run Stage 3 (Monitor) cycle | none | checks active monitoring queue |
| `show_pending()` | Print pending tweets table | none | console output |
| `show_triaged()` | Print triaged projects table | none | console output |
| `show_verified()` | Print verified projects table | none | console output |
| `show_monitoring_queue()` | Print projects in monitoring | none | console output |
| `show_project_journey(handle)` | Print full audit trail for one project | `handle: str` | console output |
| `show_fingerprints(handle)` | Print AI decision fingerprints | `handle: str` (optional) | console output |

---

## agent/analyzer.py — Stage 1: Triage

**Purpose:** `TweetAnalyzer` class. Classifies raw tweets to determine if they represent a pre-launch crypto project. Uses a two-step LLM pipeline.

### Decision Tree (4 cases)

1. **Reject** — not a project, publish to `triage:rejected`
2. **has_ca** — tweet contains a contract address, reject with CA reason
3. **mention_saved** — author is NOT the project, save mention and publish to `mentions:new`
4. **triaged** — author IS the project, save to `triaged_projects` and publish to `projects:triaged`

### Class: `TweetAnalyzer`

| Method | Purpose | Inputs | Outputs |
|---|---|---|---|
| `__init__(verbose)` | Init with OpenRouter client | `verbose: bool` | — |
| `analyze_tweet(tweet)` | Full analysis of one tweet (4-case tree) | `tweet: dict` | `result: dict` or `None` |
| `_call_classifier(tweet_data)` | Step 1 LLM: is it a project? who is author? | `tweet_data: dict` | classifier JSON dict |
| `_call_extractor(tweet_data, classifier_result)` | Step 2 LLM: extract full project details | `tweet_data: dict, classifier_result: dict` | extractor JSON dict |
| `_validate_mentions_from_api(result, tweet)` | Override LLM mention decisions with real Twitter entity data | `result: dict, tweet: dict` | `result: dict` (modified) |
| `analyze_batch(limit)` | Process multiple pending tweets | `limit: int` | count processed |
| `run()` | Continuous loop calling `analyze_batch` | none | loop |

---

## agent/verifier.py — Stage 2: Verification

**Purpose:** `ProjectVerifier` class. Deep-verifies triaged projects by fetching full user profile, website content, AlphaGate data, then running an LLM.

### Class: `ProjectVerifier`

| Method | Purpose | Inputs | Outputs |
|---|---|---|---|
| `__init__()` | Init clients (Twitter, OpenRouter, AlphaGate, WebsiteReader) | — | — |
| `verify_project(triage_data)` | Full verification pipeline for one project | `triage_data: dict` | `result: dict` |
| `fetch_user_data(handle, author_id)` | Fetch profile + tweets (including pinned tweet) via Twitter API | `handle: str, author_id: str` | `user_info: dict, tweets: list` |
| `is_project_launched(user_info, tweets, pinned)` | Pre-LLM CA check using regex | `user_info: dict, tweets: list, pinned: dict` | `bool` |
| `_call_llm(prompt)` | Call OpenRouter with full verification prompt | `prompt: str` | LLM response dict |

**Key behavior:** If CA detected pre-LLM → project is immediately marked `rejected/launched`. Otherwise LLM verdict determines `confirmed` or `rejected`. On confirm: publishes to `projects:confirmed` and chain-specific channel. Saves fingerprint.

---

## agent/monitor.py — Stage 3: Monitoring

**Purpose:** `ProjectMonitor` class. Continuously monitors verified projects for CA detection, follower changes, activity drops, and launch date updates.

### Class: `ProjectMonitor`

| Method | Purpose | Inputs | Outputs |
|---|---|---|---|
| `__init__()` | Init clients | — | — |
| `monitor_project(project)` | Full monitoring cycle for one project | `project: dict` | `result: dict` |
| `run_monitoring_cycle()` | Activate confirmed projects + process queue | — | count processed |
| `parse_launch_date(date_str)` | Parse many date formats to `datetime` | `date_str: str` | `datetime` or `None` |
| `is_launch_date_in_future(date_str)` | Check if date is future | `date_str: str` | `bool` |
| `is_launch_date_passed(date_str)` | Check if date has passed | `date_str: str` | `bool` |

**Output channels:**
- `projects:launched` — CA found
- `projects:abandoned` — no activity for N days
- `projects:alert` — launch date approaching
- `projects:monitored` + `projects:monitored:{chain}` — routine update

---

## agent/discoverer.py — Discovery Pipeline

**Purpose:** `ProjectDiscoverer` class. Investigates Twitter handles mentioned by influencers to identify undiscovered projects.

### Class: `ProjectDiscoverer`

| Method | Purpose | Inputs | Outputs |
|---|---|---|---|
| `__init__()` | Init clients | — | — |
| `investigate_handle(handle, mentions)` | Fetch tweets/profile, run LLM, save if confirmed | `handle: str, mentions: list` | `result: dict` |
| `run_discovery_cycle(min_mentions, limit)` | Pull handles from DB, investigate each | `min_mentions: int, limit: int` | count investigated |

---

## agent/api_client.py — OpenRouter LLM Client

**Purpose:** HTTP client wrapping the OpenRouter API for all LLM calls.

### Constants
- `MODEL = "google/gemini-2.5-flash-lite"` — model for all AI decisions
- `OPENROUTER_API_KEY` — hardcoded API key

### Class: `OpenRouterClient`

| Method | Purpose | Inputs | Outputs |
|---|---|---|---|
| `chat(messages, system)` | Send chat request with retry/exponential backoff | `messages: list, system: str` | response text |
| `parse_json_response(text)` | Extract JSON from markdown code blocks | `text: str` | `dict` |

**Config:** Forces `response_format: json_object`. Retries up to 3 times with exponential backoff.

---

## agent/database.py — Agent DB (agent.db)

**Purpose:** All SQLite CRUD operations for `agent.db`. Also handles dual-write to Supabase.

### Database Tables

| Table | Purpose |
|---|---|
| `processed_tweets` | Dedup — every tweet that passed through Stage 1 |
| `triaged_projects` | Stage 1 output — unique projects by `twitter_handle` |
| `verified_projects` | Stage 2 output — full verification data + Stage 3 monitoring fields |
| `monitoring_history` | Stage 3 audit trail — one row per monitoring cycle per project |
| `verification_queue` | Queue table for pending verifications |
| `decision_fingerprints` | Full AI decision audit trail with inputs, reasoning, key factors |
| `mentions` | Influencer mentions of project handles |
| `project_favorites` | User favorites from Telegram bot |
| `add_requests` | Multi-step `/add` command state for Telegram bot |
| `launch_calendar` | Detected launch dates per project |

### Key Functions

| Function | Purpose | Inputs | Outputs |
|---|---|---|---|
| `init_db()` | Create all tables + run migrations | — | — |
| `is_tweet_processed(tweet_id)` | Dedup check | `tweet_id: str` | `bool` |
| `is_handle_triaged(handle)` | Check if handle in triage | `handle: str` | `bool` |
| `mark_tweet_processed(tweet_id, is_project, confidence, reason, raw)` | Mark tweet done | args | — |
| `save_triage_result(result)` | Save Stage 1 output, dual-write to Supabase | `result: dict` | `bool` (True if saved, False if duplicate) |
| `get_pending_tweets(limit)` | Get tweets not yet processed | `limit: int` | `list[dict]` |
| `save_verification_result(result)` | Save Stage 2 output | `result: dict` | — |
| `get_projects_for_monitoring()` | Get `active` monitoring queue | — | `list[dict]` |
| `save_monitoring_history(data)` | Append Stage 3 cycle record | `data: dict` | — |
| `save_fingerprint(data)` | Save AI decision fingerprint | `data: dict` | — |
| `get_fingerprints(handle, stage, limit)` | Query fingerprints | args | `list[dict]` |
| `_sync_to_supabase(table, data)` | Dual-write one record | `table: str, data: dict` | — |

### `MONITOR_INTERVALS` Dict
Priority → check interval in hours:
- `critical` → 1h
- `high` → 2h
- `medium` → 4h
- `low` → 12h

---

## agent/prompts.py — LLM Prompt Templates

**Purpose:** All prompt templates for Stages 1–3 pipeline.

| Function | Purpose | Returns |
|---|---|---|
| `get_system_prompt()` | Stage 1 triage system prompt | `str` |
| `get_verification_system_prompt()` | Stage 2 verification system prompt | `str` |
| `get_monitor_system_prompt()` | Stage 3 monitoring system prompt | `str` |
| `build_verification_prompt(triage, user_info, tweets, pinned, alphagate)` | Build full Stage 2 user prompt | `str` |
| `build_monitor_prompt(project, user_info, tweets)` | Build Stage 3 user prompt | `str` |
| `build_user_prompt(tweet_data)` | Build Stage 1 user prompt | `str` |

---

## agent/prompts_stage1.py — Specialized Stage 1 Prompts

**Purpose:** Two separate LLM calls for Stage 1 — classifier then extractor.

| Function/Constant | Purpose |
|---|---|
| `get_classifier_system_prompt()` | System prompt for Step 1 (is it a project? who is author?) |
| `CLASSIFIER_USER_PROMPT` | Template for classifier user turn |
| `build_classifier_prompt(tweet_data)` | Build complete classifier input dict |
| `get_extractor_system_prompt()` | System prompt for Step 2 (extract full details) |
| `EXTRACTOR_USER_PROMPT` | Template for extractor user turn |
| `build_extractor_prompt(tweet_data)` | Build complete extractor input dict |

---

## agent/alphagate_client.py — AlphaGate API Client

**Purpose:** Enriches projects with social signal data from AlphaGate: key followers, alpha hunters (traders), bio/username change alerts.

### Class: `AlphaGateClient`

| Method | Purpose | Inputs | Outputs |
|---|---|---|---|
| `get_alerts(username)` | Bio/username/website change alerts | `username: str` | `list[dict]` |
| `get_first_followers(twitter_id)` | Key followers who followed early | `twitter_id: str` | `list[dict]` |
| `get_alpha_hunters(username, twitter_id)` | Alpha traders following the project | `username: str, twitter_id: str` | `list[dict]` |
| `enrich_project(username, twitter_id)` | Combine all 3 endpoints into one enrichment dict | `username: str, twitter_id: str` | `dict` |

### Helper Functions

| Function | Purpose |
|---|---|
| `format_key_followers_html(followers)` | Format key followers list as HTML |
| `format_alpha_hunters_html(hunters)` | Format alpha hunters list as HTML |

---

## agent/ca_detector.py — Contract Address Detector

**Purpose:** Regex-based pre-LLM detection of on-chain contract addresses in text.

### Patterns
- `EVM_PATTERN` — `0x` + 40 hex chars (Ethereum, BSC, Base, etc.)
- `SOLANA_PATTERN` — Base58 32-44 char string
- `BTC_SEGWIT_PATTERN` — `bc1` prefix
- `TRON_PATTERN` — `T` + 33 alphanumeric chars
- `TON_PATTERN` — `EQ` or `UQ` prefix

### Functions

| Function | Purpose | Inputs | Outputs |
|---|---|---|---|
| `detect_ca(text)` | Find CA in any text | `text: str` | `(found: bool, address: str, chain: str)` |
| `is_project_launched(bio, tweets, pinned_tweet)` | Alias used by verifier — check bio + all tweet text | `bio: str, tweets: list, pinned_tweet: dict` | `bool` |

---

## agent/calendar_agent.py — Launch Calendar Agent

**Purpose:** `CalendarAgent` class. Extracts launch dates from projects and saves to `launch_calendar` table. AI summary is in Portuguese (PT-BR).

### Class: `CalendarAgent`

| Method | Purpose | Inputs | Outputs |
|---|---|---|---|
| `analyze_project(handle, project_data, tweets)` | LLM analysis to extract launch date + ticker | `handle: str, project_data: dict, tweets: list` | `dict` |
| `save_analysis(handle, analysis, project_data)` | Save to `launch_calendar` table | args | — |
| `generate_project_summary(project_data, tweets)` | Generate ≤65-word PT-BR summary | `project_data: dict, tweets: list` | `str` |

### Standalone Function

| Function | Purpose |
|---|---|
| `run_calendar_analysis(handle, project_data, tweets)` | Run `analyze_project` + `save_analysis` in one call |

---

## agent/chain_utils.py — Chain Mapping Utilities

**Purpose:** Shared mapping of chain names to canonical groups and emojis.

### Data
- `CHAIN_MAP: dict` — maps aliases (e.g., `"bnb"`, `"binance"`) to standard group key (e.g., `"bsc"`)
- `CHAIN_EMOJIS: dict` — maps chain group to emoji

### Functions

| Function | Purpose | Inputs | Outputs |
|---|---|---|---|
| `get_chain_group(chain)` | Normalize chain name to standard key | `chain: str` | `str` (e.g., `"solana"`, `"bsc"`) |
| `get_chain_emoji(chain)` | Get display emoji for chain | `chain: str` | emoji `str` |
| `get_chain_channel(chain, type)` | Build Redis channel name | `chain: str, type: str` | e.g., `"projects:confirmed:solana"` |

---

## agent/twitter_cache.py — Twitter Cache

**Purpose:** TTL-based cache for Twitter API results stored in `users.db`. Avoids redundant API calls during monitoring cycles.

### Functions

| Function | Purpose | Inputs | Outputs |
|---|---|---|---|
| `get_or_fetch_user_tweets(client, handle, author_id, ttl_hours, include_replies)` | Return cached tweets or fetch fresh | `client, handle: str, author_id: str, ttl_hours: float` | `dict` with `tweets` list |
| `get_or_fetch_user_info(client, author_id, handle, ttl_hours)` | Return cached user info or fetch fresh | `client, author_id: str, handle: str, ttl_hours: float` | `dict` |

**Cache key:** `id:{author_id}` if `author_id` provided, else `handle:{handle}`.

---

## agent/website_reader.py — Website Reader

**Purpose:** `WebsiteReader` class. Reads project websites via Jina AI reader prefix to extract structured content.

### Class: `WebsiteReader`

| Method | Purpose | Inputs | Outputs |
|---|---|---|---|
| `read_url(url)` | Fetch page via `https://r.jina.ai/{url}` | `url: str` | `str` content |
| `find_project_website(user_info, tweets)` | Find best URL: bio links first, then tweet links | `user_info: dict, tweets: list` | `str` URL or `None` |
| `extract_site_info(content)` | Parse title, description, social links, CA patterns | `content: str` | `dict` |
