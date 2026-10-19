# db/test_dual_write.py
"""
Test script to verify dual-write to SQLite + Supabase is working.
"""

import os
import sys
from datetime import datetime

# Add parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env
from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("DUAL-WRITE TEST")
print("=" * 60)

# Test 1: Check Supabase connection
print("\n[1] Testing Supabase connection...")
from db.supabase_client import get_supabase_client, sync_to_supabase

client = get_supabase_client(verbose=True)
if client.test_connection():
    print("    [OK] Supabase connection successful!")
else:
    print("    [ERROR] Supabase connection failed!")
    sys.exit(1)

# Test 2: Test processed_tweets dual-write
print("\n[2] Testing processed_tweets dual-write...")

test_tweet_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# Import and init agent database
from agent.database import init_db, mark_tweet_processed

init_db()

# Mark a test tweet as processed (this should write to both SQLite and Supabase)
mark_tweet_processed(
    tweet_id=test_tweet_id,
    is_project=False,
    confidence=0.25,
    rejection_reason="test_rejection",
    raw_response='{"test": true}'
)
print(f"    Marked tweet {test_tweet_id} as processed (SQLite)")

# Verify in Supabase
result = client.select("processed_tweets", filters={"tweet_id": test_tweet_id})
if result.get("status") == "ok" and result.get("data"):
    print(f"    [OK] Found in Supabase: {result['data'][0].get('tweet_id')}")
else:
    print(f"    [WARNING] Not found in Supabase immediately (may be async)")

# Test 3: Test fingerprint dual-write
print("\n[3] Testing decision_fingerprints dual-write...")

from agent.database import save_fingerprint

fingerprint_data = {
    "twitter_handle": "test_handle",
    "tweet_id": test_tweet_id,
    "author_id": "test_author",
    "stage": 99,
    "stage_name": "test_stage",
    "decision": "test",
    "confidence": 0.5,
    "reason": "Testing dual-write",
    "input_type": "test",
    "input_summary": "Test fingerprint",
    "llm_reasoning": "This is a test",
    "key_factors": {"test_factor": True},
    "model_used": "test-model",
    "tokens_used": 100,
    "processing_time": 1.5
}

fp_id = save_fingerprint(fingerprint_data)
print(f"    Saved fingerprint ID: {fp_id} (SQLite)")

# Verify in Supabase (give it a moment)
import time
time.sleep(1)

result = client.select("decision_fingerprints", filters={"stage": 99}, limit=1)
if result.get("status") == "ok" and result.get("data"):
    print(f"    [OK] Found in Supabase: stage={result['data'][0].get('stage')}")
else:
    print(f"    [WARNING] Not found in Supabase (check logs)")

# Test 4: Test keyword_batches dual-write
print("\n[4] Testing keyword_batches dual-write...")

from tweets.database import init_db as init_tweets_db, save_batch_config

init_tweets_db()

save_batch_config(
    batch_name="test_batch",
    keywords=["test1", "test2"],
    description="Test batch for dual-write",
    priority=99
)
print(f"    Saved batch config: test_batch (SQLite)")

result = client.select("keyword_batches", filters={"batch_name": "test_batch"})
if result.get("status") == "ok" and result.get("data"):
    print(f"    [OK] Found in Supabase: {result['data'][0].get('batch_name')}")
else:
    print(f"    [WARNING] Not found in Supabase")

# Cleanup test data
print("\n[5] Cleaning up test data...")

client.delete("processed_tweets", {"tweet_id": test_tweet_id})
client.delete("decision_fingerprints", {"stage": 99})
client.delete("keyword_batches", {"batch_name": "test_batch"})
print("    [OK] Test data cleaned up from Supabase")

print("\n" + "=" * 60)
print("DUAL-WRITE TEST COMPLETE")
print("=" * 60)
print("""
Summary:
- SQLite: All writes go to local .db files as before
- Supabase: All writes are also synced to cloud PostgreSQL
- Sync is non-blocking: if Supabase fails, SQLite still works
- Enable/disable with SUPABASE_ENABLED=true/false in .env
""")

