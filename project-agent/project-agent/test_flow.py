# test_flow.py
# Test the complete flow: collector -> triage -> check results

import sys
sys.path.insert(0, '.')

from tweets.batch_collector import BatchCollector
from agent.analyzer import TweetAnalyzer
from agent.database import (
    get_pending_tweets, 
    get_triage_stats, 
    init_db,
    get_fingerprints,
    get_triaged_projects
)

def main():
    init_db()
    
    # Step 1: Collect tweets
    print("=" * 60)
    print("STEP 1: Collecting tweets with 'launching soon' keyword")
    print("=" * 60)
    
    collector = BatchCollector(verbose=True)
    stats = collector.collect_batch('launch_soon', max_pages=1)
    print(f"Collector stats: {stats}")
    
    # Step 2: Check pending tweets
    print("\n" + "=" * 60)
    print("STEP 2: Pending tweets in database")
    print("=" * 60)
    
    pending = get_pending_tweets(limit=10)
    print(f"Pending tweets: {len(pending)}")
    
    for i, t in enumerate(pending[:5], 1):
        author = t.get('author_username', '?')
        text = t.get('text', '')[:80]
        print(f"  [{i}] @{author}: {text}...")
    
    # Step 3: Analyze first 3 tweets with LLM
    print("\n" + "=" * 60)
    print("STEP 3: Analyzing tweets with LLM")
    print("=" * 60)
    
    analyzer = TweetAnalyzer(verbose=True)
    
    for i, tweet in enumerate(pending[:3], 1):
        print(f"\n--- Tweet {i} ---")
        result = analyzer.analyze_tweet(tweet)
        
        if result:
            is_proj = result.get('is_project', False)
            conf = result.get('confidence', 0)
            author_analysis = result.get('author_analysis') or {}
            is_author = author_analysis.get('is_author_the_project')
            mentioned = result.get('mentioned_projects', [])
            
            print(f"  is_project: {is_proj}")
            print(f"  confidence: {conf}")
            print(f"  is_author_the_project: {is_author}")
            print(f"  mentioned_projects: {len(mentioned)}")
            
            if mentioned:
                for m in mentioned[:3]:
                    print(f"    - @{m.get('handle', '?')}")
    
    # Step 4: Check fingerprints
    print("\n" + "=" * 60)
    print("STEP 4: Decision fingerprints")
    print("=" * 60)
    
    fps = get_fingerprints(stage=1, limit=10)
    print(f"Stage 1 fingerprints: {len(fps)}")
    
    for fp in fps[:5]:
        handle = fp.get('twitter_handle', '?')
        decision = fp.get('decision', '?')
        conf = fp.get('confidence', 0)
        key_factors = fp.get('key_factors') or {}
        is_author = key_factors.get('is_author_the_project', 'N/A')
        
        print(f"  @{handle}: decision={decision} | is_author={is_author} | conf={conf:.2f}")
    
    # Step 5: Check triaged projects
    print("\n" + "=" * 60)
    print("STEP 5: Triaged projects")
    print("=" * 60)
    
    triaged = get_triaged_projects(limit=10)
    print(f"Triaged projects: {len(triaged)}")
    
    for p in triaged[:5]:
        handle = p.get('twitter_handle', '?')
        name = p.get('project_name', '?')
        chain = p.get('project_chain', '?')
        print(f"  @{handle} | {name} | {chain}")
    
    # Step 6: Check mentions
    print("\n" + "=" * 60)
    print("STEP 6: Mentions saved")
    print("=" * 60)
    
    import sqlite3
    conn = sqlite3.connect('agent.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM mentions LIMIT 10")
    mentions = cur.fetchall()
    conn.close()
    
    print(f"Mentions: {len(mentions)}")
    for m in mentions[:5]:
        src = m['source_author_handle'] or '?'
        mentioned = m['mentioned_handle'] or '?'
        print(f"  @{src} mentioned @{mentioned}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()

