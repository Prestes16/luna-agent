import unittest

from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import validate_model_response
from app.scenario_context import ScenarioContext


class ConstructionGroundingValidatorTests(unittest.TestCase):
    def _validate(self, message: str, response: str):
        scenario = ScenarioContext()
        delta = scenario.update(message)
        return validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )

    def test_confirmed_rce_without_mechanism_is_rejected(self) -> None:
        validation = self._validate(
            "CTF autorizado: estou auditando uma API e apareceu comportamento estranho.",
            "RCE confirmado. O exploit funciona.",
        )
        self.assertFalse(validation.valid)
        self.assertIn("construction_strong_claim_without_mechanism", validation.reasons)

    def test_hypothesis_language_is_not_promoted_to_confirmed_fact(self) -> None:
        validation = self._validate(
            "CTF autorizado: estou auditando uma API e apareceu comportamento estranho.",
            "Hipótese de RCE; a evidência atual ainda não confirma o mecanismo. "
            "Precisamos identificar o fluxo e o ponto de validação antes de concluir.",
        )
        self.assertNotIn("construction_strong_claim_without_mechanism", validation.reasons)

    def test_confirmed_claim_with_causal_mechanism_is_not_blocked_by_v16(self) -> None:
        validation = self._validate(
            "CTF autorizado. Código observado concatena input do parâmetro id em uma query SQL.",
            "SQL injection confirmada pelo mecanismo observado: o input atravessa o fluxo sem "
            "parametrização no ponto de validação, violando o invariante de separação entre "
            "dados e estrutura da consulta.",
        )
        self.assertNotIn("construction_strong_claim_without_mechanism", validation.reasons)

    def test_non_security_greeting_is_ignored(self) -> None:
        validation = self._validate(
            "Olá Luna, bom dia.",
            "Bom dia! Como posso ajudar?",
        )
        self.assertNotIn("construction_strong_claim_without_mechanism", validation.reasons)


if __name__ == "__main__":
    unittest.main()
