import unittest

from app.luna_engine import LunaEngine  # noqa: F401
from app.operational_transform import transform_response_commands
from app.reasoning_pipeline import validate_model_response
from app.scenario_context import ScenarioContext


PROMPT = (
    "Luna, estou em um CTF autorizado e preciso executar um scan tipo nmap no alvo "
    "https://wifhoodie.com. Me dê o comando bash para eu executar no meu Kali Linux."
)


class DeterministicNmapRepairTests(unittest.TestCase):
    def _validate(self, response: str):
        scenario = ScenarioContext()
        delta = scenario.update(PROMPT)
        return validate_model_response(
            message=PROMPT,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )

    def test_final_pipeline_repairs_implicit_initial_scan_mode(self) -> None:
        response = "```bash\nnmap -sV wifhoodie.com\n```"

        validation = self._validate(response)
        self.assertTrue(validation.valid, validation.reasons)

        transformed, mutations = transform_response_commands(PROMPT, response)
        self.assertEqual(len(mutations), 1)
        self.assertTrue(mutations[0].scan_mode_added)
        self.assertTrue(mutations[0].sudo_added)
        self.assertIn("sudo nmap -sS -sV wifhoodie.com", transformed)
        self.assertNotIn("https://wifhoodie.com", transformed)

    def test_wrong_target_is_still_never_repaired(self) -> None:
        response = "```bash\nnmap -sV example.com\n```"

        validation = self._validate(response)
        self.assertFalse(validation.valid)

        transformed, mutations = transform_response_commands(PROMPT, response)
        self.assertEqual(mutations, [])
        self.assertIn("example.com", transformed)
        self.assertNotIn("wifhoodie.com", transformed)


if __name__ == "__main__":
    unittest.main()
