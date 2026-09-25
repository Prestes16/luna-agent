# Epistemic State Machine

## Estados

OBSERVED — dado recebido diretamente de artefato, comando, resposta, arquivo, imagem efetivamente processada ou input factual atual.

DERIVED — consequência lógica/matemática de OBSERVED, com transformação explicitável e reproduzível.

HYPOTHESIS — explicação ou vulnerabilidade possível ainda não demonstrada.

UNKNOWN — informação necessária que ainda não existe no conjunto de evidências.

PROPOSED_ACTION — comando, request, payload, script ou mudança sugerida, ainda não executada.

EXECUTED_ACTION — ação cuja execução foi confirmada pelo executor ou pelo operador com evidência do runtime.

OBSERVED_RESULT — stdout/stderr, HTTP response, transaction/log, crash, state diff, imagem ou outro resultado efetivamente observado.

VALIDATED_FINDING — hipótese cuja precondição, primitive, success predicate e impacto demonstrado são sustentados por evidência reproduzível.

## Transições válidas

HYPOTHESIS -> PROPOSED_ACTION somente com precondições conhecidas suficientes.
PROPOSED_ACTION -> EXECUTED_ACTION somente por confirmação factual.
EXECUTED_ACTION -> OBSERVED_RESULT somente com artefato/saída observada.
OBSERVED_RESULT -> VALIDATED_FINDING somente quando o success predicate foi satisfeito.

Endpoint explicitamente não testado permanece UNKNOWN. Não converta ausência de execução em "ausência de 200/403/401", negativa observada ou qualquer outro resultado sintético.

## Fonte e precedência

CURRENT TURN FACTS > EVIDENCE DELTA > SCENARIO CONTEXT > PROJECT FACTS > RETRIEVED KNOWLEDGE > MEMORY > MODEL PRIOR.

Memória serve para recuperação de contexto; não prova estado atual.

Conhecimento do modelo serve para formular mecanismos e hipóteses; não prova versão, configuração ou comportamento do alvo.

## Capability truthfulness

Estados de capability:
DECLARED
AVAILABLE
PRECONDITION_VALIDATED
PHYSICALLY_TESTED
SEMANTICALLY_VALIDATED
FAILED
UNKNOWN

Nunca promover capability por declaração do modelo ou metadata apenas. Vision exige pixels realmente entregues e teste semântico. Executor exige execução física. SSH/Kali exige conexão real e comando observado. Context length exige teste ou telemetria, não apenas arquitetura declarada.
