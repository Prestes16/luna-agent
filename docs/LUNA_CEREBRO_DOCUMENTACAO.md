# Documentação do Cérebro da Luna — Versão Completa

**Data:** 2026-04-08  
**Projeto:** Luna Agent — Agente Pessoal Premium  
**Autor:** Manus AI (em colaboração com Cleiton)

---

## Visão Geral

O cérebro da Luna é composto por uma arquitetura modular de prompts, workspaces, serviços de memória e um runtime autônomo. Esta documentação descreve tudo que foi construído e como cada componente se conecta.

---

## 1. Arquitetura de Prompts (Sistema Nervoso Central)

O system prompt da Luna é montado dinamicamente pela função `build_system_prompt(mode)` no `app/main.py`. Ele combina os seguintes arquivos em ordem:

| Arquivo | Função |
|---|---|
| `prompts/identity.md` | Define quem é a Luna, sua missão e modos disponíveis |
| `prompts/rules.md` | Regras invioláveis de comportamento |
| `prompts/memory-viva.md` | Memória operacional viva: contexto do projeto, conhecimento Solana e bug bounty |
| `prompts/voice-personality.md` | Tom de voz, personalidade e estilo de comunicação |
| `prompts/workstyle.md` | Como a Luna trabalha: método 1x1, anti-fantasia, ciclo de raciocínio |
| `prompts/modes/{modo}.md` | Prompt especializado do modo ativo |
| Workspace ativo | Contexto do projeto atual (PROJECT_CONTEXT + CURRENT_STATUS + NEXT_STEPS) |

### Modos Disponíveis

| Modo | Arquivo | Especialização |
|---|---|---|
| `dev` | `prompts/modes/dev.md` | Desenvolvimento geral (padrão) |
| `hunter` | `prompts/modes/hunter.md` | Bug bounty e hacking ético |
| `solana` | `prompts/modes/solana.md` | Desenvolvimento e auditoria Solana |
| `recon` | `prompts/modes/recon.md` | Reconhecimento e OSINT |
| `code_review` | `prompts/modes/code_review.md` | Revisão de código com foco em segurança |

**Como ativar um modo:** Enviar `"mode": "hunter"` (ou outro) no payload do `/chat`.

---

## 2. Sistema de Memória

A Luna possui dois níveis de memória integrados ao contexto de cada conversa:

### Memória de Curto Prazo (STM — Short-Term Memory)
- Armazenada em memória RAM por sessão.
- Mantém o histórico recente da conversa (últimas 8 mensagens por padrão).
- Gerenciada por `app/services/memory.py` via `stm_add()` e `stm_get()`.

### Memória de Longo Prazo (LTM — Long-Term Memory)
- Armazenada em SQLite por workspace.
- Persiste entre sessões e reinicializações.
- Gerenciada por `app/services/memory.py` via `ltm_add()`, `ltm_get_facts()` e `ltm_save_fact()`.
- Integrada automaticamente ao contexto do `/chat` via `build_memory_context()`.

### Memória Viva (Operacional)
- Arquivo `prompts/memory-viva.md` — editado manualmente ou pela Luna.
- Contém o contexto do projeto, preferências do Cleiton, conhecimento especializado e posicionamento estratégico.
- Sempre carregado no system prompt.

---

## 3. Workspaces

Cada workspace é uma pasta em `workspaces/` com arquivos de contexto padronizados:

| Arquivo | Conteúdo |
|---|---|
| `PROJECT_CONTEXT.md` | Visão, objetivo e stack do projeto |
| `CURRENT_STATUS.md` | O que está funcionando e o que está em andamento |
| `NEXT_STEPS.md` | Próximas ações priorizadas |
| `PREFERENCES_CLEITON.md` | Preferências e regras específicas do Cleiton |
| `SESSION_LOG.md` | Log de sessões e eventos importantes |
| `DECISIONS_LOG.md` | Decisões técnicas e estratégicas registradas |
| `BUGS_AND_FIXES.md` | Bugs encontrados, corrigidos e aprendizados |
| `SECURITY_GUARDS.md` | Regras de segurança e condições de parada |
| `AUTONOMY_POLICY.md` | Política de autonomia do agente neste workspace |
| `EXECUTION_LOG.md` | Log de execuções do agente autônomo |

### Workspaces Disponíveis

| Workspace | Foco |
|---|---|
| `luna-agent` | Projeto principal da Luna |
| `bug-bounty` | Caçadas de bug bounty e security research |
| `solana-dev` | Desenvolvimento Solana / Bags Shield |

**Como trocar workspace:** `POST /workspace/switch` com `{"workspace": "bug-bounty"}`.

---

## 4. Guards de Segurança

O sistema de guards (`app/services/guards.py`) protege a Luna em três camadas:

| Guard | Função |
|---|---|
| **Identity Guard** | Bloqueia tentativas de alterar a identidade da Luna |
| **Scope Guard** | Bloqueia pedidos maliciosos (malware, dano real, etc.) |
| **Safe Mode Guard** | Detecta contexto ofensivo e prefixar resposta com aviso ético |

O Safe Mode Guard foi calibrado para **não bloquear** pesquisa de segurança legítima (bug bounty, auditoria Solana). Ele apenas adiciona o prefixo: `"Contexto de segurança / bug bounty detectado. Respondendo com postura de hacking ético: evidência > pressa, uma hipótese por vez."`.

---

## 5. Runtime Autônomo (Agent Runtime)

O `app/agent_runtime.py` implementa o ciclo de autonomia da Luna:

```
plan() → preview() → execute()
```

### Fluxo de Autonomia

1. **`plan(objective)`** — Analisa a intenção do objetivo e gera um `AgentPlan` com ações propostas.
2. **`preview(action)`** — Retorna o que a ação faria, sem executar. Para revisão humana.
3. **`execute(action)`** — Executa a ação dentro dos limites de segurança definidos pela `AgentPolicy`.

### Ferramentas Disponíveis

| Ferramenta | Risco | Aprovação |
|---|---|---|
| `list_dir` | Baixo | Não (por padrão) |
| `read_file` | Baixo | Não (por padrão) |
| `read_log` | Baixo | Não (por padrão) |
| `write_patch` | Médio | Sim (por padrão) |
| `run_command` | Médio/Alto | Sim (por padrão) |
| `deploy` | Alto | Sempre |

### Endpoints do Agente

| Endpoint | Método | Função |
|---|---|---|
| `/agent/plan` | POST | Gera um plano para o objetivo |
| `/agent/preview` | POST | Prévia do plano sem executar |
| `/agent/execute` | POST | Executa o último plano |
| `/agent/state` | GET | Estado atual do agente |
| `/agent/audit` | GET | Audit log de execuções |
| `/agent/approve` | POST | Aprova ou nega uma ação pendente |

---

## 6. Conhecimento Especializado Incorporado

### Solana / Anchor Framework

A `memory-viva.md` e o `prompts/modes/solana.md` incorporam conhecimento profundo sobre:

- Arquitetura de contas da Solana (stateless programs, PDAs).
- Vulnerabilidades críticas: Missing Signer Check, Missing Ownership Check, Integer Overflow, Unsafe CPI, PDA Sharing.
- Token-2022 Extensions: Permanent Delegate, Transfer Fees, Transfer Hook, Mint Close Authority.
- Checklist de segurança pré-deploy (baseado em 50+ audits reais).
- Boas práticas do Anchor Framework: constraints, error handling, testes de exploração.

### Bug Bounty / Hacking Ético

O `prompts/modes/hunter.md` e `prompts/modes/recon.md` incorporam:

- Fluxo profissional: Recon → Hipótese → Validação mínima → PoC → Relatório.
- OWASP Top 10 atualizado (Broken Access Control, Injection, SSRF, etc.).
- BOLA/IDOR, Business Logic Flaws, JWT vulnerabilities.
- Estrutura de relatório premium para triagem de alta qualidade.
- Regras anti-fantasia: nunca inventar vulnerabilidades, impacto ou payloads.

---

## 7. Endpoints Principais da API

| Endpoint | Método | Função |
|---|---|---|
| `/chat` | POST | Chat principal com suporte a `mode` |
| `/chat/stream` | POST | Chat com streaming SSE |
| `/workspace/switch` | POST | Trocar workspace ativo |
| `/workspace/context` | GET | Ver contexto do workspace |
| `/workspaces` | GET | Listar workspaces disponíveis |
| `/memory/fact` | POST | Salvar fato na LTM |
| `/memory/facts` | GET | Listar fatos da LTM |
| `/agent/plan` | POST | Planejar ação autônoma |
| `/agent/execute` | POST | Executar ação autônoma |
| `/agent/approve` | POST | Aprovar ação pendente |
| `/health` | GET | Status do sistema |

---

## 8. Como Usar os Modos na Prática

### Iniciar uma sessão de Bug Bounty
```json
POST /chat
{
  "message": "Vamos caçar bugs no programa X. Começa pelo recon.",
  "mode": "hunter",
  "session_id": "bb-sessao-01"
}
```

### Iniciar uma sessão de desenvolvimento Solana
```json
POST /chat
{
  "message": "Quero implementar a instrução de depósito no Bags Shield.",
  "mode": "solana",
  "session_id": "sol-sessao-01"
}
```

### Fazer code review de segurança
```json
POST /chat
{
  "message": "Revisa esse contrato Anchor para mim.",
  "mode": "code_review",
  "session_id": "review-01"
}
```

### Trocar para o workspace de bug bounty
```json
POST /workspace/switch
{
  "workspace": "bug-bounty"
}
```

---

## 9. Próximos Passos Recomendados

1. **Seletor de modo na UI** — Adicionar dropdown de modo (dev/hunter/solana/recon/code_review) no `index.html`.
2. **Seletor de workspace na UI** — Mostrar o workspace ativo e permitir troca sem precisar da API.
3. **Ferramentas especializadas** — Implementar `app/tools/recon_tool.py` e `app/tools/solana_tool.py` para automação de tarefas específicas.
4. **Painel de dossiês** — Criar uma view na UI para gerenciar achados de bug bounty.
5. **Streaming melhorado** — Garantir que o `/chat/stream` também suporte o campo `mode`.

---

## Resumo das Mudanças Realizadas

| Arquivo | Tipo | Mudança |
|---|---|---|
| `prompts/identity.md` | Editado | Adicionados modos e especialização Solana |
| `prompts/memory-viva.md` | Editado | Conhecimento Solana e bug bounty expandido |
| `prompts/modes/hunter.md` | **Criado** | Modo Bug Bounty completo |
| `prompts/modes/solana.md` | **Criado** | Modo Solana completo |
| `prompts/modes/recon.md` | **Criado** | Modo Reconhecimento completo |
| `prompts/modes/code_review.md` | **Criado** | Modo Code Review completo |
| `app/main.py` | Editado | `build_system_prompt(mode)`, integração LTM, endpoints `/agent/*` |
| `app/agent_runtime.py` | Editado | Lógica de planejamento por intenção, método `preview()` |
| `app/agent_state_store.py` | Editado | `load_agent_config()`, `load_agent_state()`, `approve_action()` expandido |
| `app/agent_models.py` | Editado | `ApprovalDecision` com `approved_by` e `deny_reason` |
| `app/services/guards.py` | Editado | Safe Mode calibrado para bug bounty ético, preface atualizado |
| `workspaces/bug-bounty/` | **Criado** | Workspace completo com 9 arquivos |
| `workspaces/solana-dev/` | **Criado** | Workspace completo com 9 arquivos |
| `workspaces/luna-agent/CURRENT_STATUS.md` | Editado | Status atualizado com novas capacidades |
| `workspaces/luna-agent/NEXT_STEPS.md` | Editado | Próximos passos atualizados |
| `workspaces/luna-agent/PROJECT_CONTEXT.md` | Editado | Objetivo atualizado |
