# Design — Crypto Alpha Hunting Bot

## Arquitetura de Alto Nível

```
TWITTER API (api.twitterapi.io)
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│                    INPUT SOURCES                          │
│  Collector(3h) │ AlphaHunter(12h) │ AlphaFollowers(12h)  │
│                │ AlphaGate(2h)    │ Discoverer(30min)     │
└───────┬────────┴──────────────────┴───────────────────────┘
        │ Redis Pub/Sub (port 6388)
        ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  TRIAGE       │───▶│  VERIFIER     │───▶│  MONITOR      │
│  Stage 1      │    │  Stage 2      │    │  Stage 3      │
│  poll: 10s    │    │  poll: 30s    │    │  cycle: 60s   │
│  LLM x2       │    │  LLM x1       │    │  LLM x1       │
└───────────────┘    └───────────────┘    └───────────────┘
        │                   │                    │
        └───────────────────┴────────────────────┘
                            │
                     Redis Pub/Sub
                            │
                ┌───────────▼───────────┐
                │   TELEGRAM BOTS       │
                │  telegram-high        │
                │  telegram-low         │
                │  telegram-chains      │
                │  calendar-alerter     │
                └───────────────────────┘
```

## Persistência
```
SQLite (compartilhado via volume Docker db-data):
├── agent.db    → processed_tweets, triaged_projects, verified_projects,
│                 fingerprints, monitoring_history
├── tweets.db   → histórico de tweets coletados, batch runs
└── users.db    → twitter_cache (TTL 6h), alpha_followers seen

Redis (WAL persistence, port 6388):
├── Canais Pub/Sub → mensagens entre serviços
└── Persistência → evita perda em restart

Supabase (opcional, dual-write silencioso):
└── Mirror de agent.db para cloud
```

## Canais Redis
| Canal | Produtor | Consumidor | Propósito |
|-------|---------|-----------|---------|
| `tweets:collected` | Collector, AlphaHunter | telegram-low | Exibição Stage 0 |
| `tweets:new` | Collector | Triage | Trigger de processamento |
| `projects:triaged` | Triage | telegram-low | Notificação Stage 1 |
| `triage:rejected` | Triage | telegram-low | Rejeições |
| `mentions:new` | Triage | telegram-high | Menções detectadas |
| `projects:confirmed` | Verifier | telegram-high | Confirmações |
| `projects:confirmed:{chain}` | Verifier | telegram-chains | Por chain |
| `projects:alert` | Monitor | telegram-high | Alertas ativos |
| `projects:launched` | Monitor | telegram-high | Lançamentos |
| `projects:abandoned` | Monitor | telegram-high | Abandonados |
| `projects:removed` | Monitor | telegram-high | Removidos |
| `projects:reactivated` | Monitor | telegram-high | Reativados |
| `fingerprint:new` | Triage | telegram-low | Audit trail |
| `monitor:delete` | Manual | Monitor | Remoção manual |
| `discovery:complete` | Discoverer | telegram-high | Descobertas |

## Fluxo de Dados — Stage 1 (Triage)
```
tweet_text
    │
    ▼ [PRE-CHECK sem LLM]
has_ca? ──YES──▶ descarta
    │
    NO
    ▼
[LLM Classifier]
  Input: tweet estruturado
  Output: {is_new_project, author_is_project, has_ca, has_mentions}
    │
    ▼ is_new_project=False?
    ├──YES──▶ triage:rejected
    │
    NO
    ▼
[LLM Extractor]
  Input: tweet + resultado classifier
  Output: {handle, chain, description, launch_timing}
    │
    ▼
[_validate_mentions_from_api()]  ← anti-alucinação crítico
  Confirma menções via entities.user_mentions da API
    │
    ▼
  Salva em triaged_projects
  Publica → projects:triaged
```

## Fluxo de Dados — Stage 2 (Verifier)
```
triaged_project (handle confirmado)
    │
    ▼ [fetch_user_data() com cache 6h]
  perfil + tweets + pinned_tweet
    │
    ▼ [pre-LLM CA check]
  CA detectado? ──YES──▶ descarta silenciosamente
    │
    NO
    ▼
  [website fetch se URL no perfil]
    │
    ▼
  [AlphaGate enrichment]  ← 3 requests HTTP, SEM cache
  key_followers, alpha_hunters, winrate
    │
    ▼
  [LLM Verifier]
  Input: perfil + tweets + AlphaGate + website
  Output: verified, score, reasoning
    │
    ▼ verified=True
  [CalendarAgent] → extrai datas + tickers
  [Generate PT-BR summary]
    │
    ▼
  Salva em verified_projects
  Publica → projects:confirmed + projects:confirmed:{chain}
```

## Modelo LLM
- **Provider:** OpenRouter
- **Modelo:** `google/gemini-2.5-flash-lite`
- **Response format:** `{"type": "json_object"}` (JSON livre, não schema enforced)
- **Retry:** exponential backoff, 2^attempt seconds
- **Fingerprint:** cada call salvo com reasoning, tokens, timing

## Cache Strategy
| Dado | Implementado | TTL | Storage |
|------|-------------|-----|---------|
| Twitter user info | ✅ | 6h | SQLite users.db |
| Twitter user tweets | ✅ | 6h | SQLite users.db |
| AlphaGate enrichment | ❌ | — | — |
| Websites de projetos | ❌ | — | — |
| Resultados de LLM | ❌ | — | — |

## Decisões Arquiteturais
Ver: `.agent-memory/decisions.md`

## Serviços Docker (15 total)
| Serviço | Intervalo | Propósito |
|---------|----------|---------|
| collector | 3h | Coleta por keywords |
| triage | 10s poll | Classificação LLM |
| verifier | 30s poll | Verificação completa |
| monitor | 60s cycle | Monitoramento pós-confirmação |
| discoverer | 30min | Investigação de handles mencionados |
| alpha-hunter | 12h | Tweets de alpha callers |
| alpha-followers | 12h | Followings de seeds VIP |
| alphagate | 2h | Projetos do AlphaGate |
| telegram-high | contínuo | Alertas críticos |
| telegram-low | contínuo | Notificações Stage 0/1 |
| telegram-chains | contínuo | Roteamento por chain |
| telegram-chains-callback | contínuo | Inline buttons |
| calendar-alerter | contínuo | Alertas de datas |
| redis | — | Message broker + persistência |
