---
name: zeroize-audit
description: Audita limpeza de segredos em C/C++/Rust, verificando missing zeroization, caminhos de controle e casos em que o compilador elimina a limpeza. Use para keys, passwords, seeds, tokens e buffers sensíveis em memória.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; source/assembly review is read-only; compilation remains supervised.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits zeroize-audit"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/zeroize-audit"
  luna-domain: "crypto-security"
  luna-purpose: "secret-memory-hygiene"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "140"
  luna-triggers: "zeroize, zeroization, limpar segredo da memória, limpar segredo da memoria, wipe secret, key memory, secret memory hygiene, compiler removed zeroization, memset otimizado, apagar chave da memória, apagar chave da memoria"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "medium"
  luna-auto-min-score: "10"
  luna-exclusive-group: "secret-memory"
allowed-tools: Read Grep Glob
---

# Zeroize Audit — Luna Cyber

## Workflow
1. Identifique material sensível e seu lifetime.
2. Trace cópias temporárias, stack/heap buffers, serialization e FFI.
3. Verifique cleanup em success, error, early return e panic/exception.
4. Diferencie “source chama memset” de “artefato compilado preserva a limpeza”.
5. Quando assembly/IR estiver disponível, confirme que stores não foram removidos.
6. Revise APIs específicas de zeroization e garantias da linguagem/toolchain.
7. Reporte residual copies e boundaries fora de controle.

## Output
```text
ZEROIZATION REVIEW
Secrets/buffers:
Lifetime/copies:
Cleanup paths:
Compiler/assembly evidence:
Missing zeroization:
Residual copies:
Findings:
Coverage limits:
```
