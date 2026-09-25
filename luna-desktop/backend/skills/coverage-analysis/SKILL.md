---
name: coverage-analysis
description: Mede e interpreta cobertura de campanhas de fuzzing para saber o que o harness realmente alcança, comparar baseline e mudanças e transformar regiões não cobertas em ações de harness, corpus ou dictionary. Use quando fuzzing plateau, harness muda ou caminhos não são atingidos.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; coverage commands may be proposed; build/execution remains supervised.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits Testing Handbook / coverage-analysis"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/testing-handbook-skills/skills/coverage-analysis"
  luna-domain: "security-testing"
  luna-purpose: "fuzz-coverage-analysis"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "130"
  luna-triggers: "fuzz coverage, cobertura de fuzz, coverage do fuzzer, fuzzer plateau, fuzzing plateau, caminho não alcançado, caminho nao alcancado, llvm-cov fuzz, corpus coverage, cobertura do harness"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
allowed-tools: Read Grep Glob Bash
---

# Coverage Analysis — Luna Cyber

## Objetivo

Cobertura é evidência de **reachability do harness**, não prova de segurança nem ranking universal de fuzzers.

## Workflow

1. Fixe build, target, corpus e toolchain.
2. Gere baseline reproduzível.
3. Execute corpus sob instrumentation apropriada quando autorizado.
4. Colete line/function/branch/basic-block conforme disponível.
5. Compare antes/depois do harness ou campanha.
6. Investigue regiões relevantes não alcançadas:
   - parser gate/magic;
   - checksum/crypto;
   - state setup;
   - missing seed/dictionary;
   - harness encoding;
   - dead/unreachable code.
7. Proponha uma mudança por vez e meça delta.
8. Não sacrifique invariantes de produção sem registrar divergência de build.

## Interpretação

- Coverage ↑ não significa automaticamente bugs ↑.
- Coverage 100% não prova ausência de falhas.
- Coverage plateau pode significar corpus saturado, obstacle, state model ruim ou target inadequado.
- Compare métricas somente com builds/configs compatíveis.

## Contrato de saída

```text
FUZZ COVERAGE
Target/build:
Corpus:
Instrumentation:
Baseline:
Current:
Delta:
High-value uncovered regions:
Likely blockers:
Harness/seed/dictionary actions:
Measurement limitations:
Next experiment:
```
