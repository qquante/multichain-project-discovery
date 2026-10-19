# BMAD Setup — Crypto Alpha Hunting Bot
> Spec-Driven Development setup. Gerado: 2026-04-16

## Estrutura Criada
```
project-agent/
├── AGENTS.md                        ← Constituição do agente (LER PRIMEIRO)
├── docs/
│   ├── requirements.md              ← O QUE o sistema faz (7 requisitos)
│   ├── design.md                    ← COMO funciona (arquitetura, canais, fluxos)
│   └── tasks.md                     ← Tasks com status (14 tasks mapeadas)
└── .agent-memory/
    ├── episodic.jsonl               ← Log de tudo que foi feito (append-only)
    ├── known_bugs.md                ← 7 bugs conhecidos com status
    └── decisions.md                 ← 7 decisões arquiteturais fixadas
```

## Como Usar com Claude Code / Cursor / Qualquer Agente

### Início de cada sessão
Instrua o agente:
```
Leia AGENTS.md, docs/tasks.md e .agent-memory/episodic.jsonl antes de qualquer ação.
```

### Para executar uma task
```
Execute TASK-001 do docs/tasks.md. Siga os critérios de aceite exatamente.
Após concluir, registre em .agent-memory/episodic.jsonl e marque como DONE em tasks.md.
```

### Para verificar o que foi feito
```
Leia .agent-memory/episodic.jsonl e me diga o que foi alterado no projeto.
```

### Para adicionar nova task
```
Adicione em docs/tasks.md com:
- ID sequencial (TASK-015, etc.)
- Prioridade
- Arquivo e linhas afetadas
- O que fazer (código exato se possível)
- Critério de aceite verificável
```

## Ordem Recomendada de Execução
1. TASK-001 (AlphaGate cookies) — CRÍTICO, provavelmente quebrado agora
2. TASK-002 (Alpha-hunter canal) — CRÍTICO, afeta todas as coletas
3. TASK-003 (BATCH_SIZE) — 2 linhas de mudança, alto impacto
4. TASK-004 (Cache AlphaGate) — depende de TASK-001
5. TASK-005 (Schema enforced) — melhora confiabilidade do LLM
6. TASK-006 (Telegram routing) — restaura filtro por chain
7. TASK-007 (Collector consistency) — melhora cobertura de coleta
