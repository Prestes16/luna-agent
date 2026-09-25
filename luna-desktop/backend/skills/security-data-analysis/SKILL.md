---
name: security-data-analysis
description: Analisa dados de cybersecurity — logs, eventos, findings, scan results, timelines e tabelas — preservando provenance, grain, timestamps, missingness, deduplicação e distinção entre correlação e mecanismo. Use para investigação quantitativa e triagem baseada em dados de segurança.
license: MIT
compatibility: Luna Cyber local runtime; analytical/read-only skill; no host or network action is implied.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0"
  luna-domain: "security-data-analysis"
  luna-purpose: "cyber-evidence-analytics"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "135"
  luna-triggers: "analisar logs de segurança, analisar logs de seguranca, security logs, dados de segurança, dados de seguranca, scan results, resultados de scan, findings csv, vulnerabilidades csv, event correlation, correlação de eventos, correlacao de eventos, timeline de incidente, telemetry security, telemetria de segurança, telemetria de seguranca, sarif aggregate"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "medium"
  luna-auto-min-score: "10"
  luna-exclusive-group: "security-data"
allowed-tools: Read Grep Glob
---

# Security Data Analysis — Luna Cyber

## Objetivo

Transformar dados brutos de segurança em evidência quantitativa auditável, sem confundir padrão estatístico com vulnerabilidade confirmada.

## Data-quality gate

Antes de métricas/conclusões determine:
- fonte/provenance;
- grain: o que uma linha/evento representa;
- timezone e clock semantics;
- janela temporal;
- schema/tipos;
- missingness;
- duplicatas;
- chaves de join;
- sampling/truncation;
- alterações de versão/coleta.

Se esses pontos impedirem uma conclusão, declare `dados insuficientes para verificar`.

## Workflow

1. Defina pergunta e unidade de análise.
2. Preserve dataset original; normalize em transformação separada.
3. Faça sanity checks: contagens, ranges, nulidade, cardinalidade e duplicatas.
4. Normalize tempo e IDs sem perder valor original.
5. Deduplicate com regra explícita; não simplesmente `drop_duplicates` sem chave semântica.
6. Segmente por dimensão relevante: host, service, rule, severity original, tool, commit, endpoint.
7. Correlacione eventos mantendo tolerância temporal e causalidade separadas.
8. Calcule métricas exatamente quando possível; para amostras, declare denominador e cobertura.
9. Valide outliers no dado bruto antes de interpretá-los.
10. Findings de scanner permanecem candidates até validação de mecanismo.

## Cyber-specific anti-patterns

- somar severidades de scanners diferentes como se fossem escala comum;
- contar duplicates como vulnerabilidades independentes;
- inferir ataque apenas por proximidade temporal;
- comparar períodos com coleta diferente;
- misturar timestamps UTC/local;
- usar média quando distribuição é heavy-tail sem mostrar mediana/percentis;
- concluir “mais seguro” por menos alerts sem verificar cobertura do scanner.

## Contrato de saída

```text
SECURITY DATA ANALYSIS
Question:
Sources/provenance:
Grain:
Time window/timezone:
Quality checks:
Transformations:
Metrics:
Segments:
Correlations:
Outliers:
Candidates requiring mechanism validation:
Limitations:
Evidence-backed conclusions:
```
