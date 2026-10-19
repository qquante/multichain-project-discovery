#!/usr/bin/env python3
"""Analyze project flow through all stages."""

import sqlite3
import json

def analyze():
    conn = sqlite3.connect('agent.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    print("="*80)
    print("STAGE 1: TRIAGED PROJECTS (Last 15)")
    print("="*80)
    
    cur.execute('''
        SELECT twitter_handle, project_name, project_chain, project_type, 
               confidence, author_followers, tweet_text_preview, keywords_found,
               has_telegram, has_website, source_tweet_id
        FROM triaged_projects 
        ORDER BY created_at DESC LIMIT 15
    ''')
    
    triaged = []
    for i, row in enumerate(cur.fetchall(), 1):
        d = dict(row)
        triaged.append(d['twitter_handle'])
        print(f"\n{i}. @{d['twitter_handle']} | {d['project_name']} | {d['project_chain']}")
        print(f"   Type: {d['project_type']} | Conf: {d['confidence']:.2f} | Followers: {d['author_followers']}")
        keywords = d['keywords_found'] or '[]'
        print(f"   Keywords: {keywords}")
        print(f"   TG: {d['has_telegram']} | Web: {d['has_website']}")
        tweet = (d['tweet_text_preview'] or '')[:100]
        print(f"   Tweet: {tweet}...")
    
    print("\n" + "="*80)
    print("STAGE 2: VERIFIED PROJECTS (Last 15)")
    print("="*80)
    
    cur.execute('''
        SELECT twitter_handle, project_name, project_chain, 
               verification_status, verification_confidence, rejection_reason,
               bio, followers, tweets_analyzed, spam_score
        FROM verified_projects 
        ORDER BY created_at DESC LIMIT 15
    ''')
    
    for i, row in enumerate(cur.fetchall(), 1):
        d = dict(row)
        status_icon = "✅" if d['verification_status'] == 'confirmed' else "❌"
        print(f"\n{i}. {status_icon} @{d['twitter_handle']} | {d['project_name']} | {d['project_chain']}")
        print(f"   Status: {d['verification_status']} | Conf: {d['verification_confidence']:.2f}")
        if d['rejection_reason']:
            print(f"   Rejection: {d['rejection_reason']}")
        print(f"   Followers: {d['followers']} | Tweets: {d['tweets_analyzed']} | Spam: {d['spam_score']:.2f}")
        bio = (d['bio'] or '')[:80]
        print(f"   Bio: {bio}...")
    
    print("\n" + "="*80)
    print("DECISION FINGERPRINTS (Last 20)")
    print("="*80)
    
    cur.execute('''
        SELECT twitter_handle, stage, stage_name, decision, confidence, reason,
               input_tweet_text, input_bio, llm_reasoning, project_name, project_chain
        FROM decision_fingerprints 
        ORDER BY created_at DESC LIMIT 20
    ''')
    
    for i, row in enumerate(cur.fetchall(), 1):
        d = dict(row)
        print(f"\n{i}. @{d['twitter_handle']} | Stage {d['stage']} ({d['stage_name']})")
        print(f"   Decision: {d['decision']} | Conf: {d['confidence']:.2f}")
        print(f"   Reason: {d['reason']}")
        print(f"   Project: {d['project_name']} | Chain: {d['project_chain']}")
        tweet = (d['input_tweet_text'] or '')[:100]
        print(f"   Tweet: {tweet}...")
        reasoning = (d['llm_reasoning'] or '')[:150]
        print(f"   LLM: {reasoning}...")
    
    print("\n" + "="*80)
    print("STATS SUMMARY")
    print("="*80)
    
    cur.execute('SELECT COUNT(*) FROM triaged_projects')
    total_triaged = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM verified_projects')
    total_verified = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM verified_projects WHERE verification_status = 'confirmed'")
    confirmed = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM verified_projects WHERE verification_status = 'rejected'")
    rejected = cur.fetchone()[0]
    
    cur.execute('''
        SELECT rejection_reason, COUNT(*) as cnt 
        FROM verified_projects 
        WHERE rejection_reason IS NOT NULL 
        GROUP BY rejection_reason 
        ORDER BY cnt DESC LIMIT 10
    ''')
    rejection_reasons = cur.fetchall()
    
    print(f"\nTotal Triaged: {total_triaged}")
    print(f"Total Verified: {total_verified}")
    print(f"  - Confirmed: {confirmed}")
    print(f"  - Rejected: {rejected}")
    print(f"\nTop Rejection Reasons:")
    for r in rejection_reasons:
        print(f"  - {r[0]}: {r[1]}")
    
    conn.close()

def analyze_false_positives():
    """Analyze tweets to identify false positives."""
    
    conn_tweets = sqlite3.connect('tweets.db')
    conn_tweets.row_factory = sqlite3.Row
    cur = conn_tweets.cursor()
    
    print("\n" + "="*80)
    print("ANALYZING FALSE POSITIVES - Tweets mentioning @use_corn")
    print("="*80)
    
    cur.execute('''
        SELECT author_username, author_name, author_description, author_followers, text
        FROM tweets 
        WHERE text LIKE '%@use_corn%'
        ORDER BY captured_at DESC LIMIT 10
    ''')
    
    for i, row in enumerate(cur.fetchall(), 1):
        d = dict(row)
        print(f"\n{i}. AUTHOR: @{d['author_username']} | {d['author_name']}")
        print(f"   Followers: {d['author_followers']}")
        bio = (d['author_description'] or '')[:100]
        print(f"   Bio: {bio}")
        print(f"   Tweet: {d['text'][:200]}")
        
        # Check if this is likely a false positive
        is_corn_account = 'corn' in (d['author_username'] or '').lower()
        mentions_corn_handle = '@use_corn' in (d['text'] or '').lower()
        
        if not is_corn_account and mentions_corn_handle:
            print(f"   >>> FALSE POSITIVE: Author is NOT @use_corn but mentions it!")
    
    print("\n" + "="*80)
    print("WHAT IS @use_corn's REAL ACCOUNT?")
    print("="*80)
    
    cur.execute('''
        SELECT DISTINCT author_username, author_name, author_description, author_followers
        FROM tweets 
        WHERE LOWER(author_username) = 'use_corn'
        LIMIT 1
    ''')
    
    row = cur.fetchone()
    if row:
        d = dict(row)
        print(f"Found: @{d['author_username']}")
        print(f"Name: {d['author_name']}")
        print(f"Followers: {d['author_followers']}")
        print(f"Bio: {d['author_description']}")
    else:
        print("NOT FOUND in database - we never captured @use_corn's own tweets!")
    
    conn_tweets.close()


if __name__ == "__main__":
    analyze()
    analyze_false_positives()

