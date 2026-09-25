---
name: post-patch-validation
description: Valida patches e correções de segurança comparando baseline vulnerável e versão corrigida, verificando PoC original, variantes da root cause, comportamento legítimo, regressões e novos riscos. Substitui o antigo conceito de fix-review.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; validation planning is instruction-only; execution of tests requires the supervised executor/operator.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits post-patch-validation"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/post-patch-validation"
  luna-domain: "offensive-security"
  luna-purpose: "security-fix-validation"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "145"
  luna-triggers: "post-patch, validar patch, validar correção, validar correcao, fix review, confirmar correção, confirmar correcao, patch resolveu, correção resolveu, correcao resolveu, retest fix, revisar remediation, validar remediation"
  luna-requires-any: "patch, fix, correção, correcao, remediation, commit, pr, pull request"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "high"
  luna-auto-min-score: "10"
  luna-exclusive-group: "patch-validation"
allowed-tools: Read Grep Glob Bash
---

# Post-Patch Validation — Luna Cyber

## Regra central

“O PoC parou de funcionar” **não basta** para declarar uma vulnerabilidade corrigida.

## Workflow

1. Pin do **baseline vulnerável** e do **patched**.
2. Reproduza conceitualmente ou com evidência fornecida o finding original.
3. Trace a root cause e identifique sites irmãos/variantes.
4. Defina checks independentes:
   - control: harness benigno funciona;
   - exploit: baseline falha safety assertion e patch bloqueia;
   - variant: pelo menos uma variante relevante;
   - behavior: comportamento legítimo preservado;
   - regression: regressões alvo;
   - security: risco novo/adjacente;
   - suite: testes existentes/sanitizer/fuzz quando cabível.
5. Preserve logs e outputs por revisão.
6. Se execução não foi realizada, diga `NOT RUN`; não simule resultado.
7. Human review continua necessário após checks passarem.

## Evidence levels

- SOURCE: invariantes/diff somente.
- BUILD: compilação/análise do target.
- RUNTIME: comportamento reportado realmente exercitado.

Use o nível mais alto **realmente observado**, nunca o desejado.

## Racionalizações a rejeitar

- “PoC original falhou, então fixed.”
- “Suite completa passou.”
- “É patch upstream/canônico.”
- “Diff é minúsculo.”
- “Não há variante óbvia.”
- “Uma rerun flakey passou.”

## Contrato de saída

```text
POST-PATCH VALIDATION
Finding/root cause:
Vulnerable base:
Patched revision:
Evidence level:
Original exploit check:
Variant checks:
Behavior preservation:
Regression checks:
Adjacent security checks:
Existing suite:
Observed failures:
Validation gaps:
Assessment: supported_fixed | not_fixed | partially_fixed | insufficient_evidence
```
