import hashlib
import unittest

from app.command_policy import assess_command_policy, effective_tool
from app.luna_engine import LunaEngine  # noqa: F401
from app.reasoning_pipeline import validate_model_response
from app.reasoning_runtime_patch_v8 import command_attestations
from app.scenario_context import ScenarioContext


GENERIC_PROMPT = (
    "Luna, estou em um CTF autorizado e preciso executar um scan tipo nmap no alvo "
    "https://wifhoodie.com. Me dê o comando bash para eu executar no meu Kali Linux."
)
AGGRESSIVE_PROMPT = (
    "CTF autorizado: quero um scan nmap agressivo e completo no alvo "
    "https://wifhoodie.com. Me dê um comando bash para eu executar no Kali."
)


class OperationalCommandPolicyTests(unittest.TestCase):
    def _validate(self, message: str, response: str):
        scenario = ScenarioContext()
        delta = scenario.update(message)
        return validate_model_response(
            message=message,
            response=response,
            scenario=scenario,
            evidence_delta_count=delta.count,
        )

    def test_generic_scan_requires_persistent_artifact(self) -> None:
        response = "```bash\nnmap -sV wifhoodie.com\n```"
        validation = self._validate(GENERIC_PROMPT, response)
        self.assertFalse(validation.valid)
        self.assertIn("nmap_scan_artifact_missing", validation.reasons)

    def test_focused_scan_with_artifact_is_operator_ready(self) -> None:
        response = "```bash\nnmap -sV wifhoodie.com -oN scan_wifhoodie_com.txt\n```"
        validation = self._validate(GENERIC_PROMPT, response)
        self.assertTrue(validation.valid, validation.reasons)

    def test_privileged_nmap_mode_requires_sudo(self) -> None:
        response = "```bash\nnmap -A wifhoodie.com -oN scan_wifhoodie_com.txt\n```"
        validation = self._validate(AGGRESSIVE_PROMPT, response)
        self.assertFalse(validation.valid)
        self.assertIn("nmap_privileged_mode_missing_sudo", validation.reasons)

    def test_sudo_wrapped_privileged_nmap_is_recognized(self) -> None:
        command = "sudo nmap -A wifhoodie.com -oN scan_wifhoodie_com.txt"
        response = f"```bash\n{command}\n```"
        validation = self._validate(AGGRESSIVE_PROMPT, response)
        self.assertNotIn("nmap_privileged_mode_missing_sudo", validation.reasons)
        self.assertNotIn("critical_tool_veto", validation.reasons)
        self.assertEqual(effective_tool(command), "nmap")
        self.assertTrue(validation.valid, validation.reasons)

    def test_sha256_attestation_matches_exact_command(self) -> None:
        command = "nmap -sV wifhoodie.com -oN scan_wifhoodie_com.txt"
        response = f"```bash\n{command}\n```"
        attestations = command_attestations(GENERIC_PROMPT, response)
        self.assertEqual(len(attestations), 1)
        self.assertEqual(
            attestations[0]["sha256"],
            hashlib.sha256(command.encode("utf-8")).hexdigest(),
        )
        self.assertTrue(attestations[0]["target_verified"])
        self.assertTrue(attestations[0]["artifact_present"])

    def test_policy_recommends_deterministic_artifact_name(self) -> None:
        assessment = assess_command_policy(GENERIC_PROMPT, "nmap -sV wifhoodie.com")
        self.assertEqual(assessment.recommended_artifact, "scan_wifhoodie_com.txt")


if __name__ == "__main__":
    unittest.main()
