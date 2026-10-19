# investigate_db.py
# Script to investigate all database tables and understand the flow

import sqlite3
import json
import os

def investigate():
    print("=" * 80)
    print("DATABASE INVESTIGATION")
    print("=" * 80)
    
    # Check if DB exists
    if not os.path.exists('agent.db'):
        print("[ERROR] agent.db not found!")
        return
    
    conn = sqlite3.connect('agent.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # 1. VERIFIED_PROJECTS (being monitored)
    print("\n" + "=" * 80)
    print("1. VERIFIED_PROJECTS - Projects being MONITORED")
    print("=" * 80)
    
    cur.execute("""
        SELECT id, twitter_handle, project_name, project_chain, 
               verification_status, monitoring_status, priority,
               followers, created_at
        FROM verified_projects 
        WHERE monitoring_status IN ('active', 'pending')
        ORDER BY created_at DESC 
        LIMIT 25
    """)
    
    rows = cur.fetchall()
    print(f"Total active/pending: {len(rows)}")
    print("-" * 80)
    
    for row in rows:
        handle = row['twitter_handle'] or 'NULL'
        name = row['project_name'] or 'NULL'
        chain = row['project_chain'] or 'unknown'
        status = row['verification_status'] or 'NULL'
        mon = row['monitoring_status'] or 'NULL'
        prio = row['priority'] or 'low'
        followers = row['followers'] or 0
        
        print(f"ID={row['id']:3} | @{handle:20} | {name:20} | {chain:10} | v={status:10} | m={mon:8} | p={prio:6} | f={followers}")
    
    # 2. TRIAGED_PROJECTS (Stage 1 output)
    print("\n" + "=" * 80)
    print("2. TRIAGED_PROJECTS - Stage 1 Triage Output")
    print("=" * 80)
    
    cur.execute("""
        SELECT id, twitter_handle, project_name, project_chain, 
               confidence, has_ca, created_at
        FROM triaged_projects 
        ORDER BY created_at DESC 
        LIMIT 25
    """)
    
    rows = cur.fetchall()
    print(f"Total: {len(rows)}")
    print("-" * 80)
    
    for row in rows:
        handle = row['twitter_handle'] or 'NULL'
        name = row['project_name'] or 'NULL'
        chain = row['project_chain'] or 'unknown'
        conf = row['confidence'] or 0
        has_ca = 'YES' if row['has_ca'] else 'NO'
        
        print(f"ID={row['id']:3} | @{handle:20} | {name:20} | {chain:10} | conf={conf:.2f} | ca={has_ca}")
    
    # 3. MENTIONS
    print("\n" + "=" * 80)
    print("3. MENTIONS - Influencer mentions saved")
    print("=" * 80)
    
    cur.execute("""
        SELECT id, source_author_handle, mentioned_handle, 
               project_name_extracted, confidence, created_at
        FROM mentions 
        ORDER BY created_at DESC 
        LIMIT 20
    """)
    
    rows = cur.fetchall()
    print(f"Total: {len(rows)}")
    print("-" * 80)
    
    for row in rows:
        src = row['source_author_handle'] or 'NULL'
        mentioned = row['mentioned_handle'] or 'NULL'
        name = row['project_name_extracted'] or 'NULL'
        conf = row['confidence'] or 0
        
        print(f"ID={row['id']:3} | @{src:20} mentioned @{mentioned:20} | {name:15} | conf={conf:.2f}")
    
    # 4. PROCESSED_TWEETS - Check decisions
    print("\n" + "=" * 80)
    print("4. PROCESSED_TWEETS - Recent LLM decisions")
    print("=" * 80)
    
    cur.execute("""
        SELECT tweet_id, is_project, confidence, rejection_reason,
               substr(raw_response, 1, 500) as response_preview
        FROM processed_tweets 
        WHERE is_project = 1
        ORDER BY processed_at DESC 
        LIMIT 10
    """)
    
    rows = cur.fetchall()
    print(f"Recent is_project=TRUE: {len(rows)}")
    print("-" * 80)
    
    for row in rows:
        tid = row['tweet_id'] or 'NULL'
        conf = row['confidence'] or 0
        
        # Try to parse the response to check is_author_the_project
        try:
            resp = json.loads(row['response_preview'] + '"}}}') if row['response_preview'] else {}
        except:
            resp = {}
        
        author_analysis = resp.get('author_analysis', {})
        is_author = author_analysis.get('is_author_the_project', 'NOT_IN_RESPONSE')
        author_type = author_analysis.get('author_type', 'unknown')
        
        print(f"tweet={tid[:20]:20} | conf={conf:.2f} | is_author={is_author} | type={author_type}")
    
    # 5. FINGERPRINTS - Check recent decisions
    print("\n" + "=" * 80)
    print("5. DECISION_FINGERPRINTS - Stage 1 decisions")
    print("=" * 80)
    
    cur.execute("""
        SELECT twitter_handle, decision, confidence, 
               json_extract(key_factors, '$.is_author_the_project') as is_author,
               json_extract(key_factors, '$.author_type') as author_type,
               created_at
        FROM decision_fingerprints 
        WHERE stage = 1
        ORDER BY created_at DESC 
        LIMIT 20
    """)
    
    rows = cur.fetchall()
    print(f"Recent Stage 1 fingerprints: {len(rows)}")
    print("-" * 80)
    
    for row in rows:
        handle = row['twitter_handle'] or 'NULL'
        decision = row['decision'] or 'NULL'
        conf = row['confidence'] or 0
        is_author = row['is_author'] if row['is_author'] is not None else 'NULL'
        author_type = row['author_type'] or 'unknown'
        
        print(f"@{handle:20} | decision={decision:15} | conf={conf:.2f} | is_author={is_author} | type={author_type}")
    
    # 6. Summary stats
    print("\n" + "=" * 80)
    print("6. SUMMARY STATS")
    print("=" * 80)
    
    cur.execute("SELECT COUNT(*) FROM triaged_projects")
    triaged = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM verified_projects")
    verified = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM verified_projects WHERE verification_status = 'confirmed'")
    confirmed = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM verified_projects WHERE monitoring_status = 'active'")
    active = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM mentions")
    mentions = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM decision_fingerprints WHERE stage = 1")
    fp_stage1 = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM decision_fingerprints WHERE stage = 1 AND decision = 'triaged'")
    fp_triaged = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM decision_fingerprints WHERE stage = 1 AND decision = 'mention_saved'")
    fp_mention = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM decision_fingerprints WHERE stage = 1 AND decision = 'not_project_skipped'")
    fp_skipped = cur.fetchone()[0]
    
    print(f"Triaged projects:     {triaged}")
    print(f"Verified projects:    {verified}")
    print(f"  - Confirmed:        {confirmed}")
    print(f"  - Active monitoring:{active}")
    print(f"Mentions saved:       {mentions}")
    print(f"Stage 1 fingerprints: {fp_stage1}")
    print(f"  - triaged:          {fp_triaged}")
    print(f"  - mention_saved:    {fp_mention}")
    print(f"  - not_project_skipped: {fp_skipped}")
    
    conn.close()
    
    print("\n" + "=" * 80)
    print("INVESTIGATION COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    investigate()

