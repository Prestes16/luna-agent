import unittest

from app.kali_tool_guidance import guidance_for_context, guidance_for_message, requested_kali_tool
from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import extract_commands
from app.scenario_context import ScenarioContext


class KaliToolGuidanceTests(unittest.TestCase):
    def test_nmap_guidance_prefers_explicit_scan_mode_without_output_file(self) -> None:
        message = (
            "CTF autorizado: use nmap no alvo https://wifhoodie.com e me dê "
            "o comando bash para Kali."
        )
        guidance = guidance_for_message(message)
        self.assertEqual(requested_kali_tool(message), "nmap")
        self.assertIn("-sS", guidance)
        self.assertIn("-sT", guidance)
        self.assertIn("Não crie arquivo de saída sem pedido explícito", guidance)

    def test_generic_web_nmap_guidance_includes_high_value_profile(self) -> None:
        message = (
            "CTF autorizado: use nmap no alvo https://wifhoodie.com e me dê "
            "o comando bash para Kali."
        )
        guidance = guidance_for_message(message)
        self.assertIn("WEB HIGH-VALUE PORT PROFILE", guidance)
        self.assertIn("80,443", guidance)
        self.assertIn("3306", guidance)
        self.assertIn("6379", guidance)

    def test_ffuf_guidance_requires_factual_wordlist(self) -> None:
        message = "Quero usar ffuf nesse CTF autorizado."
        guidance = guidance_for_message(message)
        self.assertEqual(requested_kali_tool(message), "ffuf")
        self.assertIn("FUZZ", guidance)
        self.assertIn("não invente path local", guidance)

    def test_extended_kali_command_is_extracted_from_bash_fence(self) -> None:
        response = (
            "```bash\n"
            "ffuf -u https://lab.local/FUZZ -w /usr/share/seclists/Discovery/Web-Content/common.txt\n"
            "```"
        )
        commands = extract_commands(response)
        self.assertEqual(len(commands), 1)
        self.assertTrue(commands[0].startswith("ffuf "))

    def test_followup_nmap_optimization_uses_contextual_port_profile(self) -> None:
        scenario = ScenarioContext()
        scenario.update("CTF autorizado no alvo https://wifhoodie.com.")
        history = [
            {"role": "assistant", "content": "```bash\nsudo nmap -sS -p 80,443 wifhoodie.com\n```"},
        ]
        guidance = guidance_for_context(
            "Agora otimize esse comando para as principais portas de maior valor.",
            scenario=scenario,
            history=history,
        )
        self.assertIn("TOOL CONTRACT [nmap]", guidance)
        self.assertIn("WEB HIGH-VALUE PORT PROFILE", guidance)
        self.assertIn("3306", guidance)
        self.assertNotIn("--top-ports quando", guidance.split("prefira -p", 1)[-1][:20])

    def test_other_tools_followup_injects_capability_router(self) -> None:
        scenario = ScenarioContext()
        scenario.update("CTF autorizado no alvo https://wifhoodie.com.")
        history = [
            {"role": "assistant", "content": "```bash\nsudo nmap -sS -p 80,443 wifhoodie.com\n```"},
        ]
        guidance = guidance_for_context(
            "Agora quero explorar outras possibilidades e ferramentas.",
            scenario=scenario,
            history=history,
        )
        self.assertIn("KALI CAPABILITY ROUTER", guidance)
        self.assertIn("candidatos, não ações automáticas", guidance)
    def test_hydra_guidance_requests_missing_facts_instead_of_inventing(self) -> None:
        scenario = ScenarioContext()
        scenario.update("CTF autorizado no alvo https://wifhoodie.com.")
        guidance = guidance_for_context(
            "Agora use Hydra e me dê o comando no Kali.",
            scenario=scenario,
            history=[],
        )
        self.assertIn("TOOL READINESS [hydra]", guidance)
        self.assertIn("service/module", guidance)
        self.assertIn("identity source", guidance)
        self.assertIn("secret source", guidance)
        self.assertIn("não gere comando", guidance)

if __name__ == "__main__":
    unittest.main()
