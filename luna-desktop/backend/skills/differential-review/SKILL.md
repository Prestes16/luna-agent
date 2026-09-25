---
name: differential-review
description: Faz revisão diferencial de segurança sobre PRs, commits e diffs, usando baseline, histórico Git, classificação de risco, cobertura de testes e blast radius para avaliar o que a mudança pode quebrar. Use quando houver mudança concreta para revisar, inclusive regressões de segurança.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; read-only review workflow; git commands may be proposed but execution remains supervised.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits differential-review"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/differential-review"
  luna-domain: "offensive-security"
  luna-purpose: "security-diff-review"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "140"
  luna-triggers: "review diff, revisar diff, revisão de diff, revisao de diff, security review do commit, revisar commit, review commit, revisar pr, review pr, pull request de segurança, pull request de seguranca, blast radius, git diff"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "medium"
  luna-auto-min-score: "10"
  luna-exclusive-group: "change-review"
allowed-tools: Read Grep Glob Bash
---

# Differential Review — Luna Cyber

## Objetivo

Avaliar uma mudança **comparando-a ao baseline**, não como código isolado. O tamanho do diff não define risco.

## Quando usar

Use quando existe PR, commit, patch ou diff. Não use para greenfield sem baseline.

## Workflow

1. **Pin de baseline e head**: refs/SHAs exatos quando disponíveis.
2. **Inventário do diff**: arquivos, símbolos, linhas removidas/adicionadas.
3. **Classificação de risco**:
   - HIGH: auth, autorização, crypto, parsing, value transfer, external call, privilege, validation removal;
   - MEDIUM: business logic, state transition, API pública;
   - LOW: mudança comprovadamente cosmética/documental.
4. **Histórico**: blame/log em segurança removida ou comportamento alterado.
5. **Blast radius**: callers, dependências, interfaces, configs e consumidores afetados.
6. **Cobertura**: testes existentes e lacunas para código modificado.
7. **Adversarial pass**: para HIGH, derive preconditions e cenários concretos sem inflar impacto.
8. **Regressão**: verifique se a mudança restaura bug anterior ou quebra invariantes.
9. **Relatório com limitações**.

## Métricas mínimas

Não use contagem de linhas como risco. Quando possível registre:
- número de callers diretos relevantes;
- arquivos/componentes afetados;
- testes tocando os símbolos alterados;
- caminhos de erro/cleanup alterados;
- mudanças em boundary/authority.

## Racionalizações a rejeitar

- “PR pequena = revisão rápida.”
- “É só refactor.”
- “Conheço esse código.”
- “Sem testes não é parte da revisão.”
- “Blast radius parece óbvio.”
- “O commit diz fix/security, logo é seguro.”

## Contrato de saída

```text
DIFFERENTIAL SECURITY REVIEW
Base:
Head:
Scope:
Changed files:
Risk classification:
Security-sensitive deltas:
History evidence:
Blast radius:
Test coverage:
Regression candidates:
Adversarial scenarios:
Findings supported by evidence:
Unverified concerns:
Coverage gaps:
```

Finding precisa apontar para mudança + mecanismo + pré-condições + evidência.
