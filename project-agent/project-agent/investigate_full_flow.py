#!/usr/bin/env python3
"""
INVESTIGAÇÃO COMPLETA DO FLUXO
Analisa cada etapa desde AlphaGate até Telegram
"""

import sqlite3
import json
import os
from datetime import datetime

def investigate():
    print("=" * 80)
    print("🔬 INVESTIGAÇÃO COMPLETA DO FLUXO")
    print("=" * 80)
    
    # Check DBs - support Docker path
    db_path = os.environ.get('DB_PATH', '/app/data')
    agent_db = os.path.join(db_path, 'agent.db')
    tweets_db = os.path.join(db_path, 'tweets.db')
    
    # Fallback to local
    if not os.path.exists(agent_db):
        agent_db = 'agent.db'
        tweets_db = 'tweets.db'
    
    if not os.path.exists(agent_db):
        print(f"[ERROR] {agent_db} not found!")
        return
    
    conn = sqlite3.connect(agent_db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # ========================================
    # 1. TRIAGED_PROJECTS - Dados salvos pelo AlphaGate
    # ========================================
    print("\n" + "=" * 80)
    print("📋 1. TRIAGED_PROJECTS - O que foi salvo (últimos 20)")
    print("=" * 80)
    
    cur.execute("""
        SELECT 
            twitter_handle, 
            project_name, 
            project_chain, 
            project_type,
            author_followers,
            confidence,
            has_ca,
            tweet_text_preview,
            keywords_found,
            has_telegram,
            has_website,
            website_link,
            source_tweet_id,
            created_at
        FROM triaged_projects 
        ORDER BY created_at DESC 
        LIMIT 20
    """)
    
    rows = cur.fetchall()
    print(f"Total encontrados: {len(rows)}")
    print("-" * 80)
    
    alphagate_count = 0
    triage_count = 0
    
    for row in rows:
        source = row['source_tweet_id'] or ''
        is_alphagate = 'alphagate_' in source
        
        if is_alphagate:
            alphagate_count += 1
            source_type = "🅰️ ALPHAGATE"
        else:
            triage_count += 1
            source_type = "🐦 TRIAGE"
        
        handle = row['twitter_handle'] or 'NULL'
        name = row['project_name'] or 'NULL'
        chain = row['project_chain'] or 'unknown'
        ptype = row['project_type'] or 'unknown'
        followers = row['author_followers'] or 0
        conf = row['confidence'] or 0
        has_ca = '✅' if row['has_ca'] else '❌'
        has_tg = '✅' if row['has_telegram'] else '❌'
        has_web = '✅' if row['has_website'] else '❌'
        website = (row['website_link'] or '')[:30]
        keywords = row['keywords_found'] or '[]'
        preview = (row['tweet_text_preview'] or '')[:50]
        
        print(f"\n{source_type} @{handle}")
        print(f"  Name: {name} | Chain: {chain} | Type: {ptype}")
        print(f"  Followers: {followers} | Conf: {conf:.2f} | CA: {has_ca}")
        print(f"  TG: {has_tg} | Web: {has_web} | {website}")
        print(f"  Keywords: {keywords}")
        print(f"  Preview: {preview}...")
        print(f"  Source ID: {source[:50]}")
    
    print(f"\n📊 RESUMO: AlphaGate={alphagate_count} | Triage={triage_count}")
    
    # ========================================
    # 2. ANÁLISE: Dados do AlphaGate estão "porcos"?
    # ========================================
    print("\n" + "=" * 80)
    print("🔍 2. ANÁLISE DOS DADOS ALPHAGATE")
    print("=" * 80)
    
    cur.execute("""
        SELECT 
            twitter_handle,
            project_name,
            project_chain,
            project_type,
            author_followers,
            confidence,
            keywords_found
        FROM triaged_projects 
        WHERE source_tweet_id LIKE 'alphagate_%'
        ORDER BY created_at DESC 
        LIMIT 10
    """)
    
    rows = cur.fetchall()
    
    problems = {
        'chain_unknown': 0,
        'type_unknown': 0,
        'followers_zero': 0,
        'conf_zero': 0,
        'no_keywords': 0
    }
    
    for row in rows:
        chain = row['project_chain'] or 'unknown'
        ptype = row['project_type'] or 'unknown'
        followers = row['author_followers'] or 0
        conf = row['confidence'] or 0
        keywords = row['keywords_found'] or '[]'
        
        if chain == 'unknown':
            problems['chain_unknown'] += 1
        if ptype == 'unknown':
            problems['type_unknown'] += 1
        if followers == 0:
            problems['followers_zero'] += 1
        if conf == 0:
            problems['conf_zero'] += 1
        if keywords == '[]' or not keywords:
            problems['no_keywords'] += 1
    
    print(f"Total AlphaGate analisados: {len(rows)}")
    print("-" * 40)
    print(f"Chain = unknown:    {problems['chain_unknown']}")
    print(f"Type = unknown:     {problems['type_unknown']}")
    print(f"Followers = 0:      {problems['followers_zero']}")
    print(f"Confidence = 0:     {problems['conf_zero']}")
    print(f"Keywords vazios:    {problems['no_keywords']}")
    
    # ========================================
    # 3. VERIFIED_PROJECTS - Stage 2 Output
    # ========================================
    print("\n" + "=" * 80)
    print("✅ 3. VERIFIED_PROJECTS - Stage 2 Output (últimos 20)")
    print("=" * 80)
    
    cur.execute("""
        SELECT 
            twitter_handle,
            project_name,
            project_chain,
            verification_status,
            verification_confidence,
            rejection_reason,
            followers,
            monitoring_status,
            created_at
        FROM verified_projects 
        ORDER BY created_at DESC 
        LIMIT 20
    """)
    
    rows = cur.fetchall()
    print(f"Total verificados: {len(rows)}")
    print("-" * 80)
    
    for row in rows:
        handle = row['twitter_handle'] or 'NULL'
        name = row['project_name'] or 'NULL'
        chain = row['project_chain'] or 'unknown'
        status = row['verification_status'] or 'pending'
        conf = row['verification_confidence'] or 0
        rejection = row['rejection_reason'] or ''
        followers = row['followers'] or 0
        monitoring = row['monitoring_status'] or 'pending'
        
        icon = '✅' if status == 'confirmed' else '❌' if status == 'rejected' else '⏳'
        
        print(f"\n{icon} @{handle} | {name}")
        print(f"   Chain: {chain} | Status: {status} | Conf: {conf:.2f}")
        print(f"   Followers: {followers} | Monitoring: {monitoring}")
        if rejection:
            print(f"   Rejection: {rejection}")
    
    # ========================================
    # 4. CONTAGEM POR STATUS
    # ========================================
    print("\n" + "=" * 80)
    print("📊 4. ESTATÍSTICAS GERAIS")
    print("=" * 80)
    
    cur.execute("SELECT COUNT(*) FROM triaged_projects")
    total_triaged = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM triaged_projects WHERE source_tweet_id LIKE 'alphagate_%'")
    alphagate_total = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM verified_projects")
    total_verified = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM verified_projects WHERE verification_status = 'confirmed'")
    confirmed = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM verified_projects WHERE verification_status = 'rejected'")
    rejected = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM verified_projects WHERE monitoring_status = 'active'")
    active_monitoring = cur.fetchone()[0]
    
    print(f"📋 Triaged Total:       {total_triaged}")
    print(f"   - Via AlphaGate:     {alphagate_total}")
    print(f"   - Via Triage/LLM:    {total_triaged - alphagate_total}")
    print(f"")
    print(f"✅ Verified Total:      {total_verified}")
    print(f"   - Confirmed:         {confirmed}")
    print(f"   - Rejected:          {rejected}")
    print(f"   - Pending:           {total_verified - confirmed - rejected}")
    print(f"")
    print(f"🔄 Active Monitoring:   {active_monitoring}")
    
    # ========================================
    # 5. PENDENTES DE VERIFICAÇÃO
    # ========================================
    print("\n" + "=" * 80)
    print("⏳ 5. PROJETOS PENDENTES DE VERIFICAÇÃO")
    print("=" * 80)
    
    cur.execute("""
        SELECT t.twitter_handle, t.project_name, t.project_chain, t.created_at
        FROM triaged_projects t
        LEFT JOIN verified_projects v ON LOWER(t.twitter_handle) = LOWER(v.twitter_handle)
        WHERE v.id IS NULL
        ORDER BY t.created_at DESC
        LIMIT 20
    """)
    
    pending = cur.fetchall()
    print(f"Total pendentes: {len(pending)}")
    print("-" * 40)
    
    for row in pending:
        handle = row['twitter_handle'] or 'NULL'
        name = row['project_name'] or 'NULL'
        chain = row['project_chain'] or 'unknown'
        created = row['created_at'] or ''
        print(f"  @{handle:20} | {name:20} | {chain:10} | {created[:19]}")
    
    # ========================================
    # 6. RAW_RESPONSE - Ver dados brutos salvos
    # ========================================
    print("\n" + "=" * 80)
    print("🔧 6. RAW_RESPONSE - Dados brutos de um projeto AlphaGate")
    print("=" * 80)
    
    cur.execute("""
        SELECT twitter_handle, raw_response
        FROM triaged_projects 
        WHERE source_tweet_id LIKE 'alphagate_%'
        ORDER BY created_at DESC 
        LIMIT 1
    """)
    
    row = cur.fetchone()
    if row:
        handle = row['twitter_handle']
        raw = row['raw_response']
        
        print(f"Handle: @{handle}")
        print("-" * 40)
        
        try:
            data = json.loads(raw)
            print(json.dumps(data, indent=2)[:2000])
        except:
            print(f"Raw: {raw[:1000] if raw else 'NULL'}")
    else:
        print("Nenhum projeto AlphaGate encontrado!")
    
    conn.close()
    
    # ========================================
    # 7. FLUXO ESPERADO vs FLUXO REAL
    # ========================================
    print("\n" + "=" * 80)
    print("📋 7. FLUXO ESPERADO vs FLUXO REAL")
    print("=" * 80)
    
    print("""
FLUXO ESPERADO:
═══════════════

┌─────────────────┐
│   ALPHAGATE     │ → Busca API AlphaGate
│   API           │ → Converte para nosso formato
└────────┬────────┘ → save_triage_result()
         │           → publica em 'projects:triaged'
         ▼
┌─────────────────┐
│   TELEGRAM      │ → Escuta 'projects:triaged'
│   (Stage 1)     │ → Envia para TOPIC_STAGE_1
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   VERIFIER      │ → Escuta 'projects:triaged'
│   (Stage 2)     │ → Lê de triaged_projects (DB)
└────────┬────────┘ → Faz verificação
         │           → Salva em verified_projects
         ▼           → Publica em 'projects:confirmed' ou 'projects:rejected'
┌─────────────────┐
│   TELEGRAM      │ → Escuta 'projects:confirmed'/'rejected'
│   (Stage 2)     │ → Envia para TOPIC_STAGE_2
└─────────────────┘

PROBLEMA IDENTIFICADO:
═════════════════════

Os dados do AlphaGate estão chegando com:
- Chain: unknown
- Type: unknown  
- Confidence: 0.00
- Followers: 0

ISSO SIGNIFICA:
1. A API do AlphaGate NÃO está retornando dados OU
2. Os dados estão sendo perdidos na conversão OU
3. O save_triage_result() não está salvando os campos corretamente
""")
    
    print("=" * 80)
    print("🔬 INVESTIGAÇÃO COMPLETA")
    print("=" * 80)


if __name__ == "__main__":
    investigate()

