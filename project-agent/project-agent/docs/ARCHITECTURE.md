# ARCHITECTURE: Crypto Project Intelligence Pipeline

A fully automated system that detects pre-launch crypto projects from Twitter before their tokens launch, verifies them through a 3-stage AI pipeline, and delivers alerts to Telegram.

---

## System Overview

```
TWITTER API
     │
     ├──[Keyword Search]──────→ tweets.db
     ├──[Alpha Callers]─────── tweets.db
     └──[AlphaGate API]────────────────────────────────→ triaged_projects
     └──[Alpha Followers]──→ tweets.db
                                  │
                                  ▼
                           ┌─────────────┐
                           │  STAGE 1    │
                           │  TRIAGE     │  ← TweetAnalyzer (2-step LLM)
                           └──────┬──────┘
                                  │
                    ┌─────────────┼──────────────┐
                    ▼             ▼               ▼
              triaged_projects  mentions      rejected
                    │             │
                    ▼             ▼
             ┌─────────────┐  discoverer
             │  STAGE 2    │  (investigates
             │  VERIFIER   │   @handles)
             └──────┬──────┘
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
    verified_projects    rejected
          │
          ▼
   ┌─────────────┐
   │  STAGE 3    │
   │  MONITOR    │  ← Runs on schedule (1h–12h by priority)
   └──────┬──────┘
          │
   ┌──────┴───────────────────────────────┐
   │              │              │        │
   ▼              ▼              ▼        ▼
launched      abandoned       alert    update

                    ALL EVENTS → Redis Pub/Sub → Telegram Bots
```

---

## Data Flow: Collection → Analysis → Telegram

### Phase 0: Collection (tweets.db)

**Services:** `collector`, `alpha-hunter`, `alpha-followers`, `alphagate`

1. `collector` runs every 3h, iterates 18 keyword batches
2. For each batch: `BatchCollector.collect_batch()` → paginates Twitter search
3. Each new tweet saved to `tweets.db` (with Supabase dual-write)
4. Publishes `tweets:collected` (one per tweet) and `tweets:new` (batch notification)
5. `alpha-hunter` fetches tweets from alpha callers, saves to `tweets.db`
6. `alpha-followers` fetches followings of 17 seed traders → inserts triage stubs directly to `agent.db`
7. `alphagate` fetches pre-filtered projects from AlphaGate API → saves directly to `triaged_projects` (bypasses Stage 1 LLM)

### Phase 1: Triage (Stage 1)

**Service:** `triage`  
**Input:** `tweets:new` Redis notification + periodic DB poll (every 10s)  
**Core logic:** `agent/analyzer.py TweetAnalyzer`

Two-step LLM pipeline per tweet:

```
Tweet text + author info
        │
        ▼
  CLASSIFIER LLM
  (is it a project? is author the project or a shill?)
        │
        ├── reject → mark processed, publish to triage:rejected
        └── is_project
                │
                ├── has_ca (contract address in tweet) → reject
                ├── author is influencer (not project) → save mention, publish mentions:new
                └── author IS the project
                        │
                        ▼
                  EXTRACTOR LLM
                  (extract: name, ticker, chain, launch date, links, signals)
                        │
                        ▼
                  save to triaged_projects
                  publish to projects:triaged
```

**CA Detection:** `ca_detector.py` runs regex BEFORE LLM. If CA found → skip LLM entirely.

**Mention validation:** `_validate_mentions_from_api()` overrides LLM mention decisions using real Twitter entity data in the tweet payload.

**Fingerprint:** Every decision (accept/reject/mention) saved to `decision_fingerprints`.

### Phase 2: Verification (Stage 2)

**Service:** `verifier`  
**Input:** `projects:triaged` Redis notification + periodic DB poll (every 30s)  
**Core logic:** `agent/verifier.py ProjectVerifier`

```
triaged project data
        │
        ▼
  Fetch Twitter profile + tweets (including pinned)
        │
        ▼
  Fetch AlphaGate enrichment (key followers, alpha hunters, alerts)
        │
        ▼
  Pre-LLM CA check (ca_detector.py)
  If CA found → immediately reject (already launched)
        │
        ▼
  Fetch website via Jina AI reader
  Extract: title, description, social links, contract patterns
        │
        ▼
  VERIFICATION LLM
  (full profile + tweets + site + AlphaGate context)
  Decision: confirmed / rejected
        │
        ├── rejected → save to verified_projects(rejected)
        │              publish to projects:rejected
        │
        └── confirmed → CalendarAgent (extract launch date)
                        generate PT-BR AI summary
                        save to verified_projects(confirmed)
                        publish to projects:confirmed
                        publish to projects:confirmed:{chain}
```

### Phase 3: Monitoring (Stage 3)

**Service:** `monitor`  
**Trigger:** `projects:confirmed` subscription + priority schedule  
**Core logic:** `agent/monitor.py ProjectMonitor`

Priority-based check intervals:
- `critical` → every 1 hour
- `high` → every 2 hours
- `medium` → every 4 hours
- `low` → every 12 hours

```
For each due project:
        │
        ▼
  Fetch latest tweets + user_info (via twitter_cache TTL)
  Fetch AlphaGate enrichment
        │
        ▼
  MONITORING LLM
  (analyze: CA?, follower growth, activity, launch signals)
        │
        ├── CA detected
        │       → update launch_calendar (silent)
        │       → publish projects:launched
        │
        ├── inactive N+ days (no tweets)
        │       → status = abandoned
        │       → publish projects:abandoned
        │
        ├── launch date approaching
        │       → publish projects:alert
        │
        └── routine update
                → publish projects:monitored
                → publish projects:monitored:{chain}
```

**Abandoned checker:** Separate service runs every 7 days. After 30 days silence → `status = removed`.

### Discovery Pipeline

**Service:** `discoverer`  
**Runs:** Every 30 minutes

```
mentions table (unprocessed)
        │
        ▼
  For each mentioned @handle:
        │
        ▼
  Fetch their tweets + profile
        │
        ▼
  DISCOVERY LLM
  (is this handle a pre-launch project?)
        │
        ├── yes → save to triaged_projects → enters Stage 2
        └── no  → mark as investigated
        │
        ▼
  publish to discovery:complete
```

---

## Redis Pub/Sub Channel Map

| Channel | Published By | Consumed By |
|---|---|---|
| `tweets:collected` | collector, alpha-hunter | telegram-low (Stage 0) |
| `tweets:new` | collector, alpha-followers | triage service |
| `projects:triaged` | triage, alphagate | verifier, telegram-low |
| `triage:rejected` | triage | telegram-low |
| `mentions:new` | triage | telegram-high |
| `fingerprint:new` | triage, verifier | telegram-low |
| `projects:confirmed` | verifier | monitor, telegram-high |
| `projects:confirmed:{chain}` | verifier | telegram-chains |
| `projects:rejected` | verifier | telegram-high |
| `projects:monitored` | monitor | telegram-high |
| `projects:monitored:{chain}` | monitor | telegram-chains |
| `projects:launched` | monitor | telegram-high |
| `projects:abandoned` | monitor | telegram-high |
| `projects:alert` | monitor | telegram-high |
| `projects:reactivated` | abandoned-checker | telegram-high |
| `projects:removed` | abandoned-checker | telegram-high |
| `discovery:complete` | discoverer | telegram-high |
| `monitor:delete` | telegram-bot | monitor |
| `calendar:alert:{type}` | calendar-alerter | (informational) |

---

## Telegram Bot Architecture

Three separate bots handle different message priorities:

```
telegram-low  (Bot 1 — can drop)
├── tweets:collected    → #stage-0
├── projects:triaged    → #stage-1
├── triage:rejected     → #stage-1
└── fingerprint:new     → #fingerprints

telegram-high  (Bot 2 — NEVER drop, unlimited queue)
├── projects:confirmed  → #stage-2
├── projects:rejected   → #stage-2
├── projects:monitored  → #stage-3
├── projects:alert      → #stage-3
├── projects:launched   → #stage-3
├── projects:abandoned  → #stage-3
├── projects:removed    → #stage-3
├── projects:reactivated→ #stage-3
├── mentions:new        → #mentions
└── discovery:complete  → #mentions

telegram-chains  (Bot 3 — chain groups)
├── projects:confirmed:{chain}  → ALL channel (new projects)
└── projects:monitored:{chain}  → UPDATES channel

telegram-chains-callback
└── handles ❤️ LIKE / 🛑 Stop Track buttons on chain bot messages

telegram-bot (interactive)
└── /add command (multi-step: handle → summary → monitor level)
```

---

## Database Architecture

```
tweets.db          users.db           agent.db
─────────          ────────           ────────
tweets             user_tweets        processed_tweets
query_state        user_fetch_state   triaged_projects
quoted_tweets      alpha_followings   verified_projects
keyword_batches    twitter_cache      monitoring_history
collection_history                    verification_queue
                                      decision_fingerprints
                                      mentions
                                      project_favorites
                                      add_requests
                                      launch_calendar
       │                │                    │
       └────────────────┴────────────────────┘
                         │
                    Supabase PostgreSQL
                    (dual-write via db/supabase_client.py)
```

**Dual-write pattern:** Every SQLite INSERT is followed by a fire-and-forget Supabase upsert. Supabase failures are non-blocking. Local SQLite is always the source of truth.

---

## External API Dependencies

| API | Purpose | Used By |
|---|---|---|
| Twitter API (twitterapi.io) | Tweet search, user profiles, followings | `tweets/api_client.py`, `users/api_client.py` |
| OpenRouter (gemini-2.5-flash-lite) | All LLM decisions (Stages 1–3, discovery) | `agent/api_client.py` |
| AlphaGate API | Key followers, alpha hunters, bio change alerts | `agent/alphagate_client.py`, `services/alphagate/` |
| Jina AI Reader | Website content extraction | `agent/website_reader.py` |
| Supabase REST API | Cloud PostgreSQL dual-write | `db/supabase_client.py` |
| Telegram Bot API | Message delivery, button callbacks, long-polling | All `services/telegram*` |

---

## Project Lifecycle State Machine

```
tweet discovered
       ↓
triaged (Stage 1 confirmed)
       ↓
verified / confirmed (Stage 2)
       ↓
monitoring:active (Stage 3)
       ↓
  ┌────┼────────┐
  ▼    ▼        ▼
launched abandoned alert
         ↓
    [7 days]
         ↓
    removed (30+ days silence)
         OR
    reactivated (if posts again)
```

**Discovery override:** `discoverer` can inject projects at the `triaged` stage for any influencer-mentioned handle.

---

## Docker Compose Services

From `docker-compose.yml`, all services share:
- A Redis instance at `redis://redis:6388`
- Mounted `data/` volume for SQLite databases
- Shared `/app` working directory
- Environment variables for API keys, Telegram tokens, chat IDs
