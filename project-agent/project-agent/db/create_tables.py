# db/create_tables.py
"""
Create tables in Supabase using the SQL REST endpoint.
"""

import os
import requests
import json

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://dfslhabqmerrheijrlfm.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', os.environ.get("SUPABASE_KEY", ""))


def execute_sql_via_rpc(sql: str) -> dict:
    """Execute SQL via Supabase RPC (requires a function to be created first)."""
    # This won't work unless we have a SQL execution function
    # For DDL, we need to use the Supabase Dashboard SQL Editor
    pass


def create_table_via_rest(table_name: str, check_only: bool = False) -> dict:
    """Check if table exists via REST API."""
    url = f"{SUPABASE_URL}/rest/v1/{table_name}?limit=0"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            return {"exists": True, "table": table_name}
        elif response.status_code == 404:
            return {"exists": False, "table": table_name}
        else:
            return {"exists": False, "table": table_name, "error": response.status_code}
    except Exception as e:
        return {"exists": False, "table": table_name, "error": str(e)}


def check_all_tables():
    """Check which tables exist."""
    tables = [
        'tweets', 'query_state', 'quoted_tweets', 'keyword_batches', 'collection_history',
        'processed_tweets', 'triaged_projects', 'verified_projects', 'monitoring_history',
        'verification_queue', 'decision_fingerprints', 'mentions',
        'user_tweets', 'user_fetch_state'
    ]
    
    print("=" * 60)
    print("CHECKING SUPABASE TABLES")
    print("=" * 60)
    
    existing = []
    missing = []
    
    for table in tables:
        result = create_table_via_rest(table)
        if result.get('exists'):
            existing.append(table)
            print(f"[EXISTS] {table}")
        else:
            missing.append(table)
            print(f"[MISSING] {table}")
    
    print()
    print(f"Existing: {len(existing)}")
    print(f"Missing: {len(missing)}")
    
    if missing:
        print()
        print("=" * 60)
        print("TO CREATE MISSING TABLES:")
        print("=" * 60)
        print()
        print("1. Go to: https://supabase.com/dashboard/project/dfslhabqmerrheijrlfm/sql")
        print("2. Open file: supabase_schema.sql")
        print("3. Copy ALL content")
        print("4. Paste in SQL Editor")
        print("5. Click 'Run'")
        print()
    
    return {"existing": existing, "missing": missing}


if __name__ == "__main__":
    check_all_tables()

