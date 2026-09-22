import unittest

from app.command_ast import assess_nmap_strategy, parse_command
from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import validate_model_response
from app.scenario_context import ScenarioContext


class StrategyAwareNmapTests(unittest.TestCase):
    def _validate(self, message: str, response: str):
        scenario = ScenarioContext()
        delta = scenario.update(message)
        return validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )

    def test_command_ast_extracts_nmap_structure(self) -> None:
        ast = parse_command("nmap -sV -T3 wifhoodie.com")
        self.assertIsNotNone(ast)
        self.assertEqual(ast.tool, "nmap")
        self.assertIn("-sV", ast.options)
        self.assertIn("wifhoodie.com", ast.positionals)

    def test_generic_initial_scan_rejects_aggressive_default(self) -> None:
        message = (
            "Estou em um CTF autorizado e preciso executar um scan tipo nmap no alvo "
            "https://wifhoodie.com; me dê o comando bash para executar no Kali."
        )
        response = "```bash\nnmap -A wifhoodie.com\n```"
        validation = self._validate(message, response)
        self.assertFalse(validation.valid)
        self.assertIn("nmap_overbroad_for_initial_recon", validation.reasons)

    def test_generic_initial_scan_accepts_focused_service_detection(self) -> None:
        message = (
            "Estou em um CTF autorizado e preciso executar um scan tipo nmap no alvo "
            "https://wifhoodie.com; me dê o comando bash para executar no Kali."
        )
        response = "```bash\nnmap -sV wifhoodie.com -oN scan_wifhoodie_com.txt\n```"
        validation = self._validate(message, response)
        self.assertNotIn("nmap_overbroad_for_initial_recon", validation.reasons)
        self.assertNotIn("nmap_strategy_utility_below_threshold", validation.reasons)
        self.assertTrue(validation.valid, validation.reasons)

    def test_explicit_aggressive_request_allows_A(self) -> None:
        message = (
            "CTF autorizado: quero um scan nmap agressivo e completo no alvo "
            "https://wifhoodie.com. Me dê um comando bash."
        )
        response = "```bash\nnmap -A wifhoodie.com\n```"
        validation = self._validate(message, response)
        self.assertNotIn("nmap_overbroad_for_initial_recon", validation.reasons)
        self.assertNotIn("nmap_strategy_utility_below_threshold", validation.reasons)

    def test_focused_scan_has_higher_initial_utility_than_aggressive(self) -> None:
        message = "Faça um scan nmap inicial no alvo https://wifhoodie.com."
        focused = assess_nmap_strategy(message, parse_command("nmap -sV wifhoodie.com"))
        aggressive = assess_nmap_strategy(message, parse_command("nmap -A wifhoodie.com"))
        self.assertGreater(focused.utility, aggressive.utility)


if __name__ == "__main__":
    unittest.main()
