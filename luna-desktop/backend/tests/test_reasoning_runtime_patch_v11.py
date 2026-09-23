import unittest

from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import validate_model_response
from app.scenario_context import ScenarioContext


class PrivacyRoutingValidatorTests(unittest.TestCase):
    def _validate(self, message: str, response: str):
        scenario = ScenarioContext()
        delta = scenario.update(message)
        return validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )

    def test_anonymity_overclaim_is_rejected(self) -> None:
        validation = self._validate(
            "Quero configurar Tor e proxychains no Kali.",
            "Isso garante anonimato 100% e torna impossível rastrear sua origem.",
        )
        self.assertFalse(validation.valid)
        self.assertIn("privacy_anonymity_overclaim", validation.reasons)

    def test_direct_fallback_after_privacy_failure_is_rejected(self) -> None:
        validation = self._validate(
            "Quero usar VPN de forma fail-closed.",
            "Se a VPN falhar, continue diretamente pela conexão direta para não interromper o trabalho.",
        )
        self.assertFalse(validation.valid)
        self.assertIn("privacy_direct_fallback_suggested", validation.reasons)

    def test_proxychains_raw_nmap_scan_is_rejected(self) -> None:
        validation = self._validate(
            "CTF autorizado: quero usar proxychains com Tor e nmap no alvo https://wifhoodie.com.",
            "```bash\nproxychains4 nmap -sS wifhoodie.com\n```",
        )
        self.assertFalse(validation.valid)
        self.assertIn("privacy_raw_socket_proxy_mismatch", validation.reasons)

    def test_unobserved_proxychains_config_path_is_rejected(self) -> None:
        validation = self._validate(
            "Quero configurar proxychains no Kali; ainda não localizei o arquivo de configuração.",
            "```bash\nsudo nano /etc/proxychains4.conf\n```",
        )
        self.assertFalse(validation.valid)
        self.assertIn("privacy_unobserved_config_path", validation.reasons)

    def test_unobserved_tor_socks_port_is_rejected(self) -> None:
        validation = self._validate(
            "Quero configurar Tor; ainda não validei o listener SOCKS.",
            "```bash\ncurl --proxy socks5h://127.0.0.1:9050 https://example.test\n```",
        )
        self.assertFalse(validation.valid)
        self.assertIn("privacy_unobserved_socks_endpoint", validation.reasons)

    def test_observed_socks_endpoint_is_not_rejected_by_v11(self) -> None:
        message = (
            "Validei que o Tor escuta em 127.0.0.1:9050. Quero testar esse listener com curl."
        )
        validation = self._validate(
            message,
            "```bash\ncurl --proxy socks5h://127.0.0.1:9050 https://example.test\n```",
        )
        self.assertNotIn("privacy_unobserved_socks_endpoint", validation.reasons)


if __name__ == "__main__":
    unittest.main()
