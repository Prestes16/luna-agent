import hashlib
import unittest

from app.command_policy import assess_command_policy, effective_tool
from app.luna_engine import LunaEngine  # noqa: F401
from app.operational_transform import transform_response_commands
from app.reasoning_pipeline import validate_model_response
from app.reasoning_runtime_patch_v8 import command_attestations
from app.scenario_context import ScenarioContext


GENERIC_PROMPT = (
    "Luna, estou em um CTF autorizado e preciso executar um scan tipo nmap no alvo "
    "https://wifhoodie.com. Me dê o comando bash para eu executar no meu Kali Linux."
)
ARTIFACT_PROMPT = (
    "Luna, CTF autorizado: faça um scan nmap no alvo https://wifhoodie.com e salve "
    "o resultado em /home/kali/Desktop/scan_wifhoodie.txt. Me dê o comando bash."
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

    def test_generic_scan_does_not_create_output_file(self) -> None:
        response = "```bash\nnmap -sS wifhoodie.com\n```"
        validation = self._validate(GENERIC_PROMPT, response)
        self.assertTrue(validation.valid, validation.reasons)
        transformed, mutations = transform_response_commands(GENERIC_PROMPT, response)
        self.assertEqual(len(mutations), 1)
        self.assertIn("sudo nmap -sS wifhoodie.com", transformed)
        self.assertNotIn("-oN", transformed)
        self.assertNotIn(".txt", transformed)

    def test_already_privileged_syn_scan_needs_no_mutation(self) -> None:
        response = "```bash\nsudo nmap -sS wifhoodie.com\n```"
        validation = self._validate(GENERIC_PROMPT, response)
        self.assertTrue(validation.valid, validation.reasons)
        transformed, mutations = transform_response_commands(GENERIC_PROMPT, response)
        self.assertEqual(mutations, [])
        self.assertIn("sudo nmap -sS wifhoodie.com", transformed)
        self.assertNotIn("-oN", transformed)

    def test_explicit_artifact_path_can_be_added_deterministically(self) -> None:
        response = "```bash\nnmap -sS wifhoodie.com\n```"
        validation = self._validate(ARTIFACT_PROMPT, response)
        self.assertTrue(validation.valid, validation.reasons)
        transformed, mutations = transform_response_commands(ARTIFACT_PROMPT, response)
        self.assertEqual(len(mutations), 1)
        self.assertIn("sudo nmap -sS wifhoodie.com", transformed)
        self.assertIn("-oN /home/kali/Desktop/scan_wifhoodie.txt", transformed)

    def test_privileged_nmap_mode_gets_deterministic_sudo(self) -> None:
        response = "```bash\nnmap -A wifhoodie.com\n```"
        validation = self._validate(AGGRESSIVE_PROMPT, response)
        self.assertTrue(validation.valid, validation.reasons)
        transformed, mutations = transform_response_commands(AGGRESSIVE_PROMPT, response)
        self.assertEqual(len(mutations), 1)
        self.assertIn("sudo nmap -A wifhoodie.com", transformed)
        self.assertNotIn(".txt", transformed)

    def test_sudo_wrapped_privileged_nmap_is_recognized(self) -> None:
        command = "sudo nmap -A wifhoodie.com"
        response = f"```bash\n{command}\n```"
        validation = self._validate(AGGRESSIVE_PROMPT, response)
        self.assertNotIn("nmap_privileged_mode_missing_sudo", validation.reasons)
        self.assertNotIn("critical_tool_veto", validation.reasons)
        self.assertEqual(effective_tool(command), "nmap")
        self.assertTrue(validation.valid, validation.reasons)

    def test_sha256_attestation_matches_exact_command(self) -> None:
        command = "sudo nmap -sS wifhoodie.com"
        response = f"```bash\n{command}\n```"
        attestations = command_attestations(GENERIC_PROMPT, response)
        self.assertEqual(len(attestations), 1)
        self.assertEqual(
            attestations[0]["sha256"],
            hashlib.sha256(command.encode("utf-8")).hexdigest(),
        )
        self.assertTrue(attestations[0]["target_verified"])
        self.assertFalse(attestations[0]["artifact_required"])
        self.assertFalse(attestations[0]["artifact_present"])

    def test_generic_policy_never_synthesizes_artifact_name(self) -> None:
        assessment = assess_command_policy(GENERIC_PROMPT, "sudo nmap -sS wifhoodie.com")
        self.assertFalse(assessment.artifact_required)
        self.assertIsNone(assessment.recommended_artifact)

    def test_input_filename_does_not_imply_output_artifact(self) -> None:
        message = (
            "CTF autorizado: use nmap com -iL /home/kali/Desktop/targets.txt "
            "e me dê o comando bash."
        )
        assessment = assess_command_policy(
            message,
            "sudo nmap -sS -iL /home/kali/Desktop/targets.txt",
        )
        self.assertFalse(assessment.artifact_required)
        self.assertIsNone(assessment.recommended_artifact)

    def test_input_file_is_not_reused_as_output_when_persistence_is_requested(self) -> None:
        message = (
            "CTF autorizado: use nmap com -iL /home/kali/Desktop/targets.txt, "
            "salve o resultado e me dê o comando bash."
        )
        assessment = assess_command_policy(
            message,
            "sudo nmap -sS -iL /home/kali/Desktop/targets.txt",
        )
        self.assertTrue(assessment.artifact_required)
        self.assertIsNone(assessment.recommended_artifact)

        response = "```bash\nsudo nmap -sS -iL /home/kali/Desktop/targets.txt\n```"
        validation = self._validate(message, response)
        self.assertFalse(validation.valid)
        self.assertIn("nmap_scan_artifact_missing", validation.reasons)

        transformed, mutations = transform_response_commands(message, response)
        self.assertEqual(mutations, [])
        self.assertNotIn("-oN /home/kali/Desktop/targets.txt", transformed)

    def test_output_path_after_persistence_marker_is_preserved(self) -> None:
        message = (
            "CTF autorizado: use nmap com -iL /home/kali/Desktop/targets.txt "
            "e salve o resultado em /home/kali/Desktop/scan_result.txt."
        )
        assessment = assess_command_policy(
            message,
            "sudo nmap -sS -iL /home/kali/Desktop/targets.txt",
        )
        self.assertTrue(assessment.artifact_required)
        self.assertEqual(
            assessment.recommended_artifact,
            "/home/kali/Desktop/scan_result.txt",
        )

    def test_target_mismatch_is_never_auto_repaired(self) -> None:
        response = "```bash\nnmap -sS example.com\n```"
        validation = self._validate(GENERIC_PROMPT, response)
        self.assertFalse(validation.valid)
        transformed, mutations = transform_response_commands(GENERIC_PROMPT, response)
        self.assertEqual(mutations, [])
        self.assertIn("example.com", transformed)


if __name__ == "__main__":
    unittest.main()
