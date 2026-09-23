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

    def test_authorized_ctf_does_not_promote_privacy_family_by_substring(self) -> None:
        scenario = self._scenario()
        ranked = rank_capabilities(
            "CTF autorizado: quero analisar uma superfície web HTTP.",
            scenario=scenario,
            history=[],
            limit=4,
        )
        self.assertTrue(all(item.family != "privacy" for item in ranked))

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

    def test_http_interception_prefers_proxy_family_over_packet_capture(self) -> None:
        scenario = self._scenario()
        ranked = rank_capabilities(
            "Qual é o melhor app no Kali para interceptar requisições HTTP e poder inspecionar/replay?",
            scenario=scenario,
            history=[],
            limit=4,
        )
        self.assertEqual(ranked[0].family, "web_proxy")
        self.assertIn(ranked[0].tool, {"burpsuite", "mitmproxy", "zaproxy"})
        self.assertNotEqual(ranked[0].tool, "wireshark")

    def test_explicit_wireshark_is_packet_capture_not_proxy(self) -> None:
        scenario = self._scenario()
        ranked = rank_capabilities(
            "Quero usar wireshark para analisar uma captura de pacotes.",
            scenario=scenario,
            history=[],
            limit=4,
        )
        self.assertEqual(ranked[0].tool, "wireshark")
        self.assertEqual(ranked[0].family, "packet_capture")
        self.assertIn("packet capture", ranked[0].purpose)

    def test_alternative_request_penalizes_already_mentioned_tool(self) -> None:
        scenario = self._scenario()
        ranked = rank_capabilities(
            "Mais algum? Quero outra alternativa para interceptar requisições.",
            scenario=scenario,
            history=[
                {"role": "assistant", "content": "BurpSuite é um proxy de interceptação HTTP(S)."}
            ],
            limit=4,
        )
        self.assertNotEqual(ranked[0].tool, "burpsuite")
        self.assertEqual(ranked[0].family, "web_proxy")

    def test_interception_guidance_scopes_delivery_to_current_turn(self) -> None:
        scenario = self._scenario()
        guidance = capability_guidance(
            "Qual o melhor app para interceptar requisições no Kali?",
            scenario=scenario,
            history=[
                {"role": "user", "content": "Me dê apenas um comando bash."}
            ],
        )
        self.assertIn("proxy de interceptação HTTP(S) != captura de pacotes", guidance)
        self.assertIn("turnos anteriores", guidance)
        self.assertIn("Não emita comando", guidance)

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
