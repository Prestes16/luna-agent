import unittest

from app.threat_response import select_response_profiles, threat_response_guidance


class ThreatResponseTests(unittest.TestCase):
    def test_ransomware_profile_requires_evidence_preservation_before_cleanup(self) -> None:
        guidance = threat_response_guidance("Ransomware criptografou arquivos e deixou ransom note.")
        self.assertIn("ransomware", guidance)
        self.assertIn("evidence preservation precedes destructive cleanup", guidance)
        self.assertIn("offline/immutable backups", guidance)

    def test_stealer_profile_rotates_credentials_from_clean_device(self) -> None:
        guidance = threat_response_guidance("Credential stealer e RAT foram observados.")
        self.assertIn("stealer_rat", guidance)
        self.assertIn("rotate credentials from a clean device", guidance)
        self.assertIn("revoke sessions/tokens", guidance)

    def test_rootkit_profile_prefers_trusted_rebuild(self) -> None:
        guidance = threat_response_guidance("Suspeita de rootkit e bootkit no endpoint.")
        self.assertIn("rootkit_bootkit", guidance)
        self.assertIn("trusted-media rebuild/reimage", guidance)
        self.assertIn("boot chain", guidance)

    def test_webshell_profile_closes_initial_access_path(self) -> None:
        guidance = threat_response_guidance("Encontramos um webshell malicious PHP no servidor.")
        self.assertIn("webshell", guidance)
        self.assertIn("fix the vulnerability or credential path", guidance)
        self.assertIn("webroot integrity", guidance)

    def test_irrelevant_context_does_not_inject_response_plan(self) -> None:
        self.assertEqual(threat_response_guidance("Olá, bom dia."), "")


if __name__ == "__main__":
    unittest.main()
