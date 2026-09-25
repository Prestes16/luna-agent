---
name: token-integration-analyzer
description: Analisa implementação e integração de tokens, com foco em comportamento não padrão, privileges, hooks, fee-on-transfer, rebasing, decimals e assumptions de protocolo. Use ao auditar protocolos que aceitam tokens externos ou implementações ERC20/ERC721 e equivalentes.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; read-only review; on-chain queries require separate operator-authorized tooling.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits building-secure-contracts / token-integration-analyzer"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/building-secure-contracts/skills/token-integration-analyzer"
  luna-domain: "blockchain-security"
  luna-purpose: "token-integration-risk"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "135"
  luna-triggers: "token integration, integração de token, integracao de token, weird token, weird erc20, fee-on-transfer, fee on transfer, rebasing token, erc20 integration, erc721 integration, non-standard token, token não padrão, token nao padrao"
  luna-host-write: "deny"
  luna-network: "conditional"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "medium"
  luna-auto-min-score: "10"
  luna-exclusive-group: "token-security"
allowed-tools: Read Grep Glob
---

# Token Integration Analyzer — Luna Cyber

## Objetivo

Descobrir onde um protocolo assume comportamento “padrão” que um token externo não é obrigado a cumprir.

## Workflow

1. Determine se é **token implementation** ou **token integration**.
2. Mapeie funções de transfer/transferFrom/approve/mint/burn/hooks.
3. Registre decimals/base units e toda conversão.
4. Revise privileges: mint, pause, blacklist, upgrade, fee change.
5. Revise comportamentos não padrão relevantes:
   - missing/no return;
   - fee-on-transfer;
   - rebasing/balance mutation;
   - hooks/reentrancy;
   - pause/blocklist;
   - flash mint;
   - low/high decimals;
   - approval quirks;
   - revert on zero/large amount;
   - upgradeability;
   - unusual permit;
   - metadata adversarial.
6. Para integrações, verifique se o protocolo mede saldo real quando necessário e se assumptions são explicitamente enforced.
7. On-chain claims só podem usar dados realmente fornecidos/consultados; nunca invente holder/supply/config.

## Racionalizações a rejeitar

- “É ERC20, então é padrão.”
- “Usa OpenZeppelin, então integração está protegida.”
- “Sem fee-on-transfer no teste, nunca haverá.”
- “Decimals sempre 18/9.”
- “Slither limpo prova integração segura.”

## Contrato de saída

```text
TOKEN INTEGRATION REVIEW
Context:
Token/protocol:
Standards:
Privileges:
Non-standard behaviors:
External token assumptions:
Decimals/base-unit handling:
Hook/reentrancy surfaces:
Confirmed findings:
Unverified risks:
On-chain evidence:
Coverage gaps:
```
