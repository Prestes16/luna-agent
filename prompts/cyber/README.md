# Luna Cyber Prompt Kernel v1

Este diretório é a camada de instruções especializada da Luna Cyber. Ele não substitui o harness determinístico, o executor supervisionado, o ScenarioContext, o Evidence Vault, os validators ou os gates quantitativos.

## Princípio de arquitetura

LLM = raciocínio e geração de candidatos.
Harness = verificação, autoridade, execução e evidência.

O runtime deve compilar somente os módulos relevantes ao turno. Não concatenar tudo indiscriminadamente.

Ordem recomendada:

1. core.md — sempre.
2. epistemic.md — sempre.
3. skills.md — apenas o domínio selecionado.
4. tool-contracts.md — somente ferramentas relevantes.
5. output-contracts.md — somente o contrato pedido pelo objetivo.
6. Runtime state factual — ScenarioContext, evidence delta, capability state, target/scope e execution state.

## Não importar

Não importar branding, ferramentas, diretórios, APIs, formatos de tool call ou regras específicas de outros produtos. Não importar proibições genéricas que impeçam pesquisa ofensiva autorizada. Não declarar capacidades sem evidência física/semântica do runtime.

## Invariantes

- Memória não é evidência atual.
- Capability declarada não é capability testada.
- Hipótese não é finding.
- Comando proposto não é comando executado.
- Saída esperada não é resultado observado.
- Uma ação mutável exige pre-state, success predicate, verificação e rollback quando aplicável.
- Execução real permanece fora do loop de ferramentas do modelo.
