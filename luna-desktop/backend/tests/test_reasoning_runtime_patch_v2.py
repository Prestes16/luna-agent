import unittest

# Importing app.luna_engine loads app.__init__ and activates the runtime patches.
from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import validate_model_response
from app.scenario_context import ScenarioContext


class UrlAwareValidatorTests(unittest.TestCase):
    def test_url_authority_is_not_misread_as_unobserved_endpoint(self) -> None:
        scenario = ScenarioContext()
        message = "Observei o endpoint /api/admin/users, ainda não testado."
        scenario.update(message)

        validation = validate_model_response(
            message=message,
            response=(
                "O endpoint pendente continua sendo /api/admin/users. "
                "Uma URL completa tem formato http://127.0.0.1:8080/api/admin/users, "
                "mas o host precisa vir do operador."
            ),
            scenario=scenario,
            evidence_delta_count=1,
        )

        self.assertNotIn("unobserved_endpoint_mentioned", validation.reasons)

    def test_real_unobserved_route_in_prose_remains_blocked(self) -> None:
        scenario = ScenarioContext()
        message = "Observei o endpoint /api/admin/users, ainda não testado."
        scenario.update(message)

        validation = validate_model_response(
            message=message,
            response="Teste também /api/private.",
            scenario=scenario,
            evidence_delta_count=1,
        )

        self.assertIn("unobserved_endpoint_mentioned", validation.reasons)

    def test_status_cannot_be_promoted_to_fact_for_untested_endpoint(self) -> None:
        scenario = ScenarioContext()
        message = (
            "GET /api/me retornou HTTP/1.1 401 Unauthorized.\n"
            "Também observei /api/admin/users. Esse endpoint ainda NÃO foi testado.\n"
            "Separe fatos, inferências e hipóteses."
        )
        delta = scenario.update(message)
        response = """FATOS:
- 401 em /api/admin/users (implícito).

INFERÊNCIAS:
- O frontend sugere uma área administrativa.

HIPÓTESES:
- O backend pode aplicar autorização por role.
"""
        validation = validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )
        self.assertFalse(validation.valid)
        self.assertIn("status_claim_for_untested_endpoint", validation.reasons)

    def test_hypothesis_for_untested_endpoint_must_remain_conditional(self) -> None:
        scenario = ScenarioContext()
        message = (
            "Observei /api/admin/users. Esse endpoint ainda NÃO foi testado.\n"
            "Separe fatos, inferências e hipóteses."
        )
        delta = scenario.update(message)
        response = """FATOS:
- /api/admin/users foi observado e ainda não foi testado.

INFERÊNCIAS:
- Ainda não há evidência da autorização server-side.

HIPÓTESES:
- /api/admin/users será 403 Forbidden.
"""
        validation = validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )
        self.assertFalse(validation.valid)
        self.assertIn("definitive_outcome_for_untested_endpoint", validation.reasons)

    def test_conditional_hypothesis_is_allowed(self) -> None:
        scenario = ScenarioContext()
        message = (
            "Observei /api/admin/users. Esse endpoint ainda NÃO foi testado.\n"
            "Separe fatos, inferências e hipóteses."
        )
        delta = scenario.update(message)
        response = """FATOS:
- /api/admin/users foi observado e ainda não foi testado.

INFERÊNCIAS:
- O check visual não prova autorização server-side.

HIPÓTESES:
- Se o backend aplicar autorização por role, um 403 seria compatível; também pode haver outro comportamento.
"""
        validation = validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )
        self.assertTrue(validation.valid, validation.reasons)

    def test_unobserved_negative_client_behavior_is_rejected(self) -> None:
        scenario = ScenarioContext()
        message = (
            "No frontend observei if (user.role === 'admin') showAdminPanel().\n"
            "Também observei /api/admin/users; ainda não foi testado."
        )
        delta = scenario.update(message)
        response = (
            "O frontend não realiza chamadas API ainda. "
            "/api/admin/users permanece não testado."
        )
        validation = validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )
        self.assertFalse(validation.valid)
        self.assertIn("unsupported_client_behavior_claim", validation.reasons)


if __name__ == "__main__":
    unittest.main()
