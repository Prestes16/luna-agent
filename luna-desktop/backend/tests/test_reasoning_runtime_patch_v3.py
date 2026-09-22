import unittest

# Importing app.luna_engine loads app.__init__ and activates all runtime patches.
from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import validate_model_response
from app.scenario_context import ScenarioContext


class NmapCommandFidelityTests(unittest.TestCase):
    def _validate(self, message: str, response: str):
        scenario = ScenarioContext()
        delta = scenario.update(message)
        return validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )

    def test_rejects_url_scheme_as_nmap_target(self) -> None:
        message = (
            "Estou em um CTF autorizado. Preciso de um scan nmap no alvo "
            "https://wifhoodie.com; me dê o comando bash para executar no Kali."
        )
        response = "```bash\nnmap -p- --script=vuln https://wifhoodie.com -oN scan.txt\n```"
        validation = self._validate(message, response)
        self.assertIn("nmap_target_must_be_host_not_url", validation.reasons)

    def test_accepts_observed_hostname_as_nmap_target(self) -> None:
        message = (
            "Estou em um CTF autorizado. Preciso de um scan nmap no alvo "
            "https://wifhoodie.com; me dê o comando bash para executar no Kali."
        )
        response = "```bash\nnmap -p- --script=vuln wifhoodie.com -oN scan.txt\n```"
        validation = self._validate(message, response)
        self.assertNotIn("nmap_target_must_be_host_not_url", validation.reasons)
        self.assertNotIn("nmap_target_does_not_match_observed_host", validation.reasons)
        self.assertNotIn("requested_nmap_command_missing", validation.reasons)

    def test_rejects_wrong_target_host(self) -> None:
        message = (
            "Estou em um CTF autorizado. Preciso de um scan nmap no alvo "
            "https://wifhoodie.com; me dê o comando bash para executar no Kali."
        )
        response = "```bash\nnmap -sV example.com\n```"
        validation = self._validate(message, response)
        self.assertIn("nmap_target_does_not_match_observed_host", validation.reasons)

    def test_rejects_invented_nmap_product_name(self) -> None:
        message = (
            "Estou em um CTF autorizado. Preciso de um scan nmap no alvo "
            "https://wifhoodie.com; me dê o comando bash."
        )
        response = (
            "Use Nsight Plus (NMAP):\n\n"
            "```bash\nnmap -sV wifhoodie.com\n```"
        )
        validation = self._validate(message, response)
        self.assertIn("invented_nmap_product_name", validation.reasons)


if __name__ == "__main__":
    unittest.main()
