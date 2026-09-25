---
name: fp-check
description: Verifica sistematicamente um finding/candidate de segurança para decidir se o mecanismo é verdadeiro ou falso positivo, buscando evidência de reachability, preconditions, mitigations e impacto. Use para “esse bug é real?”, “é explorável?” ou “é false positive?”, não para hunting inicial.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; verification is read-only unless separate supervised execution is requested.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits fp-check"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/fp-check"
  luna-domain: "offensive-security"
  luna-purpose: "false-positive-verification"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "155"
  luna-triggers: "false positive, true positive, bug real, vulnerabilidade real, verificar finding, validar finding, esse finding é real, esse finding e real, é explorável, e exploravel"
  luna-requires-any: "finding, vulnerability, vulnerabilidade, bug, candidate, achado"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "medium"
  luna-auto-min-score: "10"
  luna-exclusive-group: "finding-verification"
allowed-tools: Read Grep Glob
---

# FP Check — Luna Cyber

## Gate
Existe um candidate/finding específico. Sem isso, não use esta skill.

## Verification chain
1. Reproduza a alegação exatamente: source, sink, boundary ou invariant.
2. Confirme reachability do caminho.
3. Liste todas as preconditions controláveis e não controláveis.
4. Procure mitigations/checks em caller, callee, framework e deployment.
5. Procure counter-evidence deliberadamente.
6. Distinga “não consegui provar” de “refutado”.
7. Só chame de exploitable quando houver mecanismo e impacto sustentados.

## Verdicts
- `TRUE_POSITIVE` — mecanismo demonstrado.
- `FALSE_POSITIVE` — uma premissa necessária foi refutada.
- `INSUFFICIENT_EVIDENCE` — faltam fatos para concluir.

## Output
```text
FINDING VERIFICATION
Claim:
Root cause:
Reachability:
Preconditions:
Mitigations checked:
Counter-evidence:
Evidence:
Verdict:
Impact if TP:
Missing evidence if unresolved:
```
