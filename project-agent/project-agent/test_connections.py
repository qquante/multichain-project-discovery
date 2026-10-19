#!/usr/bin/env python3
"""Test all external connections used by this project."""

import os
import sys
import json
import sqlite3
import urllib.request
import urllib.error
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"

results = []

def check(label, ok, detail=""):
    status = PASS if ok else FAIL
    msg = f"{status} {label}"
    if detail:
        msg += f" -- {detail}"
    print(msg)
    results.append((label, ok))


# --------------------------------------------------------------------------
# 1. Redis
# --------------------------------------------------------------------------
print("\n-- Redis -----------------------------------------------------------------")
try:
    import redis
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6388")
    r = redis.from_url(redis_url, socket_connect_timeout=3)
    pong = r.ping()
    check("Redis ping", pong, redis_url)
    p = r.pubsub()
    p.subscribe("test:connection_check")
    r.publish("test:connection_check", "hello")
    msg = None
    for m in p.listen():
        if m["type"] == "message":
            msg = m["data"]
            break
    p.unsubscribe("test:connection_check")
    check("Redis pub/sub round-trip", msg == b"hello")
except ImportError:
    check("Redis", False, "redis package not installed")
except Exception as e:
    check("Redis", False, str(e))


# --------------------------------------------------------------------------
# 2. Supabase
# --------------------------------------------------------------------------
print("\n-- Supabase --------------------------------------------------------------")
supabase_url = os.getenv("SUPABASE_URL", "")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY", "")
if not supabase_url or not supabase_key:
    check("Supabase env vars", False, "SUPABASE_URL or SUPABASE_SERVICE_KEY missing")
else:
    try:
        url = f"{supabase_url}/rest/v1/?apikey={supabase_key}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {supabase_key}"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            check("Supabase REST reachable", True, f"HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        ok = e.code < 500
        check("Supabase REST reachable", ok, f"HTTP {e.code}")
    except Exception as e:
        check("Supabase REST reachable", False, str(e))

    try:
        url2 = f"{supabase_url}/rest/v1/projects?select=id&limit=1"
        req2 = urllib.request.Request(url2, headers={
            "Authorization": f"Bearer {supabase_key}",
            "apikey": supabase_key,
        })
        with urllib.request.urlopen(req2, timeout=8) as resp:
            check("Supabase query (projects table)", True, f"HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        ok = e.code not in (401, 403)
        check("Supabase query (projects table)", ok, f"HTTP {e.code} -- {body[:100]}")
    except Exception as e:
        check("Supabase query (projects table)", False, str(e))


# --------------------------------------------------------------------------
# 3. Twitter API (twitterapi.io)
# --------------------------------------------------------------------------
print("\n-- Twitter API (twitterapi.io) -------------------------------------------")
twitter_key = os.getenv("TWITTER_API_KEY", "")
try:
    url = "https://api.twitterapi.io/twitter/user/info?userName=twitter"
    req = urllib.request.Request(url, headers={"X-API-Key": twitter_key})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
        check("Twitter API auth", True, f"HTTP {resp.status}")
        check("Twitter API response shape", "user" in data or "data" in data,
              str(list(data.keys()))[:80])
except urllib.error.HTTPError as e:
    body = e.read().decode()[:200]
    check("Twitter API auth", e.code not in (401, 403), f"HTTP {e.code} -- {body}")
except Exception as e:
    check("Twitter API", False, str(e))


# --------------------------------------------------------------------------
# 4. OpenRouter (LLM)
# --------------------------------------------------------------------------
print("\n-- OpenRouter API --------------------------------------------------------")
or_key = os.getenv("OPENROUTER_KEY", "")
if not or_key:
    check("OpenRouter env var", False, "OPENROUTER_KEY missing")
else:
    try:
        payload = json.dumps({
            "model": "openai/gpt-4o-mini",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }).encode()
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {or_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            check("OpenRouter API auth", "choices" in data or "id" in data,
                  f"HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        check("OpenRouter API auth", e.code not in (401, 403), f"HTTP {e.code} -- {body}")
    except Exception as e:
        check("OpenRouter API", False, str(e))


# --------------------------------------------------------------------------
# 5. Telegram Bots
# --------------------------------------------------------------------------
print("\n-- Telegram Bot API ------------------------------------------------------")

def test_telegram_bot(label, token):
    if not token:
        check(label, False, "token missing")
        return
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
            ok = data.get("ok") is True
            username = data.get("result", {}).get("username", "?")
            check(label, ok, f"@{username}")
    except Exception as e:
        check(label, False, str(e))

test_telegram_bot("Telegram Bot (main)",   os.getenv("TELEGRAM_BOT_TOKEN", ""))
test_telegram_bot("Telegram Bot (chains)", os.getenv("TELEGRAM_BOT_TOKEN_CHAINS", ""))


# --------------------------------------------------------------------------
# 6. SQLite (local DB)
# --------------------------------------------------------------------------
print("\n-- SQLite ----------------------------------------------------------------")
db_candidates = [
    os.path.join(os.path.dirname(__file__), "agent.db"),
    os.path.join(os.path.dirname(__file__), "data", "agent.db"),
]
for db_path in db_candidates:
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            conn.close()
            check(
                f"SQLite ({os.path.basename(db_path)})", True,
                f"{len(tables)} tables: {', '.join(t[0] for t in tables[:6])}"
            )
        except Exception as e:
            check(f"SQLite ({db_path})", False, str(e))
        break
else:
    check("SQLite agent.db", False, "file not found in . or ./data/")


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
print("\n-- Summary ---------------------------------------------------------------")
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
print(f"  {passed} passed  |  {failed} failed  |  {len(results)} total")
if failed:
    print("\nFailed checks:")
    for label, ok in results:
        if not ok:
            print(f"  * {label}")
    sys.exit(1)
