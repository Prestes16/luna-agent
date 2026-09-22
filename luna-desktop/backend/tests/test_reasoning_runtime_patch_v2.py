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


if __name__ == "__main__":
    unittest.main()
