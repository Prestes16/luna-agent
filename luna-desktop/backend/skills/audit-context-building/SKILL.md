---
name: audit-context-building
description: Constrói um modelo verificável de uma codebase antes da caça de vulnerabilidades, mapeando funções, dependências, trust boundaries, invariantes, suposições e perguntas em aberto. Use no início de auditorias, threat models, revisões de arquitetura e análises de código desconhecido.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; procedural read-only guidance; no host execution authority.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits audit-context-building"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/audit-context-building"
  luna-domain: "offensive-security"
  luna-purpose: "pre-audit-context"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "100"
  luna-triggers: "iniciar auditoria desta codebase, começar auditoria desta codebase, comecar auditoria desta codebase, threat model, modelo de ameaça, architecture review, revisão de arquitetura, revisao de arquitetura, codebase desconhecida, código desconhecido, codigo desconhecido, entender o código, entender o codigo, mapear arquitetura, superfície de ataque, superficie de ataque"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "medium"
  luna-auto-min-score: "10"
  luna-exclusive-group: "context-foundation"
  luna-complements: "solana-vulnerability-scanner, entry-point-analyzer"
allowed-tools: Read Grep Glob
---

# Audit Context Building — Luna Cyber

## Contrato operacional

Construa entendimento antes de procurar falhas. Esta skill é uma etapa de **pré-auditoria**: reconstrói como o sistema deveria funcionar, quais estados e dados atravessam cada boundary e quais suposições sustentam o comportamento observado.

Princípio Luna: **SABER CONSTRUIR PRA PODER QUEBRAR/DESMONTAR**. Antes de desmontar segurança, modele componentes, fluxo, estado, autoridade, invariantes e dependências.

Esta skill é procedural e read-only. `allowed-tools` descreve a intenção da skill, mas **não concede autoridade**. O `AgentHarness`, `ExecutionIntent` e o executor supervisionado continuam sendo as únicas fontes de autoridade operacional.

## Quando usar

Use quando:
- a codebase, contrato, firmware, serviço ou componente ainda não é suficientemente conhecido;
- o operador iniciar uma auditoria, threat model ou revisão de arquitetura;
- for necessário mapear superfície de ataque antes do hunting;
- findings anteriores estiverem difíceis de julgar por falta de contexto;
- o objetivo for entender dependências, trust boundaries, invariantes e assumptions.

Não desperdice contexto repetindo esta fase quando o sistema já estiver bem modelado e a evidência atual não tiver mudado materialmente.

## Quando NÃO usar

Esta skill **não conclui vulnerabilidades**, não atribui severidade, não escreve PoC, não escolhe payload e não prescreve correção.

Quando uma suposição parecer não enforced, registre-a como `não confirmado / nada encontrado` e carregue-a para a fase de hunting. Não converta ausência de evidência em finding.

## Fluxo de trabalho

### Fase 0 — Scope e evidência

1. Fixe alvo, versão/commit, caminhos e artefatos efetivamente fornecidos.
2. Separe fatos observados, inferências e desconhecidos.
3. Nunca trate nome de função, comentário ou documentação como prova de enforcement.
4. Registre qualquer parte necessária mas ausente como pergunta em aberto.

### Fase 1 — Reconstrução da arquitetura

Mapeie:
- componentes e responsabilidades;
- entry points;
- callers/callees relevantes;
- fontes e sinks de dados;
- estados lidos e modificados;
- boundaries de privilégio, identidade, processo, rede, contrato e persistência;
- mecanismos de autenticação/autorização;
- serialização, parsing, validação e conversões de unidades.

### Fase 2 — Microanálise de funções

Para cada função relevante, registre o formato de `references/ANALYSIS_FORMAT.md`.

A regra principal é **seguir as chamadas**. Se a segurança do caller depende do callee, leia o callee e determine qual caminho realmente estabelece a propriedade esperada. Nome de função não comprova comportamento.

### Fase 3 — Invariantes e suposições

Identifique:
- o que deve ser sempre verdadeiro;
- onde cada propriedade é estabelecida;
- onde ela é checada novamente;
- o que é aceito por confiança;
- qual input externo pode invalidá-la;
- quais checks ocorrem apenas no cliente/UI;
- quais unidades, tipos numéricos ou domínios de representação estão implícitos.

Quando não encontrar enforcement, escreva literalmente `nada encontrado` em vez de inventar mecanismo.

### Fase 4 — Trust boundaries e fluxo de autoridade

Para cada boundary responda:
- quem controla o dado antes e depois;
- qual identidade/privilégio é assumido;
- onde ocorre validação;
- onde ocorre mudança de estado;
- qual componente tem autoridade para rejeitar;
- qual evidência demonstra isso.

### Fase 5 — Dossiê de contexto

Produza um dossiê compacto contendo:
1. escopo e versão;
2. arquitetura e fluxos;
3. entry points;
4. trust boundaries;
5. invariantes;
6. assumptions sem enforcement confirmado;
7. pontos de alta complexidade/acoplamento;
8. perguntas em aberto;
9. trilhas de evidência por arquivo/função/linha;
10. hipóteses de hunting **não confirmadas**, sem chamar de vulnerabilidade.

### Fase 6 — Handoff

Entregue somente o contexto necessário para a próxima skill. O hunting posterior deve partir das assumptions, boundaries e perguntas em aberto do dossiê, não reiniciar a análise do zero.

## Regras de evidência

- Toda afirmação sobre implementação deve apontar para arquivo/função/linha ou artefato equivalente quando disponível.
- Se duas fontes discordarem, preserve a contradição; não reconcilie silenciosamente.
- Se um callee não puder ser inspecionado, marque a dependência como opaca.
- Se faltar código, log, configuração ou versão para fechar uma conclusão, declare a lacuna.
- Diferencie enforcement real de comentário, intenção, naming e check apenas visual.
- Em matemática/protocolo, registre domínio numérico, unidade, arredondamento e bounds antes de inferir invariantes.

## Racionalizações a rejeitar

- “A função se chama `validate`, então valida tudo.”
- “O diff é pequeno, então o contexto não importa.”
- “A UI bloqueia, portanto o backend também bloqueia.”
- “O comentário diz que é admin-only, então há autorização.”
- “Não achei o check rapidamente, então existe vulnerabilidade.”
- “O teste feliz passou, então todos os caminhos preservam a invariável.”
- “Esse valor parece pequeno, então overflow/rounding não importa.”

## Contrato de saída

Use esta estrutura:

```text
AUDIT CONTEXT
Scope:
Architecture:
Entry points:
Trust boundaries:
Critical state/data flows:
Invariants:
Unenforced assumptions:
  - <assumption> -> enforcement: <evidence | nada encontrado>
Opaque dependencies:
Open questions:
High-complexity areas:
Hunting hypotheses (UNVERIFIED):
Evidence index:
```

Nunca promova `Hunting hypotheses (UNVERIFIED)` a finding nesta skill.
