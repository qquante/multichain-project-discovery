# reset_db.py
"""
RESET COMPLETO - Apaga TUDO e deixa o projeto do zero.

USO:
  python reset_db.py

Isso vai:
  1. Parar todos os containers (docker-compose down -v)
  2. Limpar Supabase (todas as tabelas)
  3. Remover arquivos locais de DB
  4. Limpar Redis (buffer, filas, pub/sub)
  
NÃO faz rebuild - você faz manualmente depois se quiser.
"""

import os
import sys
import subprocess
import time

def log(msg):
    print(f"[RESET] {msg}", flush=True)

def run(cmd):
    """Executa comando e mostra resultado."""
    log(f"$ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0 and result.stderr:
        print(f"  WARN: {result.stderr[:200]}")
    return result.returncode == 0


def flush_redis():
    """Tenta limpar Redis em diferentes modos/nome de container."""
    log("[1/4] Limpando Redis (FLUSHALL se ativo)...")
    
    cmds = [
        # Nome padrão usado no compose
        "docker exec redis redis-cli FLUSHALL",
        # Nome alternativo citado (agent-redis)
        "docker exec agent-redis redis-cli FLUSHALL",
        # Rodar o serviço temporariamente só para flush
        "docker-compose run --rm redis redis-cli FLUSHALL"
    ]
    
    for cmd in cmds:
        ok = run(cmd)
        if ok:
            log(f"  ✓ Redis limpo via: {cmd}")
            return True
    log("  Aviso: Redis não estava ativo ou flush falhou (ok se já parado)")
    return False

def clear_supabase():
    """Limpa todas as tabelas do Supabase."""
    log("Limpando Supabase...")
    
    try:
        import requests
        from dotenv import load_dotenv
        load_dotenv()
        
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_SERVICE_KEY')
        enabled = os.environ.get('SUPABASE_ENABLED', 'false').lower() == 'true'
        
        if not enabled or not url or not key:
            log("Supabase desabilitado ou sem credenciais - pulando")
            return
        
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        
        # Todas as tabelas - deletar usando RPC ou truncate
        tables = [
            # Pipelines principais
            'tweets',
            'processed_tweets',
            'triaged_projects',
            'verified_projects',
            'monitoring_history',
            'mentions',
            'decision_fingerprints',
            'verification_queue',
            'launch_calendar',

            # Dados auxiliares/coleta
            'query_state',
            'quoted_tweets',
            'keyword_batches',
            'collection_history',

            # Users/cache
            'user_fetch_state',
            'user_tweets'
        ]
        
        for table in tables:
            try:
                # Método 1: DELETE com filtro que pega tudo
                # Usar gt.0 para id numérico ou neq.'' para texto
                for filter_col in ['id', 'tweet_id', 'query_hash', 'user_id', 'twitter_handle']:
                    try:
                        # Tenta deletar onde a coluna não é nula
                        delete_url = f"{url}/rest/v1/{table}?{filter_col}=not.is.null"
                        response = requests.delete(delete_url, headers=headers, timeout=10)
                        
                        if response.status_code in [200, 204]:
                            log(f"  ✓ {table}")
                            break
                    except:
                        continue
                else:
                    # Se nenhum filtro funcionou, tenta sem filtro (perigoso mas funciona)
                    delete_url = f"{url}/rest/v1/{table}?select=*"
                    response = requests.delete(delete_url, headers=headers, timeout=10)
                    if response.status_code in [200, 204]:
                        log(f"  ✓ {table}")
                    elif response.status_code == 404:
                        log(f"  - {table} (não existe)")
                    else:
                        log(f"  ? {table}: {response.status_code}")
                        
            except Exception as e:
                log(f"  ✗ {table}: {str(e)[:30]}")
        
        log("Supabase limpo!")
        
    except ImportError:
        log("Módulo requests não instalado - pulando Supabase")
    except Exception as e:
        log(f"Erro Supabase: {e}")

def clear_local_files():
    """Remove arquivos locais de banco de dados."""
    log("Removendo arquivos locais...")
    
    db_files = [
        'agent.db', 'tweets.db', 'users.db', 'tweets_cache.db',
        'data/agent.db', 'data/tweets.db', 'data/users.db', 'data/tweets_cache.db'
    ]
    
    for f in db_files:
        if os.path.exists(f):
            try:
                os.remove(f)
                log(f"  ✓ {f}")
            except Exception as e:
                log(f"  ✗ {f}: {e}")

def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    RESET COMPLETO                            ║
║                                                              ║
║  Isso vai APAGAR TUDO:                                       ║
║  - Docker containers e volumes                               ║
║  - Redis (filas, buffer, pub/sub)                            ║
║  - SQLite (agent.db, tweets.db, users.db)                    ║
║  - Supabase (todas as tabelas)                               ║
║                                                              ║
║  NÃO faz rebuild automaticamente.                            ║
║  Depois execute: docker-compose up -d --build                ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    # Confirmação
    confirm = input("Tem certeza? Digite 'SIM' para continuar: ")
    if confirm.strip().upper() != 'SIM':
        log("Cancelado.")
        return
    
    print()
    log("="*50)
    log("INICIANDO RESET COMPLETO...")
    log("="*50)
    
    # 1. Tenta limpar Redis (se container estiver rodando)
    log("")
    flush_redis()
    time.sleep(1)
    
    # 2. Para containers E remove volumes (isso limpa Redis também)
    log("")
    log("[2/4] Parando containers e removendo volumes...")
    run("docker-compose down -v")
    time.sleep(2)
    
    # 3. Limpa Supabase
    log("")
    log("[3/4] Limpando Supabase...")
    clear_supabase()
    
    # 4. Remove arquivos locais de DB
    log("")
    log("[4/4] Removendo arquivos locais...")
    clear_local_files()
    
    print()
    log("="*50)
    log("RESET COMPLETO!")
    log("="*50)
    print("""
Tudo foi apagado:
  ✓ Docker containers parados
  ✓ Docker volumes removidos (Redis limpo)
  ✓ Supabase limpo
  ✓ Arquivos locais removidos

Para iniciar novamente:
  docker-compose up -d --build

Para monitorar:
  docker-compose logs -f
""")

if __name__ == "__main__":
    main()
