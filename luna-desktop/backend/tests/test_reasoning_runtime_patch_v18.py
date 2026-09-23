import unittest

from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import validate_model_response
from app.scenario_context import ScenarioContext


class ExactArithmeticValidatorTests(unittest.TestCase):
    def _validate(self, response: str):
        message = (
            "Auditoria Anchor autorizada. Observei: let fee = amount * 125 / 10_000; "
            "amount é u64 e o ativo tem 6 casas decimais. Não sei se há checked_mul, "
            "u128, wrapping, saturating ou outra proteção."
        )
        scenario = ScenarioContext()
        delta = scenario.update(message)
        return validate_model_response(
            message=message, response=response, scenario=scenario,
            evidence_delta_count=delta.count,
        )

    def test_plain_multiplication_must_not_be_called_implicitly_saturating(self) -> None:
        validation = self._validate(
            "A multiplicação direta com operador * pode saturar automaticamente no u64."
        )
        self.assertFalse(validation.valid)
        self.assertIn(
            "plain_integer_multiplication_saturation_overclaim",
            validation.reasons,
        )

    def test_currency_tolerance_cannot_be_invented_from_decimal_scale(self) -> None:
        validation = self._validate(
            "Um sistema financeiro tolera erro absoluto menor que $0.01."
        )
        self.assertFalse(validation.valid)
        self.assertIn("invented_currency_tolerance", validation.reasons)

    def test_large_rounding_claim_requires_bound(self) -> None:
        validation = self._validate(
            "O truncamento causa uma perda significativa e grande no cálculo."
        )
        self.assertFalse(validation.valid)
        self.assertIn("rounding_loss_not_bounded", validation.reasons)

    def test_incorrect_i128_limit_is_rejected(self) -> None:
        validation = self._validate(
            "O limite de i128 relevante é 9223372036854775807."
        )
        self.assertFalse(validation.valid)
        self.assertIn("wrong_i128_bound", validation.reasons)
    def test_bounded_rounding_statement_is_not_blocked(self) -> None:
        validation = self._validate(
            "O floor descarta remainder/10000; a perda é <1 base unit por cálculo."
        )
        self.assertNotIn("rounding_loss_not_bounded", validation.reasons)


if __name__ == "__main__":
    unittest.main()
