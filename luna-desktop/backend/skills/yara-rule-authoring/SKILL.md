---
name: yara-rule-authoring
description: Cria, revisa e otimiza regras YARA-X para detecção de malware, escolhendo strings robustas, reduzindo false positives e evitando regras frágeis ou caras. Use para YARA/YARA-X, malware signatures, IOC-based detection e threat hunting baseado em artefatos.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; rule authoring is read-only/procedural; sample execution remains supervised.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits yara-authoring / yara-rule-authoring"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/yara-authoring"
  luna-domain: "malware-analysis"
  luna-purpose: "malware-detection-rule-authoring"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "135"
  luna-triggers: "yara rule, regra yara, yara-x, yara x, malware signature, assinatura de malware, assinatura yara, threat hunting yara, ioc yara"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "medium"
  luna-auto-min-score: "10"
  luna-exclusive-group: "malware-detection-rule"
allowed-tools: Read Grep Glob
---

# YARA-X Rule Authoring — Luna Cyber

## Workflow
1. Fixe família/campanha ou comportamento-alvo e corpus conhecido.
2. Prefira strings estáveis e específicas sobre bytes frágeis/offset fixo.
3. Separe artefatos discriminantes de strings comuns de toolchain/library.
4. Defina condição com custo previsível.
5. Inclua positivos e negativos representativos.
6. Revise false positives em software legítimo semelhante.
7. Evite regra baseada apenas em hash quando o objetivo é família/comportamento.
8. Registre limitações e critérios de manutenção.

## Output
```text
YARA-X RULE PACKAGE
Detection objective:
Stable indicators:
Excluded/common indicators:
Rule:
Positive fixtures:
Negative fixtures:
Performance notes:
False-positive risks:
Known evasion/coverage limits:
```
