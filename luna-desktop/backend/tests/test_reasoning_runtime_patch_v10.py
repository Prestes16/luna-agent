import unittest

from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import validate_model_response
from app.scenario_context import ScenarioContext


class PrerequisiteAwareToolTests(unittest.TestCase):
    def _scenario(self) -> ScenarioContext:
        scenario = ScenarioContext()
        scenario.update("CTF autorizado no alvo https://wifhoodie.com.")
        return scenario

    def test_missing_auth_inputs_can_be_requested_without_system_error(self) -> None:
        scenario = self._scenario()
        message = "Agora use Hydra e me dê o comando no Kali."
        delta = scenario.update(message)
        response = (
            "Antes do comando, preciso do serviço ou módulo autenticado, da fonte de usuário "
            "ou userlist e da senha ou wordlist observadas. Se for formulário web, envie "
            "também o endpoint, os campos e a mensagem de falha."
        )
        validation = validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )
        self.assertTrue(validation.valid, validation.reasons)

    def test_unobserved_path_stays_blocked_during_prerequisite_request(self) -> None:
        scenario = self._scenario()
        message = "Agora use Hydra e me dê o comando no Kali."
        delta = scenario.update(message)
        response = (
            "Preciso do serviço, usuário/userlist e senha/wordlist. Para formulário web, "
            "use /login e envie também os campos e a mensagem de falha."
        )
        validation = validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )
        self.assertFalse(validation.valid)
        self.assertIn("unobserved_endpoint_mentioned", validation.reasons)


if __name__ == "__main__":
    unittest.main()
