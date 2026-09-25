---
name: entry-point-analyzer
description: Mapeia entry points externos que alteram estado em smart contracts e programas blockchain, classificando acesso, autoridade e trust boundaries antes do hunting. Use para Solidity, Vyper, Solana/Anchor, Move, TON e CosmWasm quando o objetivo for mapear superfície de ataque, funções externas, instruções mutáveis ou operações privilegiadas.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; read-only analysis; tool execution remains controlled by the Luna harness.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits entry-point-analyzer"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/entry-point-analyzer"
  luna-domain: "blockchain-security"
  luna-purpose: "attack-surface-mapping"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "135"
  luna-triggers: "entry point, entry points, pontos de entrada, state-changing, funções externas, funcoes externas, instruções externas, instrucoes externas, superfície de ataque do contrato, superficie de ataque do contrato, privileged operations, operações privilegiadas, operacoes privilegiadas"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
allowed-tools: Read Grep Glob
---

# Entry Point Analyzer — Luna Cyber

## Contrato operacional

Mapeie **todas as operações externamente alcançáveis que podem alterar estado**. Esta skill não conclui vulnerabilidades; ela produz um mapa de superfície de ataque para alimentar auditoria e hunting.

A classificação de acesso deve seguir implementação real. Nome de modifier, decorator, tipo de conta ou comentário não é prova suficiente.

## Quando usar

Use para:
- iniciar auditoria de smart contract/programa já identificado;
- listar instruções/funções state-changing;
- separar operações públicas, role-restricted, admin/governance e contract-only;
- localizar callbacks/CPI/hooks e operações de upgrade/emergência;
- entender quem possui autoridade para alterar estado ou mover valor.

Não use para codebase não blockchain ou para funções puramente read-only.

## Workflow

1. **Detecte plataforma** por arquivos, imports, manifestos e sintaxe.
2. **Fixe scope**: diretórios, commit/versão, programas/contratos incluídos.
3. **Enumere unidades mutáveis** sem pular arquivos relevantes.
4. **Trace access control** até sua implementação real.
5. **Registre estado/valor afetado** e chamadas externas/CPI.
6. **Classifique acesso**:
   - PUBLIC;
   - ROLE_RESTRICTED;
   - ADMIN_GOVERNANCE;
   - CONTRACT_ONLY;
   - RESTRICTED_REVIEW_REQUIRED.
7. **Marque operações críticas**: initialize, upgrade, pause, mint/burn, withdraw, transfer, oracle/config, callback, cross-program/cross-contract.
8. **Produza cobertura**: arquivos analisados, arquivos não analisados e razões.

## Regras por ecossistema

### Solana / Anchor
Considere handlers de instrução, contexts, `Signer`, `Account`, `UncheckedAccount`, `Program`, constraints `seeds/bump`, ownership e CPI. `mut` indica estado alterável, mas não prova autorização.

### Solidity / Vyper
Considere funções externas/públicas não-view/pure, modifiers herdados, fallback/receive, callbacks e upgrade/proxy control.

### Move / TON / CosmWasm
Use a semântica de entry/invoke/execute própria da plataforma; não force conceitos EVM.

## Racionalizações a rejeitar

- “O modifier se chama onlyOwner, então está validado.” → leia sua implementação/herança.
- “É callback, então não importa.” → callback é trust boundary.
- “Altera pouco estado.” → qualquer mutação pode violar invariantes.
- “Framework garante.” → cite qual constraint/tipo concretamente garante.
- “Não encontrei entry point por grep simples.” → confirme macros, dispatch e geração de handlers.

## Contrato de saída

```text
ENTRY POINT MAP
Scope:
Platform/language:
Files covered:
Files not covered:

PUBLIC:
- function/instruction -> file:line -> state/value -> evidence

ROLE_RESTRICTED:
- function/instruction -> restriction -> implementation evidence

ADMIN_GOVERNANCE:
- ...

CONTRACT_ONLY / CALLBACKS:
- expected caller -> enforcement evidence

RESTRICTED_REVIEW_REQUIRED:
- observed restriction pattern -> unresolved question

Critical operations:
External/CPI calls:
Coverage gaps:
Handoff to hunting:
```

Toda classificação precisa de evidência localizável.
