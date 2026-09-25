---
name: insecure-defaults
description: Audita defaults inseguros e caminhos fail-open — fallback secrets, credenciais padrão, crypto fraca, permissões permissivas, CORS/debug e flags que desabilitam proteção — rastreando cada candidato até um sink de segurança antes de reportar.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; read-only configuration/code audit.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits insecure-defaults"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/insecure-defaults"
  luna-domain: "offensive-security"
  luna-purpose: "fail-open-default-audit"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "140"
  luna-triggers: "insecure defaults, default credentials, credenciais padrão, credenciais padrao, fallback secret, segredo fallback, fail-open, fail open, weak crypto default, cors permissivo, cors *, debug leakage, default password, senha padrão, senha padrao"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "medium"
  luna-auto-min-score: "10"
  luna-exclusive-group: "config-security"
allowed-tools: Read Grep Glob
---

# Insecure Defaults — Luna Cyber

## Categorias

1. fallback secret/key/token;
2. default credentials;
3. fail-open security switches;
4. crypto/hash inadequado em decisão de segurança;
5. permissive access/permissions/CORS;
6. debug/error leakage;
7. configuração de produção que depende de override não garantido.

## Regra de verificação

Descoberta por grep produz **candidate**, não finding.

Para cada candidate tente refutá-lo:

1. O código/config é alcançável em produção ou no escopo pedido?
2. O default realmente é usado quando a configuração falta?
3. O valor é materialmente inseguro?
4. Ele chega a uma decisão/sink de segurança?
5. Deployment/configuração sempre o substitui? Há evidência completa disso?

Se a cadeia ficar incompleta, reporte como lacuna/candidate não confirmado.

Distinga:
- **configurable default**: pode ser substituído;
- **unconditional insecure value**: inseguro independentemente de env override.

## Racionalizações a rejeitar

- “É só dev default.” → prove que produção não o alcança.
- “Existe env var.” → prove que ausência falha closed ou que deployment sempre define.
- “É em tests.” → se tests são o scope pedido, analise; fora disso classifique reachability.
- “String parece secret.” → trace uso.
- “CORS * é sempre vuln.” → contexto de credenciais/origin importa.

## Contrato de saída

```text
INSECURE DEFAULTS AUDIT
Scope:
Config/deploy model:
Candidates:
  - category
  - location
  - default/value
  - reachability
  - security sink
  - deployment override evidence
  - verdict: confirmed | refuted | unresolved
Findings:
Coverage gaps:
```
