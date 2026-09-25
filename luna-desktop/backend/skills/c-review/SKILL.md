---
name: c-review
description: Faz revisão de segurança de C/C++ userspace para memory corruption, integer bugs, lifetime/ownership, races, parsing e platform-specific issues. Use em aplicações nativas, daemons, bibliotecas e serviços C/C++; não use para Rust ou smart contracts.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; read-only review procedure; compilation/sanitizers remain supervised.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits c-review"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/c-review"
  luna-domain: "native-security"
  luna-purpose: "c-cpp-security-review"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "145"
  luna-triggers: "c security review, c++ security review, audit c++, auditoria c++, memory corruption, use-after-free, use after free, integer overflow c, race condition c++, double free, buffer overflow c++"
  luna-exclude-triggers: "solana, solidity"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "high"
  luna-auto-min-score: "10"
  luna-exclusive-group: "language-security-review"
allowed-tools: Read Grep Glob
---

# C/C++ Review — Luna Cyber

## Workflow
1. Fixe target/toolchain/platform e entry points.
2. Mapeie ownership/lifetime e buffers controláveis externamente.
3. Revise arithmetic de tamanho, truncation, signedness, overflow/underflow e alloc size.
4. Revise UAF/double-free/leak/error cleanup.
5. Revise parsing, format strings, command/path handling e serialization.
6. Revise concurrency/shared state e TOCTOU.
7. Revise privilege/FFI/syscall boundaries.
8. Ligue candidates a reachability, preconditions e impacto.
9. Indique sanitizers/fuzzing apenas quando úteis e não finja execução.

## Anti-atalhos
- “80% de cobertura é praticamente tudo.”
- “É biblioteca interna, input é confiável.”
- “ASan limpo prova ausência de memory bugs.”
- “Tamanho pequeno elimina integer overflow.”

## Output
```text
C/C++ SECURITY REVIEW
Target/platform:
Entry points:
Memory/lifetime:
Integer/size:
Concurrency:
Parsing/boundaries:
Findings:
Rejected candidates:
Coverage gaps:
```
