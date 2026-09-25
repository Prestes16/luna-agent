---
name: spec-to-code-compliance
description: Compara implementação com whitepaper, protocol spec, design document ou documentação normativa, classificando requisitos implementados, contraditos, ausentes e comportamentos de código não documentados. Use somente quando existem spec e código a comparar.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; read-only comparison of provided/available documentation and code.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits spec-to-code-compliance"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/spec-to-code-compliance"
  luna-domain: "protocol-security"
  luna-purpose: "spec-implementation-compliance"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "145"
  luna-triggers: "spec to code, spec-to-code, whitepaper vs code, comparar especificação com código, comparar especificacao com codigo, protocol spec compliance, implementação vs documentação, implementacao vs documentacao, design document vs code"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "high"
  luna-auto-min-score: "10"
  luna-exclusive-group: "spec-compliance"
allowed-tools: Read Grep Glob
---

# Spec-to-Code Compliance — Luna Cyber

## Gate
É obrigatório haver documentação normativa e implementação. Não infira uma spec a partir do próprio código.

## Workflow
1. Fixe versão/revisão de ambos.
2. Extraia requisitos testáveis da spec com citações.
3. Mapeie cada requisito a implementação/evidência.
4. Classifique:
   - IMPLEMENTED;
   - CONTRADICTED;
   - ABSENT;
   - PARTIAL/AMBIGUOUS.
5. Registre comportamento material de código não mencionado pela spec.
6. Quando a spec for ambígua, não trate sua interpretação como requisito.
7. Divergência é finding de compliance; impacto de segurança exige análise adicional.

## Output
```text
SPEC-CODE MATRIX
Spec/revision:
Code/revision:
Requirement -> implementation -> verdict -> evidence
Contradictions:
Absent requirements:
Undocumented behavior:
Ambiguities:
Security-relevant divergences:
Coverage gaps:
```
