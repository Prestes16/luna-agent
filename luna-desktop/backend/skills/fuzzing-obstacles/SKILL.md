---
name: fuzzing-obstacles
description: Identifica e contorna de forma controlada barreiras que impedem o fuzzer de alcançar código profundo — checksums, magic values, crypto validation e estado não determinístico — mantendo patches de fuzzing isolados e medindo cobertura antes/depois.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; source modifications/builds for fuzzing require operator-controlled workflow.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits Testing Handbook / fuzzing-obstacles"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/testing-handbook-skills/skills/fuzzing-obstacles"
  luna-domain: "security-testing"
  luna-purpose: "fuzz-barrier-removal"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "135"
  luna-triggers: "fuzzing obstacle, obstáculo de fuzzing, obstaculo de fuzzing, checksum bloqueia fuzzer, magic value bloqueia fuzzer, fuzzer stuck validation, fuzzer preso na validação, fuzzer preso na validacao, fuzz barrier, coverage behind checksum"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "medium"
  luna-auto-min-score: "10"
  luna-exclusive-group: "fuzz-barrier"
allowed-tools: Read Grep Glob
---

# Fuzzing Obstacles — Luna Cyber

## Workflow
1. Use coverage/evidence para localizar o gate real.
2. Classifique a barreira: checksum/hash, signature/crypto, magic, state setup, nondeterminism.
3. Prefira seed/dictionary/structured generator quando isso preserva produção.
4. Se patch de fuzzing for necessário, isole atrás de build flag claramente insegura para produção.
5. Mantenha cheap validation que ajuda o fuzzer.
6. Evite criar estados impossíveis que gerem false positives downstream.
7. Meça cobertura antes/depois e documente divergência do build real.
8. Nunca confunda crash dependente do patch com bug reproduzível em produção.

## Output
```text
FUZZING OBSTACLE
Blocking check:
Evidence:
Preferred bypass strategy:
Production divergence:
False-positive risk:
Coverage before/after:
Reproduction requirements:
```
