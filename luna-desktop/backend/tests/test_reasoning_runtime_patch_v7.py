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
        ast = parse_command("nmap -sS -sV -T3 wifhoodie.com")
        self.assertIsNotNone(ast)
        self.assertEqual(ast.tool, "nmap")
        self.assertIn("-sS", ast.options)
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

    def test_strategy_layer_flags_implicit_scan_mode(self) -> None:
        message = (
            "Estou em um CTF autorizado e preciso executar um scan tipo nmap no alvo "
            "https://wifhoodie.com; me dê o comando bash para executar no Kali."
        )
        assessment = assess_nmap_strategy(
            message,
            parse_command("nmap -sV wifhoodie.com"),
        )
        self.assertIn("nmap_initial_scan_mode_implicit", assessment.reasons)

    def test_generic_initial_scan_accepts_explicit_syn_strategy(self) -> None:
        message = (
            "Estou em um CTF autorizado e preciso executar um scan tipo nmap no alvo "
            "https://wifhoodie.com; me dê o comando bash para executar no Kali."
        )
        response = "```bash\nsudo nmap -sS -sV wifhoodie.com\n```"
        validation = self._validate(message, response)
        self.assertNotIn("nmap_overbroad_for_initial_recon", validation.reasons)
        self.assertNotIn("nmap_initial_scan_mode_implicit", validation.reasons)
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

    def test_web_optimization_rejects_global_top_ports_heuristic(self) -> None:
        scenario = ScenarioContext()
        scenario.update("CTF autorizado no alvo https://wifhoodie.com.")
        message = "Otimize esse scan Nmap para as portas de maior valor no contexto web."
        delta = scenario.update(message)
        validation = validate_model_response(
            message=message,
            response="```bash\nsudo nmap -sS --top-ports 50 wifhoodie.com\n```",
            scenario=scenario,
            evidence_delta_count=delta.count,
        )
        self.assertFalse(validation.valid)
        self.assertIn("nmap_top_ports_generic_for_web_context", validation.reasons)

    def test_web_optimization_accepts_contextual_explicit_port_vector(self) -> None:
        scenario = ScenarioContext()
        scenario.update("CTF autorizado no alvo https://wifhoodie.com.")
        message = "Otimize esse scan Nmap para as portas de maior valor no contexto web."
        delta = scenario.update(message)
        response = (
            "```bash\n"
            "sudo nmap -sS -p 80,443,8000,8080,8443,9090,10000,3306,5432,1433,27017,6379,11211 "
            "wifhoodie.com\n```"
        )
        validation = validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )
        self.assertNotIn("nmap_top_ports_generic_for_web_context", validation.reasons)
        self.assertNotIn("nmap_web_port_profile_low_coverage", validation.reasons)
        self.assertTrue(validation.valid, validation.reasons)
    def test_explicit_syn_scan_has_higher_initial_utility_than_implicit(self) -> None:
        message = "Faça um scan nmap inicial no alvo https://wifhoodie.com."
        explicit = assess_nmap_strategy(message, parse_command("nmap -sS -sV wifhoodie.com"))
        implicit = assess_nmap_strategy(message, parse_command("nmap -sV wifhoodie.com"))
        self.assertGreater(explicit.utility, implicit.utility)


if __name__ == "__main__":
    unittest.main()
