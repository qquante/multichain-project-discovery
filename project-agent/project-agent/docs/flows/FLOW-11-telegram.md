# FLOW-11: Telegram Output Layer

**Services:** `telegram-low`, `telegram-high`, `telegram-chains`, `telegram-chains-callback`, `telegram-bot`  
**Formatter:** `services/telegram/formatter.py` (shared between telegram-low and telegram-high)  
**Verified against code.**

---

## Overview

5 separate Telegram bots handle different message priorities and interaction types. All subscribe to Redis channels, format messages, and send via Telegram Bot API with inline rate-limiting and retry logic.

---

## Bot Architecture

```
telegram-low  ─── Stages 0+1 (low priority, droppable)
telegram-high ─── Stages 2+3 + mentions (NEVER drop, unlimited queue)
telegram-chains ─── Chain-specific groups (new projects + updates)
telegram-chains-callback ─── ❤️ LIKE / 🛑 Stop buttons on chain messages
telegram-bot ─── /add command (manual project injection)
```

---

## Bot 1: telegram-low

**File:** [services/telegram-low/main.py](../../services/telegram-low/main.py)

| Config | Value |
|---|---|
| Queue | `deque(maxlen=100)` — drops oldest when full |
| Rate limit | 1.0s between sends |
| Retry | 3 attempts, exponential backoff on 500/timeout |
| 429 handling | reads `retry_after` param, pauses, **re-queues** message |

**Subscriptions:**

| Channel | Topic | Formatter |
|---|---|---|
| `tweets:collected` | `TOPIC_STAGE_0` (#stage-0) | `format_tweet_collected()` |
| `projects:triaged` | `TOPIC_STAGE_1` (#stage-1) | `format_project_triaged()` |
| `triage:rejected` | `TOPIC_STAGE_1` (#stage-1) | `format_tweet_rejected()` |
| `fingerprint:new` | `TOPIC_FINGERPRINTS` (#fingerprints) | `format_fingerprint()` |

**Loop:** drain all Redis messages into queue → process one per 1s → log stats every 60s.

---

## Bot 2: telegram-high

**File:** [services/telegram-high/main.py](../../services/telegram-high/main.py)

| Config | Value |
|---|---|
| Queue | `deque()` — **UNLIMITED** — never drops |
| Rate limit | 1.0s between sends |
| Retry | 3 attempts, exponential backoff |
| 429 handling | re-queues message (never drops) |

**Subscriptions:**

| Channel | Topic | Formatter |
|---|---|---|
| `projects:confirmed` | `TOPIC_STAGE_2` | `format_project_confirmed()` |
| `projects:rejected` | `TOPIC_STAGE_2` | `format_project_rejected_verification()` |
| `projects:monitored` | `TOPIC_STAGE_3` | `format_project_monitored()` |
| `projects:alert` | `TOPIC_STAGE_3` | `format_launch_alert()` |
| `projects:launched` | `TOPIC_STAGE_3` | `format_project_launched()` |
| `projects:abandoned` | `TOPIC_STAGE_3` | `format_project_abandoned()` |
| `projects:removed` | `TOPIC_STAGE_3` | `format_project_removed()` |
| `projects:reactivated` | `TOPIC_STAGE_3` | `format_project_reactivated()` |
| `mentions:new` | `TOPIC_MENTIONS` | `format_mention_detected()` |
| `discovery:complete` | `TOPIC_MENTIONS` | `format_project_discovered()` |

**Loop:** drain all Redis → process one per 1s → log stats every 30s.

Both bots target same `GROUP_ID` (supergroup). `message_thread_id` routes to topic.

---

## Bot 3: telegram-chains

**File:** [services/telegram-chains/main.py](../../services/telegram-chains/main.py)

Async service. Subscribes to 16 chain-specific channels:
- `projects:confirmed:{chain}` × 8 chains
- `projects:monitored:{chain}` × 8 chains

**Routing (simplified since refactor):**

| Message type | Destination |
|---|---|
| `confirmed` (new project) | `CHAT_ID_ALL` env var |
| `monitored` (update) | `CHAT_ID_UPDATES` = `-1003541521775` (hardcoded) |

Chain-specific routing via `CHAIN_CHAT_IDS` dict still exists but not used for primary routing.

**Buttons on every message:**
```
[👤 Profile]  [🎯 Alphagate]  [❤️ LIKE]  [🛑 Stop Track]
```

`LIKE` / `Stop Track` callbacks handled by `telegram-chains-callback` service.

**New project message format:**
```
🟢 NEW PROJECT [🎯 ALPHAGATE]

🌎 FROM: AlphaGate Discovery
🟣 CHAIN: SOLANA

━━━━━━━━━━━━━━━━━━

👤 Twitter: @handle ✅
🫂 Followers: 1,234
📅 Created at: Feb 15, 2024
⭐️ Key Followers: 5 (KF: 5 | H: 2 | WR: 75.0%)

📋 Bio: ...

🔑 Token: <b>ProjectName</b> <b>$TICK</b>
🎒 Type: defi

🚀 Launch at: Jan 15, 2025 (5 days)

💬 <i>PT-BR AI summary here</i>
```

---

## Bot 4: telegram-chains-callback

**File:** [services/telegram-chains-callback/main.py](../../services/telegram-chains-callback/main.py)

Long-polling `getUpdates`. Handles callbacks from chain group buttons.

| Callback | Handler | DB write |
|---|---|---|
| `fav:{handle}` | Toggle like/unlike | `project_favorites` table |
| `stop:{handle}` | Stop monitoring | `verified_projects.monitoring_status='stopped'` |

On LIKE: edits original message to add/update `❤️ Liked by @user1, @user2` line.  
Toggle: if already liked → remove. Otherwise → add.

Uses `TELEGRAM_BOT_TOKEN_CHAINS` env (can fall back to `TELEGRAM_BOT_TOKEN`).

---

## Bot 5: telegram-bot (interactive)

**File:** [services/telegram-bot/main.py](../../services/telegram-bot/main.py)

Long-polling `getUpdates`. Multi-step `/add` command flow.

**`/add` flow:**

```
Step 1: /add command
  → "Send the project's Twitter handle"
  
Step 2: User sends @handle
  → upsert_add_request(step='summary')
  → "Send a summary/reason"

Step 3: User sends summary text
  → upsert_add_request(step='level')
  → Show inline keyboard: [Critical] [High] [Medium] [Low]

Step 4: User taps priority level
  → save_triage_result() with discovery_source='manual_add'
  → "Project @handle added for triage (level=high)"
  → clear_add_request()
```

State persisted in `add_requests` table across messages.  
Manual adds enter pipeline at Stage 2 (same as alpha-followers stubs).

---

## Common Patterns

### Rate limiting
All bots: minimum 1.0s between sends. On 429: read `retry_after` from response, set cooldown.

### 400 handling
On HTTP 400 (bad HTML): retry without `parse_mode` (plain text fallback).

### Retry with backoff
On 500 or network error: up to 3 attempts with `attempt * 2` second delay.

### Message routing
All group bots use `message_thread_id` for Telegram supergroup topics.  
Calendar alerter uses separate `TELEGRAM_ALERT_CHAT_ID` directly.

---

## Redis Channels Summary

| Channel | Bot(s) that subscribe |
|---|---|
| `tweets:collected` | telegram-low |
| `projects:triaged` | telegram-low |
| `triage:rejected` | telegram-low |
| `fingerprint:new` | telegram-low |
| `projects:confirmed` | telegram-high |
| `projects:rejected` | telegram-high |
| `projects:monitored` | telegram-high |
| `projects:alert` | telegram-high |
| `projects:launched` | telegram-high |
| `projects:abandoned` | telegram-high |
| `projects:removed` | telegram-high |
| `projects:reactivated` | telegram-high |
| `mentions:new` | telegram-high |
| `discovery:complete` | telegram-high |
| `projects:confirmed:{chain}` | telegram-chains |
| `projects:monitored:{chain}` | telegram-chains |
