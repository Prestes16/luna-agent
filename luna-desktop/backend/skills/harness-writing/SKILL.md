---
name: harness-writing
description: Projeta e melhora fuzzing harnesses para C/C++ e Rust, convertendo bytes em inputs significativos, preservando determinismo e evitando crashes causados pelo próprio harness. Use para LLVMFuzzerTestOneInput, cargo-fuzz/fuzz_target ou campanha com cobertura ruim.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; harness design is procedural; code writing/build/run remains operator-controlled.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits Testing Handbook / harness-writing"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/testing-handbook-skills/skills/harness-writing"
  luna-domain: "security-testing"
  luna-purpose: "fuzz-harness-design"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "130"
  luna-triggers: "fuzz harness, fuzzing harness, harness de fuzz, harness libfuzzer, llvmfuzzertestoneinput, fuzz_target, cargo fuzz harness, escrever harness, melhorar harness de fuzz"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
allowed-tools: Read Grep Glob
---

# Harness Writing — Luna Cyber

## BUILD-TO-BREAK aplicado a fuzzing

Entenda a API/SUT antes de alimentar bytes aleatórios. Um harness ruim mede o harness, não o target.

## Workflow

1. Identifique entry points que consomem input externo, parser, protocol, crypto ou state machine.
2. Comece pelo harness mínimo que chama o SUT.
3. Defina size bounds somente quando necessários para a API.
4. Estruture input em campos/tipos sem tornar estados interessantes inalcançáveis.
5. Preserve determinismo: mesma entrada → mesmo comportamento observável.
6. Isole filesystem/network/time/random quando não forem parte do target.
7. Evite crash no harness por cast/alignment/out-of-bounds.
8. Para APIs stateful, modele sequência de operações com encoding explícito.
9. Compile/teste smoke quando execução for autorizada.
10. Meça cobertura com `coverage-analysis` antes de concluir eficácia.

## Anti-padrões

- rejeitar quase todo input;
- exigir checksum/magic complexo sem seed/dictionary quando isso bloqueia o SUT;
- introduzir UB no próprio harness;
- usar rede externa e relógio real;
- reset incompleto entre cases;
- chamar apenas happy path.

## Contrato de saída

```text
FUZZ HARNESS DESIGN
SUT:
Target entry points:
State/reset model:
Input encoding:
Size/bounds:
Determinism controls:
Harness skeleton:
Expected crash boundary:
Seeds/dictionary candidates:
Known harness false-positive risks:
Coverage measurement plan:
```
