---
name: sharp-edges
description: Identifica APIs, configurações e designs que tornam uso inseguro fácil — footguns, defaults perigosos, ergonomia criptográfica ruim e opções ambíguas. Use em revisão de API/configuration design e princípios secure-by-default/misuse-resistant; não para implementation bug comum.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; read-only design review.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits sharp-edges"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/sharp-edges"
  luna-domain: "secure-design"
  luna-purpose: "misuse-resistant-design-review"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "130"
  luna-triggers: "sharp edges, footgun, misuse-resistant, misuse resistant, secure by default, api ergonomics, dangerous configuration, configuração perigosa, configuracao perigosa, pit of success"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "medium"
  luna-auto-min-score: "10"
  luna-exclusive-group: "secure-design"
allowed-tools: Read Grep Glob
---

# Sharp Edges — Luna Cyber

## Workflow
1. Liste decisões que o caller/operator precisa tomar corretamente.
2. Pergunte se o default é seguro e se misuse é fácil de detectar.
3. Revise type/API design, parameter ordering, optional security flags e dangerous escape hatches.
4. Revise configs que permitem fail-open ou combinações contraditórias.
5. Diferencie bug de implementação de design que incentiva bugs futuros.
6. Priorize mudanças que tornam o caminho seguro o mais fácil.

## Output
```text
SHARP-EDGE REVIEW
API/config:
Unsafe-easy paths:
Safe-default status:
Misuse detectability:
Ambiguous options:
Security consequences:
Design improvements:
Evidence:
```
