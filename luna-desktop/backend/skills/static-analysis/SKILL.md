---
name: static-analysis
description: Planeja e interpreta análise estática de segurança escolhendo Semgrep, CodeQL e processamento SARIF conforme o problema. Use para SAST, scans de código, taint/dataflow, agregação de resultados e triagem baseada em evidência; não use para criar regra Semgrep customizada.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; scanner execution is never implied and remains behind the supervised execution gate.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits static-analysis bundle"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/static-analysis"
  luna-domain: "offensive-security"
  luna-purpose: "sast-orchestration"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "125"
  luna-triggers: "static analysis, análise estática, analise estatica, sast scan, semgrep scan, codeql scan, taint analysis, dataflow analysis, analisar sarif, parse sarif, scan de código, scan de codigo"
  luna-exclude-triggers: "semgrep rule, regra semgrep, criar regra semgrep"
  luna-host-write: "deny"
  luna-network: "conditional"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "high"
  luna-auto-min-score: "10"
  luna-exclusive-group: "static-analysis"
allowed-tools: Read Grep Glob Bash
---

# Static Analysis — Luna Cyber

## Escolha de ferramenta

Escolha pelo mecanismo, não por preferência:

- **Semgrep**: pattern matching rápido, regras AST, taint relativamente localizado, triagem inicial.
- **CodeQL**: dataflow/taint interprocedural, relações semânticas e codebase grande.
- **SARIF parsing**: já existe resultado de scanner; não rode novo scan só para reformatar.

Se nenhuma ferramenta estiver disponível, faça análise manual e declare a limitação.

## Workflow

1. Fixe target, commit/versão e linguagens.
2. Defina pergunta de segurança: pattern, source→sink, invariant, API misuse.
3. Escolha engine e explique por que.
4. Defina escopo e exclusões explicitamente.
5. Proponha comandos/config somente com paths conhecidos.
6. Preserve output bruto/SARIF quando executado pelo operador/executor.
7. Normalize findings: rule, location, trace/dataflow, severity de origem.
8. **Revalide manualmente** candidatos relevantes; scanner ≠ finding.
9. Deduplicate mantendo provenance.
10. Reporte coverage gaps e zero-findings com cautela.

## Privacidade

Quando Semgrep for usado, prefira operação local e métricas desabilitadas quando suportado. Não assuma que config remota ou registry é aceitável em codebase sensível.

## Zero findings

Zero findings pode significar:
- realmente nenhum match;
- ruleset inadequado;
- target excluído;
- database CodeQL incompleto;
- build/extraction falhou;
- modelagem source/sink insuficiente.

Não converta “0” automaticamente em “seguro”.

## Contrato de saída

```text
STATIC ANALYSIS PLAN/RESULT
Target:
Revision:
Languages:
Security question:
Engine selected:
Scope/exclusions:
Rules/query packs:
Execution status: not_run | executed_by_operator | evidence_provided
Raw artifact:
Candidates:
Validated findings:
Rejected false positives:
Coverage/dataflow gaps:
Next focused analysis:
```
