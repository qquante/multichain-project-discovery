# Tasks — Crypto Alpha Hunting Bot
> Atualizado: 2026-04-16 | Gerado via análise forense completa

---

## ✅ DONE

### TASK-000 | Análise Forense Completa
- **O quê:** Mapeamento completo de arquitetura, fluxos, cache, bugs e gargalos
- **Resultado:** 11 issues identificados (3 críticos, 7 sérios, 1 informacional)
- **Data:** 2026-04-16
- **Arquivos lidos:** todos os serviços, agent/, tweets/, docker-compose.yml, .env

---

## 🔄 IN PROGRESS

*(nenhuma task em execução agora)*

---

## 📋 PENDING — CRÍTICO 🔴

### TASK-001 | Fix AlphaGate — Cookies para Env Vars
- **Prioridade:** CRÍTICA
- **Arquivo:** `agent/alphagate_client.py` — linhas 12-18 (bloco COOKIES = {...})
- **Problema:** Cookies `userId` e `extensionSessionId` hardcoded no corpo da classe.
  Quando a sessão expira (dias/semanas), TODO enrichment de AlphaGate falha silenciosamente.
  V2 docker-compose já tem as env vars mas o código não lê.
- **O que fazer:**
  ```python
  # REMOVER isso:
  COOKIES = {
      'userId': 's:AE8-W8...',
      'extensionSessionId': 's:7kV8Z...'
  }
  
  # ADICIONAR no __init__:
  def __init__(self):
      self.cookies = {
          'userId': os.environ.get('ALPHAGATE_USER_ID', ''),
          'extensionSessionId': os.environ.get('ALPHAGATE_SESSION_ID', '')
      }
      if not self.cookies['userId']:
          logger.warning("ALPHAGATE_USER_ID não configurado — enrichment desabilitado")
  ```
- **Critério de aceite:** Sistema lê cookies de ALPHAGATE_USER_ID e ALPHAGATE_SESSION_ID.
  Log de warning se não configurado. Zero cookies hardcoded no código.
- **Impacto se não fixar:** Todo projeto verificado fica sem score de social graph sem que ninguém saiba.

---

### TASK-002 | Fix Alpha-Hunter — Canal Redis Errado
- **Prioridade:** CRÍTICA
- **Arquivo:** `services/alpha-hunter/main.py` — buscar linha com `tweets:collected`
- **Problema:** Alpha-hunter publica em `tweets:collected` (canal de exibição Telegram)
  em vez de `tweets:new` (canal que aciona o Triage). Tweets de alpha callers entram
  no triage apenas pelo poll de 10s, sem trigger imediato. Podem ser perdidos.
- **O que fazer:**
  ```python
  # TROCAR:
  await redis_client.publish('tweets:collected', json.dumps(message))
  # POR:
  await redis_client.publish('tweets:new', json.dumps(message))
  # E adicionar também (para manter exibição no Telegram Stage 0):
  await redis_client.publish('tweets:collected', json.dumps(message))
  ```
- **Critério de aceite:** Tweets de alpha callers publicados em AMBOS os canais.
  Triage recebe trigger imediato.

---

## 📋 PENDING — SÉRIO 🟡

### TASK-003 | Limitar BATCH_SIZE — Risco OOM
- **Prioridade:** Alta
- **Arquivos:**
  - `services/triage/main.py` — linha com `BATCH_SIZE = 999999`
  - `services/verifier/main.py` — linha com `BATCH_SIZE = 999999`
- **Problema:** Com backlog grande, carrega tudo em memória de uma vez.
  Starvation de novos tweets durante processamento. Potencial OOM.
- **O que fazer:**
  ```python
  BATCH_SIZE = 50  # era 999999
  ```
- **Critério de aceite:** Máximo 50 items por ciclo. Novos tweets não ficam presos atrás de backlog.

---

### TASK-004 | Cache AlphaGate — SQLite TTL 2h
- **Dependência:** TASK-001 deve estar DONE primeiro
- **Prioridade:** Alta
- **Arquivo:** `agent/alphagate_client.py` + `agent/twitter_cache.py`
- **Problema:** `enrich_project()` faz 3 requests HTTP por projeto a CADA verificação
  e a CADA ciclo de monitoramento. Sem cache. Com 100 projetos monitorados = 300+ req/hora.
- **O que fazer:**
  Reutilizar a estrutura da tabela `twitter_cache` em `users.db`:
  ```python
  # Em enrich_project():
  cache_key = f"alphagate:{handle}"
  cached = self.cache.get(cache_key, cache_type='alphagate', ttl_hours=2)
  if cached:
      return json.loads(cached)
  
  result = self._fetch_enrichment(handle)
  self.cache.set(cache_key, cache_type='alphagate', data=json.dumps(result))
  return result
  ```
- **Critério de aceite:** Zero requests HTTP para projetos com enrichment < 2h.
  Hit rate de cache visível em logs.

---

### TASK-005 | Structured Output — Schema Enforced no LLM
- **Prioridade:** Alta
- **Arquivo:** `agent/api_client.py` + `agent/analyzer.py`
- **Problema:** Usa `response_format: {"type": "json_object"}` — JSON livre.
  LLM pode retornar campos ausentes, tipos errados ou campos inventados.
- **O que fazer:**
  ```python
  # Adicionar schema explícito no classifier:
  classifier_schema = {
      "type": "object",
      "properties": {
          "is_new_project": {"type": "boolean"},
          "author_is_project": {"type": "boolean"},
          "has_ca": {"type": "boolean"},
          "has_mentions": {"type": "boolean"},
          "confidence": {"type": "number", "minimum": 0, "maximum": 1},
          "rejection_reason": {
              "type": "string",
              "enum": ["already_launched","not_project","retweet",
                       "influencer_shill","low_confidence","other"]
          }
      },
      "required": ["is_new_project","author_is_project","has_ca","confidence"],
      "additionalProperties": False
  }
  
  # Rejeitar automaticamente se confidence < 0.7:
  if result.get('confidence', 0) < 0.7:
      return {'decision': 'rejected', 'reason': 'low_confidence'}
  ```
- **Critério de aceite:** Nenhum tweet aprovado sem campo `confidence`. Zero erros de parse
  por campos ausentes.

---

### TASK-006 | Fix Routing Telegram-Chains — Por Chain Real
- **Prioridade:** Média
- **Arquivo:** `services/telegram-chains/main.py`
- **Problema:** Código atual roteia TUDO para `CHAT_ID_ALL` e `CHAT_ID_UPDATES`.
  As env vars de chains específicas (`TELEGRAM_CHAT_ID_SOLANA` etc.) existem mas não são usadas.
  Usuários dos grupos de chain específica não recebem filtro correto.
- **O que fazer:** Restaurar roteamento por chain usando `CHAIN_CHAT_IDS` dict que já existe
  mas não está sendo usado para routing efetivo.
- **Critério de aceite:** Projetos Solana vão para grupo Solana. Projetos ETH para grupo ETH.
  Projetos sem chain clara vão para All.

---

### TASK-007 | Fix Collector — Consistência de Janela de Tempo
- **Prioridade:** Média
- **Arquivos:** `tweets/batch_collector.py` + `tweets/keywords.py`
- **Problema:** `build_query_for_batch()` usa `since_hours=48` mas `collect_batch()`
  para ao encontrar tweet de ontem. Keywords com poucos resultados hoje podem perder
  tweets de ontem que nunca foram coletados.
- **O que fazer:** Escolher UMA estratégia:
  - Opção A: `since_hours=24` (janela de 1 dia) + parar em tweets de ontem = consistente
  - Opção B: `since_hours=48` + NÃO parar em ontem + dedup por seen_id = coleta completa
  - **Recomendado:** Opção A para simplicidade.
- **Critério de aceite:** Janela de tempo do query = janela de tempo da coleta. Zero tweets
  de hoje-2 sendo solicitados mas nunca processados.

---

### TASK-008 | Redis Streams para Canais Críticos
- **Prioridade:** Média (backlog)
- **Problema:** Redis Pub/Sub é at-most-once. Se serviço cai durante mensagem, ela se perde.
  O workaround de poll (10s triage, 30s verifier) mitiga mas não elimina o risco.
- **O que fazer:** Migrar `tweets:new`, `projects:triaged`, `projects:confirmed` para Redis Streams.
  - Producer: `XADD stream:tweets:new * tweet_id {id} data {json}`
  - Consumer: `XREADGROUP GROUP triage consumer1 COUNT 50 STREAMS stream:tweets:new >`
  - Ack após processar: `XACK stream:tweets:new triage {message_id}`
- **Critério de aceite:** Mensagens persistem após restart de qualquer serviço.
  Dead-letter para mensagens que falham 3x.

---

### TASK-009 | Health Check AlphaGate — Alerta de Sessão Expirada
- **Dependência:** TASK-001 deve estar DONE
- **Prioridade:** Média
- **Arquivo:** `agent/alphagate_client.py`
- **Problema:** Quando sessão expira, falha silenciosamente. Sem alerta.
- **O que fazer:**
  ```python
  # Contar falhas consecutivas:
  if consecutive_failures >= 3:
      logger.error("AlphaGate: 3 falhas consecutivas — sessão possivelmente expirada")
      # Publicar em canal de sistema:
      await redis.publish('system:alerts', json.dumps({
          'type': 'alphagate_session_expired',
          'message': 'Renovar cookies ALPHAGATE_USER_ID e ALPHAGATE_SESSION_ID'
      }))
  ```
- **Critério de aceite:** Operador recebe alerta no Telegram quando AlphaGate falha 3x.

---

### TASK-010 | Observabilidade — Métricas Básicas de Pipeline
- **Prioridade:** Baixa (backlog)
- **Problema:** Zero visibilidade sobre: quantos tweets chegam/hora, % que passa triage,
  tempo médio de LLM call, taxa de falha do AlphaGate.
- **O que fazer:** Agregar dados já presentes na tabela `fingerprints` do agent.db:
  ```sql
  SELECT
      DATE(created_at) as date,
      COUNT(*) as total_decisions,
      SUM(CASE WHEN decision='triaged' THEN 1 ELSE 0 END) as approved,
      AVG(duration_ms) as avg_duration_ms
  FROM fingerprints
  GROUP BY DATE(created_at)
  ORDER BY date DESC;
  ```
  Criar endpoint simples ou script `check_stats.py` que imprime resumo.
- **Critério de aceite:** Operador pode ver funil de conversão do dia em < 5 segundos.

---

## 🗄️ BACKLOG

- [ ] TASK-011 | V2 project_scorer.py — verificar se está integrado no fluxo dos serviços ou é código órfão
- [ ] TASK-012 | Credentials — mover tokens hardcoded para secret manager ou pelo menos validar no startup
- [ ] TASK-013 | MIN_MENTIONS discoverer — restaurar default=2 ou documentar decisão de usar 1
- [ ] TASK-014 | Requirements.txt nos 5 serviços sem ele (alpha-followers, calendar-alerter, etc.)

---

## Legenda
| Símbolo | Significado |
|---------|------------|
| ✅ DONE | Concluído e verificado |
| 🔄 IN PROGRESS | Em execução agora |
| 📋 PENDING | Aguardando execução |
| 🔴 CRÍTICO | Pode estar quebrando produção agora |
| 🟡 SÉRIO | Risco real mas não quebrando agora |
| 🗄️ BACKLOG | Melhoria futura |
