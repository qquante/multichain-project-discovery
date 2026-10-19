# FLOW-7: Stage 3 — Monitor

**Service:** `services/monitor/main.py`  
**Core logic:** `agent/monitor.py — ProjectMonitor`  
**Verified against code** — doc discrepancy on intervals noted.

---

## Overview

Continuously running. Checks every 60s if any project is due for monitoring based on priority. For each due project: fetches latest Twitter data, AlphaGate enrichment, optional site content, then runs LLM analysis. Publishes status changes to Redis.

---

## Trigger

Two triggers:
1. Redis subscription to `projects:confirmed` (newly confirmed — triggers `activate_monitoring_for_confirmed()`)
2. Internal 60s loop checks `get_projects_to_monitor()` (due-by-priority)  
[monitor/main.py:34](../../services/monitor/main.py#L34) — `CHECK_INTERVAL = 60`

---

## Priority Check Intervals

Defined in `agent/database.py — MONITOR_INTERVALS`:

> **Doc discrepancy:** `ARCHITECTURE.md` / `README_FLOW.md` say `critical=8h, high=12h, medium=24h, low=24h`.  
> **Code reality:** imported from `agent.database.MONITOR_INTERVALS` — read code to confirm exact values.  
> Docs say 1/2/4/12h in ARCHITECTURE.md table, but README_FLOW says different. Code wins.

---

## Config

| Var | Default | Source |
|---|---|---|
| `CHECK_INTERVAL` | `60s` | [monitor/main.py:34](../../services/monitor/main.py#L34) |
| `BATCH_SIZE` | `999999` | [monitor/main.py:35](../../services/monitor/main.py#L35) |
| sleep between projects | `2s` | [monitor/main.py:240](../../services/monitor/main.py#L240) |

---

## Flow Diagram

```mermaid
flowchart TD
    A([60s loop]) --> B[get_projects_to_monitor — agent.db]
    B --> C{Any due?}
    C -->|no| D[log IDLE, sleep]
    C -->|yes| E[For each project]
    E --> F[get_or_fetch_user_tweets — users.db cache TTL 6h]
    F --> G[get_or_fetch_user_info — users.db cache TTL 6h]
    G --> H{user_info AND tweets both empty?}
    H -->|yes| I[mark monitoring_status=not_found, skip]
    H -->|no| J[Fetch website if site_url known]
    J --> K[AlphaGate enrichment — no cache]
    K --> L[MONITORING LLM]
    L --> M{LLM result}
    
    M --> N{ca_detected=True AND ca_address?}
    N -->|yes| O[new_status=launched]
    
    M --> P{launch_status=launched?}
    P -->|yes + date future| Q[new_status=active, urgency=scheduled]
    P -->|yes + date past| R[new_status=launched]
    P -->|yes + date today| S[new_status=active, urgency=imminent]
    P -->|yes + no date + evidence| R
    P -->|yes + no evidence| T[new_status=active, keep watching]
    
    M --> U{days_inactive >= 30?}
    U -->|yes| V[new_status=abandoned]
    U -->|no| W[new_status=active]
    
    O --> X{Publish decision}
    R --> X
    V --> X
    W --> X
    Q --> X
    S --> X
    
    X --> Y{ca_found=True?}
    Y -->|yes| Z[update_calendar_status — SILENT, no Telegram]
    Y -->|no + launched| AA[publish projects:launched + update calendar]
    Y -->|abandoned| AB[publish projects:abandoned]
    Y -->|urgency imminent/soon OR priority critical/high| AC[publish projects:alert]
    Y -->|monitor_count=0| AD[SKIP first monitor — no alert]
    Y -->|no changes| AE[SKIP — routine check]
    Y -->|has changes| AF[publish projects:monitored]
    
    Z --> AG[publish fingerprint:new]
    AA --> AG
    AB --> AG
    AC --> AG
    AD --> AG
    AE --> AG
    AF --> AG
    AG --> AH[also publish projects:monitored:{chain}]
    AH --> E
```

---

## Steps — Code Verified

### 1. Get due projects
`get_projects_to_monitor()` returns verified projects where:
- `monitoring_status = 'active'`
- `last_monitored_at IS NULL` OR `now - last_monitored_at > interval[priority]`

### 2. Fetch data (cached)
[agent/monitor.py:237–265](../../agent/monitor.py#L237)  
Same cache as verifier: `get_or_fetch_user_tweets()` + `get_or_fetch_user_info()` from `twitter_cache`.  
TTL = 6 hours. If BOTH return empty → mark `not_found`, skip LLM.

### 3. Days inactive — computed from real tweet date
[agent/monitor.py:325–333](../../agent/monitor.py#L325)  
`calculate_days_since_tweet(tweets[0].createdAt)` — does NOT trust LLM's `days_since_last_tweet`.  
LLM value used only as fallback if no tweets returned.

### 4. Monitoring LLM
[agent/monitor.py:308](../../agent/monitor.py#L308)  
`analyze_with_llm()` → `build_monitor_prompt()` + `get_monitor_system_prompt()`.

LLM output:
```json
{
  "launch_status": "not_launched" | "launched",
  "launch_urgency": "unknown" | "soon" | "imminent" | "scheduled",
  "launch_date_mentioned": str,
  "ca_detected": bool,
  "ca_address": str,
  "ca_source": str,
  "bio_changed": bool,
  "recommended_priority": "critical" | "high" | "medium" | "low",
  "significant_updates": list,
  "summary": str
}
```

### 5. Status decision logic (code-verified)
[agent/monitor.py:338–377](../../agent/monitor.py#L338)

Priority order:
1. `ca_detected=True AND ca_address` → `status=launched`
2. `launch_status=launched AND launch_date in future` → `status=active, urgency=scheduled`
3. `launch_status=launched AND launch_date passed` → `status=launched`
4. `launch_status=launched AND date=today` → `status=active, urgency=imminent`
5. `launch_status=launched AND no date AND evidence in summary` → `status=launched`
6. `days_inactive >= 30` → `status=abandoned`
7. else → `status=active`

### 6. Publish decisions
[monitor/main.py:196–238](../../services/monitor/main.py#L196)

| Condition | Action |
|---|---|
| `ca_found=True` | **SILENT** — update calendar only, NO Telegram |
| `status=launched AND ca_found=False` | publish `projects:launched` |
| `status=abandoned` | publish `projects:abandoned` |
| urgency `imminent/soon` OR priority `critical/high` | publish `projects:alert` |
| `monitor_count=0` (first check) | SKIP — no alert |
| changes=[] or ['routine check'] | SKIP — no alert |
| has real changes | publish `projects:monitored` |

**Always:** publish `fingerprint:new` + `projects:monitored:{chain}`.

---

## DB Reads

| Table | DB | Purpose |
|---|---|---|
| `verified_projects` | agent.db | Due projects queue |
| `twitter_cache` | users.db | Cached user data |

## DB Writes

| Table | DB | What |
|---|---|---|
| `verified_projects` | agent.db | Update monitoring fields |
| `monitoring_history` | agent.db | Per-check snapshot row |
| `launch_calendar` | agent.db | Launch date (on alert) |
| `decision_fingerprints` | agent.db | Stage 3 audit |

---

## Redis

| Channel | Sub/Pub | Notes |
|---|---|---|
| `projects:confirmed` | Subscribe | Triggers activate_monitoring |
| `monitor:delete` | Subscribe | User-requested stop |
| `projects:monitored` | Publish | To telegram-high #stage-3 |
| `projects:monitored:{chain}` | Publish | To telegram-chains UPDATES |
| `projects:alert` | Publish | Priority alert |
| `projects:launched` | Publish | Launch confirmed (no CA) |
| `projects:abandoned` | Publish | 30+ days inactive |
| `fingerprint:new` | Publish | Audit trail |

---

## Handle Delete via monitor:delete

[monitor/main.py:266–307](../../services/monitor/main.py#L266)  
On `monitor:delete` message: sets `monitoring_status='removed'` in `verified_projects`.  
Then publishes `projects:abandoned` with reason "Manually removed by @{user}".
