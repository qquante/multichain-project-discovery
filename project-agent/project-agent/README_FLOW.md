# 🔄 Fluxo do Sistema e Intervalos de Monitoramento

Este documento detalha o funcionamento do pipeline de descoberta de projetos e os intervalos exatos de execução de cada serviço.

## ⏱️ Intervalos de Execução

Aqui estão os tempos configurados atualmente no código:

### 📥 Coleta e Descoberta
| Serviço | Intervalo | O que faz |
|---------|-----------|-----------|
| **Collector** | **3 horas** | Coleta tweets gerais baseados em keywords ("solana memecoin", etc). |
| **Alpha Hunter** | **12 horas** | Busca tweets dos "callers" configurados (ex: AresLabs). |
| **Alpha Followers** | **12 horas** | Verifica quem os seeds seguiram recentemente. |
| **AlphaGate** | **2 horas** | Busca projetos pré-filtrados da API externa AlphaGate. |
| **Discoverer** | **30 minutos** | Investiga menções em tweets de influencers para achar handles de projetos. |

### 🧠 Processamento (Contínuo)
| Serviço | Intervalo/Polling | O que faz |
|---------|-------------------|-----------|
| **Triage** | **Contínuo** (Poll 10s) | Processa tweets com LLM assim que chegam. |
| **Verifier** | **Contínuo** (Poll 30s) | Verifica projetos triados (socials, site, contrato). |

### 👁️ Monitoramento (Projetos Confirmados)
O serviço **Monitor** roda 24/7, mas verifica cada projeto com uma frequência baseada na sua **prioridade**:

| Prioridade | Intervalo de Checagem | Critério Típico |
|------------|-----------------------|-----------------|
| **Critical** | **A cada 8 horas** | Lançamento iminente ("launching soon"). |
| **High** | **A cada 12 horas** | Lançamento esta semana. |
| **Medium** | **A cada 24 horas** | Data agendada futura. |
| **Low** | **A cada 24 horas** | Timeline vaga ou sem data. |

### 🧹 Manutenção
| Serviço | Intervalo | O que faz |
|---------|-----------|-----------|
| **Abandoned Checker** | **7 dias** | Marca como `removed` projetos sem tweets há mais de 30 dias. |

---

## 🌊 Fluxo Detalhado dos Dados

O sistema funciona como um funil com múltiplas entradas.

### 1. Entradas (Sources)
Existem 4 portas de entrada principais:

1.  **Collector (Padrão):**
    *   *Input:* Keywords no Twitter.
    *   *Fluxo:* Twitter -> `tweets.db` -> **Stage 1 (Triage/LLM)**.
2.  **Alpha Hunter:**
    *   *Input:* Tweets de Callers Alpha.
    *   *Fluxo:* Twitter -> `tweets.db` -> **Stage 1 (Triage/LLM)**.
3.  **AlphaGate (VIP):**
    *   *Input:* API AlphaGate.
    *   *Fluxo:* API -> `triaged_projects` -> **PULA Triage** -> **Stage 2 (Verifier)**.
4.  **Alpha Followers (VIP):**
    *   *Input:* Follows de Seeds.
    *   *Fluxo:* Twitter -> `triaged_projects` -> **PULA Triage** -> **Stage 2 (Verifier)**.

### 2. Stage 1: Triagem (Triage)
*   Recebe tweets do Collector e Hunter.
*   **LLM (Gemini/OpenRouter)** analisa o texto: "Isso é um projeto cripto interessante?".
*   Extrai: Nome, Ticker, Chain, Links.
*   *Saída:* Salva em `triaged_projects` e notifica o Verifier.

### 3. Stage 2: Verificação (Verifier)
*   Recebe projetos da Triagem, AlphaGate e Followers.
*   **Verificação Profunda:**
    *   Acessa o perfil do Twitter (Bio, seguidores, idade da conta).
    *   Acessa o Website (se tiver): Busca Whitepaper, Team, Roadmap.
    *   Busca Contrato (CA) no texto ou site.
*   **Calendar Agent:** Tenta descobrir data de lançamento e urgência.
*   *Saída:*
    *   Se `confirmed`: Salva em `verified_projects` e vai para Monitor.
    *   Se `rejected`: Arquiva.

### 4. Stage 3: Monitoramento (Monitor)
*   Vigia periodicamente os projetos confirmados.
*   Detecta mudanças críticas:
    *   **CA Deployado:** Mudança mais importante -> Alerta de Lançamento.
    *   Mudança de Bio/Pinned Tweet.
    *   Crescimento de seguidores.
*   Atualiza o **Launch Calendar** se descobrir novas datas.

### 5. Bot Telegram
*   Ouve os canais do Redis (`projects:confirmed`, `projects:alert`, etc) e envia mensagens formatadas para os grupos.
