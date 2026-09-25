---
name: property-based-testing
description: Projeta e revisa property-based tests para invariantes, roundtrips, oracles e domínios inteiros de input usando Hypothesis, fast-check, proptest, Echidna/Medusa e equivalentes. Use quando exemplos manuais não cobrem suficientemente o espaço de estados.
license: CC-BY-SA-4.0
compatibility: Luna Cyber local runtime; test design is procedural; dependency installation or test execution remains supervised.
metadata:
  author: "Shield-Corp / Cleiton Prestes + Luna AI"
  version: "1.0.0-luna"
  source: "Trail of Bits property-based-testing"
  source-url: "https://github.com/trailofbits/skills/tree/main/plugins/property-based-testing"
  luna-domain: "security-testing"
  luna-purpose: "invariant-testing"
  luna-risk: "read-only"
  luna-auto-activate: "true"
  luna-priority: "130"
  luna-triggers: "property-based, property based, teste de propriedade, testes de propriedade, hypothesis, fast-check, proptest, echidna, medusa, invariant test, teste de invariantes, fuzz de invariantes"
  luna-host-write: "deny"
  luna-network: "deny"
  luna-execution: "instruction-only"
  luna-evidence: "required"
  luna-admission: "on-demand"
  luna-context-cost: "medium"
  luna-auto-min-score: "10"
  luna-exclusive-group: "test-design"
allowed-tools: Read Grep Glob
---

# Property-Based Testing — Luna Cyber

## Princípio

Um example test cobre pontos escolhidos. Um property test tenta quebrar uma regra sobre um domínio.

Escolha a **propriedade mais forte** sustentada pelo código:
`no crash < type preservation < invariant < idempotence < roundtrip/oracle`.

## Catálogo útil

- Roundtrip: `decode(encode(x)) == x`.
- Inverse: `f(g(x)) == x`.
- Oracle: implementação nova == referência independente.
- Idempotence: `f(f(x)) == f(x)`.
- State invariant: preservado antes/depois.
- Metamorphic relation: transformação previsível sem recomputar a implementação.
- Conservation: valor/quantidade total respeita a regra do protocolo.

## Workflow

1. Identifique a propriedade de segurança/semântica.
2. Defina domínio, tipos, unidades, bounds e estados inválidos.
3. Construa geradores que produzam inputs úteis sem depender de `assume` excessivo.
4. Separe precondition legítima de filtragem que torna o teste vacuamente verdadeiro.
5. Defina oracle independente quando houver.
6. Inclua edge cases numéricos, serialização e transitions.
7. Para contratos, modele sequências de ações e invariantes de estado/economia.
8. Quando houver failure/shrink, determine se é:
   - bug real;
   - propriedade errada;
   - generator inválido;
   - fixture/harness defeituoso.

## Anti-padrões

- Tautologia: teste repete a mesma implementação.
- Vacuity: filtros eliminam quase todos os casos.
- “Não crashou” como única propriedade quando existe invariant melhor.
- Float onde o domínio real usa base units/inteiros.
- Oracle derivado do mesmo código que está sendo testado.

## Contrato de saída

```text
PROPERTY TEST DESIGN
Target:
Property:
Why it constrains the implementation:
Input/state domain:
Generator strategy:
Preconditions:
Oracle/metamorphic relation:
Edge cases:
Shrink interpretation:
Test skeleton:
Failure classification rules:
Coverage gaps:
```
