import unittest

from app.kali_capability_router import rank_capabilities
from app.kali_tool_guidance import guidance_for_context, requested_kali_tool
from app.luna_engine import LunaEngine  # noqa: F401
from app.network_privacy import (
    best_privacy_route,
    privacy_configuration_guidance,
    privacy_guidance,
    privacy_intent,
    privacy_preflight_guidance,
    local_privacy_preflight_needed,
    score_privacy_routes,
)
from app.reasoning_pipeline import extract_commands
from app.scenario_context import ScenarioContext


class NetworkPrivacyTests(unittest.TestCase):
    def _scenario(self) -> ScenarioContext:
        scenario = ScenarioContext()
        scenario.update("Ambiente Kali local e CTF autorizado.")
        return scenario

    def test_authorized_ctf_text_does_not_false_trigger_tor_privacy(self) -> None:
        self.assertFalse(
            privacy_intent("Estou em um CTF autorizado e quero executar um scan Nmap.")
        )

    def test_privacy_intent_detects_proxychains_tor_and_vpn(self) -> None:
        self.assertTrue(privacy_intent("Configure proxychains com Tor."))
        self.assertTrue(privacy_intent("Quero usar uma VPN WireGuard."))
        self.assertFalse(privacy_intent("Faça um scan Nmap simples."))

    def test_udp_context_prefers_vpn_capable_route(self) -> None:
        best = best_privacy_route("Preciso de privacidade para tráfego UDP e QUIC usando VPN.")
        self.assertEqual(best.profile.name, "vpn")
        self.assertTrue(best.profile.supports_udp)

    def test_explicit_proxychains_intent_penalizes_unrelated_routes(self) -> None:
        ranked = score_privacy_routes("Quero configurar proxychains para uma aplicação HTTPS TCP.")
        self.assertEqual(ranked[0].profile.name, "proxychains_tor")
        vpn = next(item for item in ranked if item.profile.name == "vpn")
        self.assertIn("explicit_route_family_mismatch", vpn.reasons)

    def test_raw_nmap_over_tor_is_marked_incompatible(self) -> None:
        ranked = score_privacy_routes("Quero usar Tor com nmap -sS SYN scan.")
        tor = next(item for item in ranked if item.profile.name == "tor")
        self.assertIn("nmap_raw_scan_not_proxyable_through_socks", tor.reasons)
        self.assertGreater(tor.mismatch_penalty, 0.5)

    def test_privacy_guidance_never_promises_anonymity(self) -> None:
        guidance = privacy_guidance("Quero dificultar rastreamento usando Tor e VPN.")
        self.assertIn("não garantia de anonimato", guidance)
        self.assertIn("nunca prometa não-rastreabilidade", guidance)
        self.assertIn("IPv4", guidance)
        self.assertIn("IPv6", guidance)

    def test_privacy_guidance_separates_network_route_from_application_identity(self) -> None:
        guidance = privacy_guidance("Quero usar Tor para melhorar minha privacidade no navegador.")
        self.assertIn("cookies", guidance)
        self.assertIn("fingerprint", guidance)
        self.assertIn("WebRTC", guidance)
        self.assertIn("correlação temporal", guidance)

    def test_vpn_tor_workflow_requires_explicit_layer_order(self) -> None:
        guidance = privacy_configuration_guidance(
            "Quero combinar VPN e Tor de forma segura."
        )
        self.assertIn("LAYER ORDER", guidance)
        self.assertIn("VPN->Tor", guidance)
        self.assertIn("Tor->VPN", guidance)
        self.assertIn("not equivalent", guidance)

    def test_configuration_workflow_is_fail_closed_and_reversible(self) -> None:
        guidance = privacy_configuration_guidance(
            "Configure proxychains com Tor e depois valide DNS e IPv6."
        )
        self.assertIn("DISCOVER -> CONFIGURE -> VERIFY -> FAIL-CLOSED -> ROLLBACK", guidance)
        self.assertIn("do not hardcode 9050 or 9150", guidance)
        self.assertIn("proxy_dns", guidance)
        self.assertIn("reversible", guidance)

    def test_unknown_local_privacy_prerequisites_do_not_require_remote_target(self) -> None:
        context = (
            "Estou no Kali. Não sei se Tor e Proxychains estão instalados, não sei qual "
            "arquivo de configuração existe e não confirmei nenhuma porta SOCKS."
        )
        self.assertTrue(local_privacy_preflight_needed(context))
        guidance = privacy_preflight_guidance(context)
        self.assertIn("remote target/base URL is NOT required", guidance)
        self.assertIn("command -v tor proxychains4 proxychains", guidance)
        self.assertIn("does NOT prove", guidance)
    def test_contextual_guidance_includes_privacy_math_and_workflow(self) -> None:
        scenario = self._scenario()
        guidance = guidance_for_context(
            "Quero configurar proxychains e Tor de forma segura no Kali.",
            scenario=scenario,
            history=[],
        )
        self.assertIn("PRIVACY ROUTING ENGINE", guidance)
        self.assertIn("PRIVACY CONFIG WORKFLOW", guidance)
        self.assertIn("PRIVACY TOOLING", guidance)

    def test_privacy_tools_are_detected_and_commands_are_extractable(self) -> None:
        self.assertEqual(requested_kali_tool("Quero usar proxychains4."), "proxychains4")
        response = (
            "```bash\nproxychains4 curl https://example.test\n```\n"
            "```bash\nwg-quick up wg0\n```"
        )
        commands = extract_commands(response)
        self.assertEqual(len(commands), 2)
        self.assertTrue(commands[0].startswith("proxychains4 "))
        self.assertTrue(commands[1].startswith("wg-quick "))

    def test_capability_router_surfaces_privacy_family(self) -> None:
        scenario = self._scenario()
        ranked = rank_capabilities(
            "Quero melhorar privacidade com Tor, proxychains ou VPN.",
            scenario=scenario,
            history=[],
            limit=5,
        )
        self.assertTrue(any(item.family == "privacy" for item in ranked))


if __name__ == "__main__":
    unittest.main()
