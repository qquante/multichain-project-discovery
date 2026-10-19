# CATALOG: db/

The `db/` module provides the Supabase dual-write client and database utilities. All SQLite databases (tweets.db, users.db, agent.db) call into this module to mirror data to Supabase PostgreSQL.

---

## db/supabase_client.py — Supabase REST Client

**Purpose:** `SupabaseClient` — HTTP client wrapping the Supabase REST API. Used by all three database modules to dual-write records.

### Configuration
- `SUPABASE_URL` — from env `SUPABASE_URL`, default hardcoded project URL
- `SUPABASE_KEY` — from env `SUPABASE_SERVICE_KEY`, default hardcoded service role JWT
- `SUPABASE_ENABLED` — from env `SUPABASE_ENABLED`, default `true`

### Class: `SupabaseClient`

| Method | Purpose | Inputs | Outputs |
|---|---|---|---|
| `__init__(verbose)` | Init, set enabled flag | `verbose: bool` | — |
| `insert(table, data, upsert)` | Insert one record | `table: str, data: dict, upsert: bool` | `dict` with status |
| `upsert(table, data)` | Insert or update (merge-duplicates) | `table: str, data: dict` | `dict` with status |
| `update(table, data, filters)` | PATCH records matching filters | `table: str, data: dict, filters: dict` | `dict` with status |
| `select(table, columns, filters, limit)` | GET records | args | `dict` with `data: list` |
| `delete(table, filters)` | DELETE records matching filters | `table: str, filters: dict` | `dict` with status |
| `test_connection()` | Ping Supabase REST endpoint | — | `bool` |
| `_convert_for_postgres(data)` | Type-coerce Python types for PostgreSQL | `data: dict` | `dict` |

**Status codes returned:** `"ok"`, `"exists"` (409 conflict), `"disabled"`, `"error"`

### Singleton

| Function | Purpose |
|---|---|
| `get_supabase_client(verbose)` | Get or create module-level singleton `SupabaseClient` |

### Module-Level Sync Functions

| Function | Purpose |
|---|---|
| `sync_to_supabase(table, data, upsert)` | Sync one record, returns `bool` |
| `batch_sync_to_supabase(table, records)` | Sync list of records, returns `{success, failed}` |

### Table-Specific Helpers

| Function | Table |
|---|---|
| `sync_tweet(data)` | `tweets` |
| `sync_processed_tweet(data)` | `processed_tweets` |
| `sync_triaged_project(data)` | `triaged_projects` |
| `sync_verified_project(data)` | `verified_projects` |
| `sync_monitoring_history(data)` | `monitoring_history` (insert-only) |
| `sync_fingerprint(data)` | `decision_fingerprints` (insert-only) |
| `sync_mention(data)` | `mentions` |
| `sync_collection_history(data)` | `collection_history` (insert-only) |
| `sync_keyword_batch(data)` | `keyword_batches` |

---

## db/create_tables.py — Table Setup Utility

**Purpose:** Utility script to verify which Supabase tables exist. Does not create tables (DDL must be run via Supabase SQL Editor using `supabase_schema.sql`).

### Functions

| Function | Purpose | Inputs | Outputs |
|---|---|---|---|
| `create_table_via_rest(table_name, check_only)` | Check if table exists via REST `limit=0` probe | `table_name: str` | `dict` with `exists: bool` |
| `check_all_tables()` | Check all 14 expected tables, print report | — | `dict` with `existing`, `missing` lists |

### Tables Checked
`tweets`, `query_state`, `quoted_tweets`, `keyword_batches`, `collection_history`, `processed_tweets`, `triaged_projects`, `verified_projects`, `monitoring_history`, `verification_queue`, `decision_fingerprints`, `mentions`, `user_tweets`, `user_fetch_state`

---

## db/supabase_setup.py — Setup Helper

**Purpose:** One-time setup utility for configuring the Supabase project. Contains helpers for initial schema validation and environment checks.

---

## db/__init__.py — Package Init

**Purpose:** Package marker. May re-export key symbols from `supabase_client.py` for cleaner imports.

---

## Dual-Write Architecture

Every write to a local SQLite database is followed by a fire-and-forget write to Supabase:

```
Local SQLite Write
       ↓
_sync_to_supabase(table, data)
       ↓
SupabaseClient.upsert(table, data)
       ↓
POST /rest/v1/{table}  (with Prefer: resolution=merge-duplicates)
```

**Error handling:** Supabase errors are silently logged (non-blocking). Local SQLite is always the source of truth. If `SUPABASE_ENABLED=false`, all sync calls return immediately with success.

---

## Local SQLite Databases

| File | Module | Tables |
|---|---|---|
| `tweets.db` | `tweets/database.py` | `tweets`, `query_state`, `quoted_tweets`, `keyword_batches`, `collection_history` |
| `users.db` | `users/database.py` | `user_tweets`, `user_fetch_state`, `alpha_followings`, `twitter_cache` |
| `agent.db` | `agent/database.py` | `processed_tweets`, `triaged_projects`, `verified_projects`, `monitoring_history`, `verification_queue`, `decision_fingerprints`, `mentions`, `project_favorites`, `add_requests`, `launch_calendar` |

All databases use WAL mode for concurrent reads. Path is set via `DB_PATH` env var (Docker-aware). Indexes exist on all frequently queried fields.
