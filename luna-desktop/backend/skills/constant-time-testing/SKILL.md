---
name: constant-time-testing
description: Planeja e interpreta testes dinâmicos/estatísticos de timing em implementações criptográficas, incluindo dudect e Timecop/Valgrind. Use quando o objetivo for medir timing variance em binário/runtime; para análise estática/assembly use constant-time-analysis.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; runtime measurement requires explicit supervised execution and controlled environment.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits Testing Handbook / constant-time-testing"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/testing-handbook-skills/skills/constant-time-testing"
  luna-domain: "crypto-security"
  luna-purpose: "runtime-timing-side-channel-testing"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "145"
  luna-triggers: "dudect, timecop, timing variance, variância de timing, variancia de timing, medir timing, statistical timing, teste runtime constant-time, valgrind timing, dynamic timing side-channel"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "high"
  luna-auto-min-score: "10"
  luna-exclusive-group: "timing-runtime"
allowed-tools: Read Grep Glob
---

# Constant-Time Testing — Luna Cyber

## Distinção
Esta skill mede comportamento runtime. Não substitui análise do compiler output.

## Workflow
1. Identifique secret classes e public controls.
2. Garanta ambiente tão estável quanto possível: CPU frequency/noise/affinity quando aplicável.
3. Defina grupos estatísticos que diferem no segredo, não em variáveis públicas irrelevantes.
4. Use dudect/abordagem estatística ou tracing dinâmico conforme o caso.
5. Preserve raw measurements/configuração/seed.
6. Interprete significância com cautela; não transforme ruído em finding.
7. Reproduza em configuração de produção/materialmente equivalente.
8. Combine com `constant-time-analysis` quando precisar explicar o mecanismo.

## Output
```text
TIMING TEST PLAN/RESULT
Target/build:
Secret/public classes:
Environment controls:
Method/tool:
Sample design:
Observed statistic:
Repeatability:
Mechanism linkage:
Verdict:
Limitations:
```
