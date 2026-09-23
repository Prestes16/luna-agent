import unittest

from app.kali_capability_router import capability_guidance, rank_capabilities
from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import extract_commands
from app.scenario_context import ScenarioContext


class KaliCapabilityRouterTests(unittest.TestCase):
    def _scenario(self) -> ScenarioContext:
        scenario = ScenarioContext()
        scenario.update("CTF autorizado no alvo https://wifhoodie.com.")
        return scenario

    def test_router_returns_small_ranked_subset_for_web_context(self) -> None:
        scenario = self._scenario()
        ranked = rank_capabilities(
            "Quero explorar outras possibilidades e ferramentas para essa superfície web.",
            scenario=scenario,
            history=[],
            limit=4,
        )
        self.assertEqual(len(ranked), 4)
        self.assertTrue(all(item.family in {"web", "tls", "network", "dns", "authentication", "offline", "windows"} for item in ranked))
        self.assertGreaterEqual(ranked[0].utility, ranked[-1].utility)

    def test_explicit_tool_receives_relevance_priority(self) -> None:
        scenario = self._scenario()
        ranked = rank_capabilities(
            "Quero usar sslscan nesse alvo HTTPS.",
            scenario=scenario,
            history=[],
            limit=4,
        )
        self.assertEqual(ranked[0].tool, "sslscan")
        self.assertEqual(ranked[0].relevance, 1.0)

    def test_capability_guidance_is_lazy_and_compact(self) -> None:
        scenario = self._scenario()
        guidance = capability_guidance(
            "Quais outras ferramentas podemos usar agora?",
            scenario=scenario,
            history=[{"role": "assistant", "content": "Usei Nmap para o baseline de portas."}],
        )
        self.assertIn("KALI CAPABILITY ROUTER", guidance)
        self.assertLess(guidance.count("[family="), 5)
        self.assertIn("pré-requisitos factuais", guidance)

    def test_expanded_tools_are_canonical_command_candidates(self) -> None:
        response = (
            "```bash\nsslscan wifhoodie.com:443\n```\n"
            "```bash\ntshark -r capture.pcap\n```"
        )
        commands = extract_commands(response)
        self.assertEqual(len(commands), 2)
        self.assertTrue(commands[0].startswith("sslscan "))
        self.assertTrue(commands[1].startswith("tshark "))


if __name__ == "__main__":
    unittest.main()
