import unittest

from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import validate_model_response
from app.scenario_context import ScenarioContext


class LocalPrivacyPreflightValidatorTests(unittest.TestCase):
    def _validate(self, response: str):
        message = (
            "Luna, estou no Kali Linux em um CTF autorizado. Quero preparar Tor e Proxychains. "
            "Não sei se estão instalados, não sei qual arquivo de configuração existe e não "
            "confirmei nenhuma porta SOCKS. Eu executarei tudo manualmente. Me dê somente o "
            "primeiro passo seguro."
        )
        scenario = ScenarioContext()
        delta = scenario.update(message)
        return validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )

    def test_remote_target_is_not_required_before_local_preflight(self) -> None:
        validation = self._validate(
            "Antes de qualquer teste, preciso da base URL/host completo com porta do alvo. "
            "Depois verificamos as ferramentas."
        )
        self.assertFalse(validation.valid)
        self.assertIn(
            "privacy_local_preflight_blocked_by_remote_target_request",
            validation.reasons,
        )

    def test_binary_presence_must_not_be_called_correct_configuration(self) -> None:
        validation = self._validate(
            "Este comando confirma que o Proxychains está configurado corretamente:\n"
            "```bash\nwhich proxychains && proxychains --version\n```"
        )
        self.assertFalse(validation.valid)
        self.assertIn("privacy_binary_check_overclaims_configuration", validation.reasons)

    def test_unknown_proxychains_variant_must_not_be_assumed(self) -> None:
        validation = self._validate(
            "Primeiro verifique o binário:\n```bash\nwhich proxychains\n```"
        )
        self.assertFalse(validation.valid)
        self.assertIn("privacy_proxychains_variant_assumed", validation.reasons)

    def test_correct_local_inventory_passes_v15_specific_guards(self) -> None:
        validation = self._validate(
            "Primeiro faça somente a descoberta local dos binários. Isso prova apenas presença "
            "no PATH; não confirma serviço, configuração ou listener SOCKS.\n"
            "```bash\ncommand -v tor proxychains4 proxychains\n```"
        )
        self.assertNotIn(
            "privacy_local_preflight_blocked_by_remote_target_request",
            validation.reasons,
        )
        self.assertNotIn("privacy_binary_check_overclaims_configuration", validation.reasons)
        self.assertNotIn("privacy_proxychains_variant_assumed", validation.reasons)


if __name__ == "__main__":
    unittest.main()
