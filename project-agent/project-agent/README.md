# Project Agent Horus - All Chains

Multi-chain cryptocurrency project detection and monitoring system.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Collector  │ ──► │   Triage    │ ──► │  Verifier   │ ──► │   Monitor   │
│  (Stage 0)  │     │  (Stage 1)  │     │  (Stage 2)  │     │  (Stage 3)  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │                   │
       └───────────────────┴───────────────────┴───────────────────┘
                                    │
                              ┌─────▼─────┐
                              │   Redis   │
                              └─────┬─────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
        ┌─────▼─────┐        ┌─────▼─────┐        ┌─────▼─────┐
        │ Telegram  │        │ Telegram  │        │ Telegram  │
        │   High    │        │   Chains  │        │  Calendar │
        └───────────┘        └───────────┘        └───────────┘
```

## Features

- **Multi-chain Support**: Solana, Ethereum, Base, BSC, Arbitrum, Monad, and 30+ chains
- **AI-Powered Analysis**: LLM-based project verification and monitoring
- **AlphaGate Integration**: Track key followers and alpha hunters
- **Launch Calendar**: Automated launch date detection and alerts
- **Chain-specific Telegram Groups**: Route alerts to chain-specific groups

## Services

| Service | Description |
|---------|-------------|
| `collector` | Collects tweets from Twitter API |
| `triage` | Stage 1 - Initial project detection |
| `verifier` | Stage 2 - Deep project verification |
| `monitor` | Stage 3 - Ongoing project monitoring |
| `telegram-high` | High priority alerts |
| `telegram-chains` | Chain-specific group routing |
| `calendar-alerter` | Launch date alerts |

## Setup

1. Copy `.env.example` to `.env` and fill in your API keys
2. Run `docker-compose up -d --build`

## Environment Variables

```env
# Twitter API
TWITTER_API_KEY=your_key

# OpenRouter (LLM)
OPENROUTER_KEY=your_key

# Supabase
SUPABASE_URL=your_url
SUPABASE_KEY=your_key

# Telegram Bots
TELEGRAM_BOT_TOKEN_HIGH=your_token
TELEGRAM_BOT_TOKEN_CHAINS=your_token

# Chain Group IDs
TELEGRAM_CHAT_ID_SOLANA=-100xxx
TELEGRAM_CHAT_ID_BASE=-100xxx
# ... etc
```

## License

Private - All rights reserved


