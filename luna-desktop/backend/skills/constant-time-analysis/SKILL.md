---
name: constant-time-analysis
description: Analisa risco de timing side-channel em código criptográfico, rastreando segredo até branch, comparação, divisão/mod, lookup ou encoding potencialmente variável e exigindo evidência no código/assembly quando disponível. Use para constant-time, timing attack e secret-dependent operations.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; static/review methodology; compilation or analyzer execution remains supervised.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits constant-time-analysis"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/constant-time-analysis"
  luna-domain: "crypto-security"
  luna-purpose: "timing-side-channel-review"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "145"
  luna-triggers: "constant-time, constant time, timing side-channel, timing side channel, timing attack, ataque de timing, canal lateral de tempo, secret-dependent branch, branch dependente de segredo, kyberslash"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
allowed-tools: Read Grep Glob Bash
---

# Constant-Time Analysis — Luna Cyber

## Escopo

Avalie se operações cujo tempo pode variar dependem de informação secreta. Esta skill é **análise estática/compilada**; medição estatística de timing é outra técnica.

## Workflow

1. Identifique funções crypto e marque fontes secretas: key, nonce secreto, plaintext sensível, tag, intermediate secret.
2. Trace secret-dependence até:
   - branch/early return;
   - `/` ou `%`;
   - comparação early-exit;
   - table lookup/index;
   - allocation/encoding/comprimento;
   - chamadas de biblioteca com timing desconhecido.
3. Diferencie input público de segredo.
4. Em código compilado, compare output de compiler/assembly na configuração real de build.
5. Considere arquitetura e nível de otimização quando materialmente relevantes.
6. Verifique mitigação no artefato compilado, não apenas no source.
7. Declare limites: cache/microarquitetura e ruído runtime não são provados por esta análise.

## Evidência mínima

Finding exige:
- origem do segredo;
- data/control flow;
- operação potencialmente variável;
- configuração/artefato observado;
- razão pela qual variação pode correlacionar com segredo.

## Racionalizações a rejeitar

- “Não existe if no source, então é constant-time.”
- “Compiler sempre gera cmov.”
- “Comparação de tag da stdlib deve ser segura.”
- “Uma arquitetura limpa prova todas.”
- “Input criptográfico é automaticamente secreto.”

## Contrato de saída

```text
CONSTANT-TIME REVIEW
Target/config:
Secret sources:
Secret-dependent flows:
Variable-time operations:
Compiler/architecture evidence:
Library guarantees checked:
Findings:
Unresolved assumptions:
Limitations:
Retest requirements:
```
