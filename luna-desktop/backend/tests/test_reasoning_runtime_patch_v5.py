import unittest

# Importing app.luna_engine activates all runtime patches through app.__init__.
from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import validate_model_response
from app.reasoning_runtime_patch_v5 import levenshtein_distance, normalized_similarity
from app.scenario_context import ScenarioContext


class Stage5MathematicalVetoTests(unittest.TestCase):
    def _validate(self, message: str, response: str):
        scenario = ScenarioContext()
        delta = scenario.update(message)
        return validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )

    def test_levenshtein_exact_and_typo(self) -> None:
        self.assertEqual(levenshtein_distance("wifhoodie.com", "wifhoodie.com"), 0)
        self.assertEqual(levenshtein_distance("wifhoodie.com", "wifihoodie.com"), 1)
        self.assertEqual(normalized_similarity("wifhoodie.com", "wifhoodie.com"), 1.0)
        self.assertLess(normalized_similarity("wifhoodie.com", "wifihoodie.com"), 1.0)

    def test_wrong_requested_tool_triggers_hard_veto(self) -> None:
        message = (
            "Estou em CTF autorizado no alvo https://wifhoodie.com. "
            "Me dê um comando nmap em bash para eu executar no Kali."
        )
        response = "```bash\ncurl -I https://wifhoodie.com\n```"
        validation = self._validate(message, response)
        self.assertIn("critical_tool_veto", validation.reasons)

    def test_one_character_target_typo_triggers_hard_veto(self) -> None:
        message = (
            "Estou em CTF autorizado no alvo https://wifhoodie.com. "
            "Me dê um comando nmap em bash para eu executar no Kali."
        )
        response = "```bash\nnmap -sV wifihoodie.com\n```"
        validation = self._validate(message, response)
        self.assertIn("critical_target_veto", validation.reasons)
        self.assertIn("target_similarity_below_threshold", validation.reasons)

    def test_exact_tool_and_target_do_not_trigger_hard_veto(self) -> None:
        message = (
            "Estou em CTF autorizado no alvo https://wifhoodie.com. "
            "Me dê um comando nmap em bash para eu executar no Kali."
        )
        response = "```bash\nnmap -sV wifhoodie.com\n```"
        validation = self._validate(message, response)
        self.assertNotIn("critical_tool_veto", validation.reasons)
        self.assertNotIn("critical_target_veto", validation.reasons)


if __name__ == "__main__":
    unittest.main()
