import unittest

from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import validate_model_response
from app.scenario_context import ScenarioContext


class QuantitativeIntegrityValidatorTests(unittest.TestCase):
    def _validate(self, message: str, response: str):
        scenario = ScenarioContext()
        delta = scenario.update(message)
        return validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )

    def test_confirmed_overflow_without_numeric_domain_is_rejected(self) -> None:
        validation = self._validate(
            "CTF autorizado: estou auditando overflow em uma rotina numérica.",
            "Overflow confirmado e explorável.",
        )
        self.assertFalse(validation.valid)
        self.assertIn(
            "quantitative_strong_claim_without_numeric_mechanism",
            validation.reasons,
        )

    def test_overflow_hypothesis_is_allowed_until_bounds_are_known(self) -> None:
        validation = self._validate(
            "CTF autorizado: estou auditando overflow em uma rotina numérica.",
            "Hipótese de overflow; ainda não confirma porque faltam bit width, signedness e limites.",
        )
        self.assertNotIn(
            "quantitative_strong_claim_without_numeric_mechanism",
            validation.reasons,
        )

    def test_confirmed_overflow_with_representation_and_boundary_is_not_blocked(self) -> None:
        validation = self._validate(
            "CTF autorizado. O valor observado usa u64 e a operação relevante é checked_add.",
            "Overflow confirmado no domínio u64: o limite MAX é excedido e checked_add retorna "
            "falha no boundary reproduzido; o invariante é que o intermediário permaneça representável.",
        )
        self.assertNotIn(
            "quantitative_strong_claim_without_numeric_mechanism",
            validation.reasons,
        )

    def test_timing_side_channel_without_measurement_is_rejected(self) -> None:
        validation = self._validate(
            "Laboratório autorizado: analise possível timing side-channel.",
            "Timing side-channel confirmado e explorável.",
        )
        self.assertFalse(validation.valid)
        self.assertIn("physics_strong_claim_without_measurement", validation.reasons)

    def test_timing_claim_with_sampling_noise_and_units_is_not_blocked(self) -> None:
        validation = self._validate(
            "Laboratório autorizado: analise possível timing side-channel.",
            "Timing side-channel confirmado após 500 amostras: mediana difere 18 us, acima do "
            "ruído medido de 2 us e da resolução do relógio; o efeito foi reproduzido.",
        )
        self.assertNotIn("physics_strong_claim_without_measurement", validation.reasons)


if __name__ == "__main__":
    unittest.main()
