---
name: semgrep-rule-creator
description: Cria e refina regras Semgrep específicas para uma root cause ou padrão de segurança, com casos positivos/negativos, teste de precisão e taint mode quando apropriado. Use quando o objetivo for escrever uma regra Semgrep customizada, não para rodar rulesets existentes.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; rule authoring is procedural; Semgrep execution remains supervised.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits semgrep-rule-creator"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/semgrep-rule-creator"
  luna-domain: "offensive-security"
  luna-purpose: "custom-static-detection"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "145"
  luna-triggers: "semgrep rule, regra semgrep, criar regra semgrep, custom semgrep, taint rule, regra de taint, detector semgrep"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
allowed-tools: Read Grep Glob Bash
---

# Semgrep Rule Creator — Luna Cyber

## Objetivo

Transformar um mecanismo observado em uma detecção reproduzível sem sacrificar precisão.

## Workflow

1. Fixe linguagem e root cause/padrão desejado.
2. Colete ao menos:
   - caso vulnerável conhecido;
   - caso seguro/negativo;
   - variações sintáticas plausíveis.
3. Inspecione como Semgrep representa a sintaxe/AST quando necessário.
4. Comece pela regra mais específica que encontra o caso conhecido.
5. Generalize incrementalmente.
6. Use **taint mode** quando a vulnerabilidade depende de fluxo source→sink, não apenas forma sintática.
7. Crie testes positivos e negativos.
8. Verifique false positives e false negatives conhecidos.
9. Defina metadata/CWE apenas quando sustentados pelo mecanismo.
10. Produza regra + fixture de teste + comando de validação.

## Regras de qualidade

- Nunca aceite regra que encontra vulnerável e também marca o caso seguro equivalente.
- Não use regex textual se AST/dataflow resolve o mecanismo com maior precisão.
- Não generalize antes do exact match funcionar.
- Evite depender de nomes locais arbitrários quando a semântica pode ser expressa.

## Racionalizações a rejeitar

- “Matchou o exemplo, está pronta.”
- “Um teste é suficiente.”
- “Taint é exagero.”
- “A regra ampla pode ser filtrada depois.”
- “AST é complicado, regex basta.”

## Contrato de saída

```text
SEMGREP RULE PACKAGE
Root cause:
Language:
Detection strategy:
Rule YAML:
Positive fixtures:
Negative fixtures:
Expected matches:
Known limitations:
Validation command:
Variant/generalization notes:
```
