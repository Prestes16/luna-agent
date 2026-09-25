---
name: mutation-testing
description: Planeja e interpreta mutation testing para descobrir testes fracos, mutants sobreviventes, equivalent mutants e gaps que escondem bugs. Use quando o usuário mencionar mutation testing, mewt, muton ou surviving mutants; não para cobertura comum sem mutação.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; campaign execution remains supervised.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits mutation-testing"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/mutation-testing"
  luna-domain: "security-testing"
  luna-purpose: "test-strength-analysis"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "125"
  luna-triggers: "mutation testing, testes de mutação, testes de mutacao, mewt, muton, surviving mutant, mutant survived, mutante sobrevivente"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "medium"
  luna-auto-min-score: "10"
  luna-exclusive-group: "test-strength"
allowed-tools: Read Grep Glob
---

# Mutation Testing — Luna Cyber

## Workflow
1. Defina escopo e operadores de mutação relevantes.
2. Baseline: suíte deve estar verde antes da campanha.
3. Preserve tempo/seed/configuração.
4. Para cada survivor relevante, determine:
   - equivalente semanticamente;
   - código não alcançado;
   - assertion fraca;
   - behavior não testado;
   - bug real exposto.
5. Não maximize mutation score cegamente; priorize mutants em security boundaries/invariants.
6. Crie teste que falha no mutant e passa no original quando o gap for real.

## Output
```text
MUTATION REVIEW
Scope/tool:
Baseline:
Mutation operators:
Killed:
Survived:
Equivalent:
Security-relevant survivors:
Tests to add:
Coverage/timeout limits:
```
