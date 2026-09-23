import unittest

from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import validate_model_response
from app.scenario_context import ScenarioContext


class CommandLifecycleValidatorTests(unittest.TestCase):
    def _validate(self, message: str, response: str):
        scenario = ScenarioContext()
        delta = scenario.update(message)
        return validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )

    def test_unverified_state_change_chain_is_rejected(self) -> None:
        validation = self._validate(
            "Quero configurar Tor no Kali de forma supervisionada.",
            "```bash\nsudo systemctl start tor && proxychains4 curl https://example.test\n```",
        )
        self.assertFalse(validation.valid)
        self.assertIn("unverified_state_change_chain", validation.reasons)

    def test_unsolicited_destructive_action_is_rejected(self) -> None:
        validation = self._validate(
            "Quero diagnosticar um arquivo temporário no meu ambiente local.",
            "```bash\nsudo rm -rf /tmp/luna-test\n```",
        )
        self.assertFalse(validation.valid)
        self.assertIn("destructive_action_not_explicit", validation.reasons)

    def test_explicit_destructive_intent_is_not_blocked_by_v12_reason(self) -> None:
        validation = self._validate(
            "Quero remover explicitamente /tmp/luna-test do meu ambiente local.",
            "```bash\nrm -rf /tmp/luna-test\n```",
        )
        self.assertNotIn("destructive_action_not_explicit", validation.reasons)


if __name__ == "__main__":
    unittest.main()
