---
name: supply-chain-risk-auditor
description: Audita dependências e lockfiles para risco de supply chain: advisories por versão, upstream abandonado, publisher/maintainer concentration, install scripts e cobertura da análise. Use quando o pedido for risco de dependências, terceiros ou cadeia de suprimentos.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; local manifests/lockfiles can be read; network enrichment requires separate authorized tooling.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits supply-chain-risk-auditor"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/supply-chain-risk-auditor"
  luna-domain: "supply-chain-security"
  luna-purpose: "dependency-risk-audit"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "135"
  luna-triggers: "supply chain, cadeia de suprimentos, audit dependencies, auditar dependências, auditar dependencias, dependency risk, risco de dependências, risco de dependencias, lockfile risk, install scripts, abandoned dependency, publisher risk"
  luna-host-write: "deny"
  luna-network: "conditional"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "high"
  luna-auto-min-score: "10"
  luna-exclusive-group: "dependency-risk"
allowed-tools: Read Grep Glob
---

# Supply Chain Risk Auditor — Luna Cyber

## Workflow
1. Detecte ecossistema e lockfiles/manifests.
2. Separe versão declarada de versão realmente resolvida.
3. Catalogue dependências diretas e árvore quando disponível.
4. Avalie advisories apenas contra versões corretas.
5. Revise install/postinstall/build hooks e código executado na instalação.
6. Registre sinais de upstream abandonado/arquivado e riscos de concentração quando houver dados.
7. Declare critérios não avaliáveis; ausência de finding não é clean bill of health.
8. Preserve provenance de cada dado externo.

## Output
```text
SUPPLY CHAIN REVIEW
Ecosystems:
Manifests/lockfiles:
Resolved versions:
Advisory evidence:
Install-time execution:
Upstream maintenance signals:
Publisher/maintainer risk:
Unassessable criteria:
Findings:
Coverage limits:
```
