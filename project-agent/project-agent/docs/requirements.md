# Requirements — Crypto Alpha Hunting Bot

## Visão Geral
Sistema de inteligência de mercado que detecta projetos de crypto pré-lançamento no Twitter
antes que o contrato (CA) seja publicado, permitindo entrada antecipada em narrativas.

---

## REQ-001 — Coleta Contínua de Tweets
**User Story:** Como operador, quero que o sistema colete tweets relevantes de forma contínua
para que nenhum projeto pré-lançamento seja perdido.

**Critérios de Aceite:**
- [ ] Collector roda a cada 3 horas automaticamente
- [ ] 18 batches de keywords cobrem: pre_launch, launch_soon, solana, megaeth, monad, bsc, ethereum, base, etc.
- [ ] Deduplicação por tweet ID entre runs
- [ ] Tweets publicados em `tweets:collected` (exibição) E `tweets:new` (trigger triage)
- [ ] Paginação até MAX_PAGES=5 por batch
- [ ] Para de coletar ao encontrar tweet já visto (stop by seen_id)

**Status atual:** ✅ Funcional | ⚠️ Inconsistência: query pede 48h mas para em tweets de ontem

---

## REQ-002 — Triagem com LLM em 2 Estágios
**User Story:** Como operador, quero que tweets irrelevantes sejam descartados automaticamente
usando AI para que apenas projetos legítimos avancem no pipeline.

**Critérios de Aceite:**
- [ ] LLM Call 1 (Classifier): determina se é projeto novo, se autor É o projeto, se tem CA
- [ ] LLM Call 2 (Extractor): só executa se classifier aprovar — extrai handle, chain, description
- [ ] Validação anti-alucinação: confirma menções via `entities.user_mentions` da API (não só pelo LLM)
- [ ] Tweets com CA detectado são descartados (projeto já lançado)
- [ ] Output com schema enforced (não JSON livre)
- [ ] Campo `confidence: 0.0-1.0` obrigatório — rejeitar se < 0.7
- [ ] Fingerprint de cada decisão salvo com reasoning completo

**Status atual:** ✅ Funcional | ⚠️ Sem schema enforced | ⚠️ Sem confidence score

---

## REQ-003 — Verificação Completa de Projetos
**User Story:** Como operador, quero verificação completa do perfil antes de confirmar um projeto
para que falsos positivos não cheguem ao Telegram.

**Critérios de Aceite:**
- [ ] Fetch de perfil completo: /user/info + tweets + pinned tweet
- [ ] Cache de 6h para dados de usuário (não refetch desnecessário)
- [ ] Fetch de website se URL presente no perfil
- [ ] AlphaGate enrichment: key_followers, alpha_hunters, winrate
- [ ] Pre-LLM CA check (economiza tokens)
- [ ] LLM de verificação com contexto completo estruturado
- [ ] CalendarAgent extrai datas + tickers após confirmação
- [ ] Summary gerado em PT-BR
- [ ] Roteamento por chain para grupos Telegram específicos

**Status atual:** ✅ Funcional | 🔴 AlphaGate cookies hardcoded expiram silenciosamente

---

## REQ-004 — Monitoramento Pós-Confirmação
**User Story:** Como operador, quero acompanhar projetos confirmados até o lançamento
para receber alerta imediato quando o CA for publicado.

**Critérios de Aceite:**
- [ ] Intervalos por prioridade: Critical=8h, High=12h, Medium/Low=24h
- [ ] Detecção de CA em novo conteúdo → alerta imediato
- [ ] Validação de data: se LLM diz "launched" mas data é futura → manter como "active"
- [ ] days_inactive calculado por timestamp real do tweet (não pelo LLM)
- [ ] Projeto inativo → marca abandoned + alerta
- [ ] Suporte a remoção manual via canal `monitor:delete`

**Status atual:** ✅ Funcional | ⚠️ AlphaGate sem cache (3 requests/projeto/ciclo)

---

## REQ-005 — Alertas Telegram Confiáveis
**User Story:** Como operador, quero receber alertas no Telegram sem perder mensagens críticas
mesmo sob rate limit da API do Telegram.

**Critérios de Aceite:**
- [ ] Fila high priority: nunca perde mensagens (deque ilimitado)
- [ ] Fila low priority: maxlen=50 (descarta antigas se cheio)
- [ ] Rate limit handling: registra timestamp, não bloqueia receiving
- [ ] 9 grupos por chain: Solana, Base, ETH, BSC, MegaETH, Monad, Other, Unknown, All
- [ ] Roteamento por chain funcionando (não hardcoded para CHAT_ID_ALL)

**Status atual:** ✅ Filas funcionam | 🟡 Roteamento por chain foi silenciado no código

---

## REQ-006 — Cache e Performance
**User Story:** Como operador, quero que o sistema não desperdice chamadas de API
para reduzir latência e custo operacional.

**Critérios de Aceite:**
- [ ] Twitter user data: cache SQLite TTL 6h ✅ (implementado)
- [ ] AlphaGate enrichment: cache SQLite TTL 2h ❌ (não implementado)
- [ ] Websites de projetos: cache TTL 1h ❌ (não implementado)
- [ ] BATCH_SIZE máximo 100 por ciclo ❌ (atual: 999999)
- [ ] AlphaGate lê cookies de env vars ❌ (atual: hardcoded)

**Status atual:** 🔴 Múltiplos itens não implementados

---

## REQ-007 — Rastreabilidade e Auditoria
**User Story:** Como operador, quero saber exatamente o que o sistema decidiu e por quê
para poder debugar falsos positivos e falsos negativos.

**Critérios de Aceite:**
- [ ] Fingerprint de cada decisão LLM salvo: reasoning, tokens, timing, resultado
- [ ] Episodic log de todas as mudanças no código
- [ ] Known bugs documentados com status
- [ ] Decisões arquiteturais documentadas com reasoning

**Status atual:** ✅ Fingerprints implementados | ⚠️ Sem episodic log de mudanças no código
