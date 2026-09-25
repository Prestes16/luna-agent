import unittest

from app.reasoning_pipeline import validate_model_response
from app.scenario_context import ScenarioContext


BASE_MESSAGE = """CTF local autorizado.
Target observado: http://127.0.0.1:8080
GET /api/audit/export ainda NÃO foi testado.
Forneça EXATAMENTE UM comando curl para GET /api/audit/export.
Classifique a ação como L0, L1, L2 ou L3.
Identifique como PROPOSED_ACTION e deixe explícito que NÃO é EXECUTED_ACTION.
"""


def _scenario() -> tuple[ScenarioContext, int]:
    scenario = ScenarioContext()
    delta = scenario.update(BASE_MESSAGE)
    return scenario, delta.count


GOOD_RESPONSE = """FACTS
/api/audit/export foi observado e ainda não foi testado.

HYPOTHESIS
O resultado do request permanece desconhecido até o teste.

NEXT TEST
curl -i http://127.0.0.1:8080/api/audit/export
CLASSIFICAÇÃO: L1
TIPO: PROPOSED_ACTION
EXECUTED_ACTION: NÃO
"""


class Stage19ExecutionSemanticsTests(unittest.TestCase):
    def test_remote_curl_must_not_be_labeled_l0(self) -> None:
        scenario, count = _scenario()
        response = GOOD_RESPONSE.replace("CLASSIFICAÇÃO: L1", "CLASSIFICAÇÃO: L0")
        result = validate_model_response(
            message=BASE_MESSAGE,
            response=response,
            scenario=scenario,
            evidence_delta_count=count,
        )
        self.assertFalse(result.valid)
        self.assertIn("authority_level_mismatch", result.reasons)

    def test_correct_l1_proposed_action_contract_passes_stage19(self) -> None:
        scenario, count = _scenario()
        result = validate_model_response(
            message=BASE_MESSAGE,
            response=GOOD_RESPONSE,
            scenario=scenario,
            evidence_delta_count=count,
        )
        self.assertNotIn("authority_level_mismatch", result.reasons)
        self.assertNotIn("execution_state_not_explicit", result.reasons)
        self.assertNotIn("untested_endpoint_negative_evidence_claim", result.reasons)
        self.assertNotIn("hypothesis_leaked_into_facts", result.reasons)

    def test_untested_endpoint_cannot_have_synthetic_absence_of_200(self) -> None:
        scenario, count = _scenario()
        response = GOOD_RESPONSE.replace(
            "O resultado do request permanece desconhecido até o teste.",
            "A ausência de resposta 200 em /api/audit/export pode indicar falta de autorização.",
        )
        result = validate_model_response(
            message=BASE_MESSAGE,
            response=response,
            scenario=scenario,
            evidence_delta_count=count,
        )
        self.assertFalse(result.valid)
        self.assertIn("untested_endpoint_negative_evidence_claim", result.reasons)

    def test_hypothesis_text_must_not_leak_into_facts(self) -> None:
        scenario, count = _scenario()
        response = GOOD_RESPONSE.replace(
            "/api/audit/export foi observado e ainda não foi testado.",
            "/api/audit/export não foi testado, mantendo a hipótese de falta de permissão.",
        )
        result = validate_model_response(
            message=BASE_MESSAGE,
            response=response,
            scenario=scenario,
            evidence_delta_count=count,
        )
        self.assertFalse(result.valid)
        self.assertIn("hypothesis_leaked_into_facts", result.reasons)

    def test_execution_state_must_be_explicit_when_operator_requires_it(self) -> None:
        scenario, count = _scenario()
        response = GOOD_RESPONSE.replace("EXECUTED_ACTION: NÃO\n", "")
        result = validate_model_response(
            message=BASE_MESSAGE,
            response=response,
            scenario=scenario,
            evidence_delta_count=count,
        )
        self.assertFalse(result.valid)
        self.assertIn("execution_state_not_explicit", result.reasons)


if __name__ == "__main__":
    unittest.main()
