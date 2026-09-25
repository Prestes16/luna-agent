---
name: variant-analysis
description: Procura outras manifestações de uma root cause já conhecida em uma codebase, generalizando um caso confirmado em padrões de busca, Semgrep ou CodeQL e triando candidatos contra o mecanismo original. Use somente depois que existir um bug/finding/root cause concreto.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; read-only search/triage; execution of scanners remains supervised.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits variant-analysis"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/variant-analysis"
  luna-domain: "offensive-security"
  luna-purpose: "root-cause-variant-hunting"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "135"
  luna-triggers: "variant analysis, análise de variantes, analise de variantes, outras ocorrências, outras ocorrencias, outros iguais, mesmo bug, bugs semelhantes, variantes desse bug, where else, semgrep para esse bug, codeql para esse bug"
  luna-requires-any: "root cause, causa raiz, vulnerabilidade, vulnerability, finding, bug confirmado, bug known, achado confirmado, exploit reproduzido"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
allowed-tools: Read Grep Glob Bash
---

# Variant Analysis — Luna Cyber

## Gate obrigatório

Esta skill exige um **caso conhecido**. Se não houver root cause ou finding concreto no contexto, não faça variant hunting; volte para context building/hunting.

## Workflow

1. **Normalize a root cause**: explique por que o caso original é incorreto, não apenas sua aparência.
2. **Exact match**: construa busca que encontre somente o caso conhecido; se não encontrar, a abstração está errada.
3. **Eixos de generalização**: identificadores, APIs equivalentes, tipos, boundaries, wrappers, caminhos de erro, linguagem/framework.
4. **Generalize uma dimensão por vez**.
5. **Leia todos os matches após cada generalização**.
6. **Pare de generalizar** quando o ruído superar o sinal útil.
7. **Triagem por mecanismo**: candidate só é variante se compartilhar a root cause relevante.
8. **Registre padrões falhos** e false positives; isso faz parte da evidência.
9. **Produza regra de regressão** quando a família estiver suficientemente estável.

## Ferramenta

- Grep/Ripgrep: calibração inicial e casos sintáticos simples.
- Semgrep: AST/padrões e taint local.
- CodeQL: relações semânticas, interprocedural e dataflow.
- Busca manual: validação final do mecanismo.

## Racionalizações a rejeitar

- “Parece igual, então é variante.”
- “A query retornou muito; todos devem ser bugs.”
- “A query não encontrou o original, mas deve estar correta.”
- “Generalizar tudo de uma vez é mais rápido.”
- “Nome de função semelhante implica mesma causa.”

## Contrato de saída

```text
VARIANT HUNT
Original finding:
Root cause:
Exact-match calibration:
Generalization ladder:
Searches attempted:
Candidates:
  - location
  - shared mechanism
  - counter-evidence checked
  - verdict: confirmed_variant | rejected | unresolved
Failed/noisy patterns:
Coverage gaps:
Regression rule proposal:
```
