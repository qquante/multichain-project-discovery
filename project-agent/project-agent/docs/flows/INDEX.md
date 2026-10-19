# Flow Documentation Index

All flows verified against actual source code. Where docs and code disagree, code wins.

---

## Input Flows (data collection)

| Flow | Service | Interval | Output | File |
|---|---|---|---|---|
| [FLOW-1](FLOW-1-collector.md) | Keyword Collector | 3h | tweets:collected, tweets:new | services/collector/ |
| [FLOW-2](FLOW-2-alpha-hunter.md) | Alpha Hunter | 12h | tweets:collected (**BUG**) | services/alpha-hunter/ |
| [FLOW-3](FLOW-3-alpha-followers.md) | Alpha Followers | 12h | tweets:new + triage stub | services/alpha-followers/ |
| [FLOW-4](FLOW-4-alphagate.md) | AlphaGate VIP | 2h | projects:triaged | services/alphagate/ |

## Stage Flows (AI pipeline)

| Flow | Service | Trigger | Output | File |
|---|---|---|---|---|
| [FLOW-5](FLOW-5-triage.md) | Stage 1 Triage | tweets:new + 10s poll | projects:triaged, mentions:new | services/triage/ |
| [FLOW-6](FLOW-6-verifier.md) | Stage 2 Verifier | projects:triaged + 30s poll | projects:confirmed | services/verifier/ |
| [FLOW-7](FLOW-7-monitor.md) | Stage 3 Monitor | projects:confirmed + 60s loop | projects:monitored/alert/launched/abandoned | services/monitor/ |

## Support Flows

| Flow | Service | Interval | Output | File |
|---|---|---|---|---|
| [FLOW-8](FLOW-8-discoverer.md) | Discoverer | 30min | triaged_projects (→ Stage 2) | services/discoverer/ |
| [FLOW-9](FLOW-9-abandoned-checker.md) | Abandoned Checker | 7 days | projects:removed, projects:reactivated | services/abandoned-checker/ |
| [FLOW-10](FLOW-10-calendar-alerter.md) | Calendar Alerter | 60min | calendar:alert:{type} + Telegram direct | services/calendar-alerter/ |

## Output Flows

| Flow | Services | Description | File |
|---|---|---|---|
| [FLOW-11](FLOW-11-telegram.md) | 5 Telegram bots | Message formatting + delivery | services/telegram-* |

---

## Confirmed Code vs Doc Discrepancies

| # | Topic | Docs Say | Code Reality | File |
|---|---|---|---|---|
| 1 | Keyword batches | 18 batches | **19 batches** (`other_chains` extra) | [tweets/keywords.py](../../tweets/keywords.py) |
| 2 | Monitor intervals | `critical=8h, high=12h, medium=24h` (README_FLOW) | defined in `agent.database.MONITOR_INTERVALS` | [agent/database.py](../../agent/database.py) |
| 3 | Stage 1 CA check | ca_detector.py runs BEFORE LLM | LLM classifier returns `has_ca`. No regex in Stage 1. | [agent/analyzer.py](../../agent/analyzer.py) |
| 4 | Alpha-hunter channel | publishes `tweets:new` | **BUG: publishes `tweets:collected`** — triage misses real-time | [alpha-hunter/main.py:107](../../services/alpha-hunter/main.py#L107) |
| 5 | AlphaGate auth | env-based config | **BUG: cookies hardcoded** | [alphagate/main.py:60](../../services/alphagate/main.py#L60) |
| 6 | Monitor CA detection | silent remove | Correct — code confirms silent (no Telegram) | [monitor/main.py:196](../../services/monitor/main.py#L196) |
| 7 | telegram-chains routing | per-chain groups | **Refactored**: all confirmed → CHAT_ID_ALL, all monitored → CHAT_ID_UPDATES | [telegram-chains/main.py:33](../../services/telegram-chains/main.py#L33) |

---

## Confirmed Bugs (in code)

| # | Bug | Location | Impact |
|---|---|---|---|
| B-1 | Alpha-hunter publishes wrong channel | [alpha-hunter/main.py:107](../../services/alpha-hunter/main.py#L107) | Delayed triage (only via 10s poll) |
| B-2 | AlphaGate cookies hardcoded | [alphagate/main.py:60–63](../../services/alphagate/main.py#L60) | Cookie rotation breaks whole AlphaGate flow |
| B-3 | AlphaGate cookies also in client | [alphagate_client.py:35–38](../../agent/alphagate_client.py#L35) | Same as B-2, separate location |
| B-4 | BATCH_SIZE=999999 everywhere | triage, verifier, monitor main.py | Memory spike risk on large backlog |

---

## Refactor Notes (for new repo)

Suggested layered order:
1. **Base utils:** `agent/chain_utils.py`, `agent/ca_detector.py`, `agent/twitter_cache.py`
2. **External clients:** `tweets/api_client.py`, `users/api_client.py`, `agent/api_client.py`, `agent/alphagate_client.py`, `agent/website_reader.py`
3. **Storage:** `db/supabase_client.py`, `tweets/database.py`, `users/database.py`, `agent/database.py`
4. **Collectors:** FLOW-1 through FLOW-4
5. **AI pipeline:** `agent/analyzer.py`, `agent/verifier.py`, `agent/monitor.py`, `agent/discoverer.py` + prompts
6. **Service runners:** triage, verifier, monitor, discoverer, abandoned-checker, calendar-alerter
7. **Output:** all telegram-* services
