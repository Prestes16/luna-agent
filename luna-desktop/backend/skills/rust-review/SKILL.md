---
name: rust-review
description: Faz revisão de segurança profunda em Rust userspace, cobrindo boundaries safe/unsafe, memory safety em unsafe blocks, FFI, concorrência, panic/DoS e async runtime. Use ao auditar crates, serviços e bibliotecas Rust; para programas Solana/Anchor prefira a skill Solana especializada.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; read-only review procedure; build/test execution remains supervised.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits rust-review"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/rust-review"
  luna-domain: "native-security"
  luna-purpose: "rust-security-review"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "145"
  luna-triggers: "rust security review, audit rust, auditoria rust, unsafe rust, ffi rust, memory safety rust, panic dos rust, concorrência rust, concorrencia rust, async rust security"
  luna-exclude-triggers: "solana, anchor, near contract, ink contract"
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

# Rust Review — Luna Cyber

## Use
Auditoria Rust userspace com foco em mecanismos que escapam das garantias normais da linguagem.

## Workflow
1. Fixe crate/workspace, versão/commit e features.
2. Mapeie `unsafe`, FFI, raw pointers, ownership/lifetime bridges e custom allocators.
3. Revise concorrência: atomics, locks, Send/Sync, shared mutable state, cancellation.
4. Revise panic/unwrap/assert em caminhos controláveis externamente e impacto DoS.
5. Revise async: cancellation safety, task leaks, blocking no runtime, state races.
6. Revise integer/size conversions em boundaries, parsing e alocações.
7. Trace cada candidate até reachability e impacto observável.
8. Reporte cobertura e áreas não inspecionadas.

## Racionalizações a rejeitar
- “unsafe é pequeno, então não merece cluster próprio.”
- “Compila, então o FFI é seguro.”
- “panic só derruba uma request.”
- “Rust elimina race conditions.”
- “Safe wrapper prova o unsafe interno.”

## Output
```text
RUST SECURITY REVIEW
Scope/features:
Unsafe/FFI boundaries:
Concurrency/async:
Panic/DoS:
Integer/size boundaries:
Confirmed findings:
Rejected candidates:
Coverage gaps:
```
