import unittest

from app.kali_tool_guidance import guidance_for_message, requested_kali_tool
from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import extract_commands


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


if __name__ == "__main__":
    unittest.main()
