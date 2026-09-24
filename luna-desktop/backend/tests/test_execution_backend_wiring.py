import os
import unittest
from unittest.mock import patch

from app.luna_engine import LunaEngine


class ExecutionBackendWiringTests(unittest.TestCase):
    def test_default_backend_is_local_subprocess(self) -> None:
        with (
            patch("app.luna_engine._ollama_is_available_sync", return_value=False),
            patch.dict(os.environ, {"LUNA_EXEC_BACKEND": "local-subprocess"}, clear=False),
        ):
            engine = LunaEngine()
        diagnostics = engine.get_local_diagnostics()
        self.assertEqual(diagnostics["execution_backend"]["kind"], "local-subprocess")
        self.assertTrue(diagnostics["execution_backend"]["ready"])

    def test_valid_kali_ssh_backend_is_selected_without_exposing_key_path(self) -> None:
        env = {
            "LUNA_EXEC_BACKEND": "kali-ssh",
            "LUNA_KALI_SSH_HOST": "192.168.56.10",
            "LUNA_KALI_SSH_USER": "kali",
            "LUNA_KALI_SSH_PORT": "22",
            "LUNA_KALI_SSH_IDENTITY": r"D:\LunaCyber\keys\kali_ed25519",
            "LUNA_KALI_SSH_KNOWN_HOSTS": r"D:\LunaCyber\config\known_hosts",
            "LUNA_KALI_SSH_HOST_KEY_POLICY": "strict",
        }
        with (
            patch("app.luna_engine._ollama_is_available_sync", return_value=False),
            patch.dict(os.environ, env, clear=False),
        ):
            engine = LunaEngine()
        backend = engine.get_local_diagnostics()["execution_backend"]
        self.assertEqual(backend["kind"], "kali-ssh")
        self.assertTrue(backend["ready"])
        self.assertTrue(backend["ssh"]["identity_file"])
        self.assertNotIn("kali_ed25519", str(backend))

    def test_invalid_kali_backend_fails_closed_and_stays_disabled_after_policy_refresh(self) -> None:
        env = {
            "LUNA_EXEC_BACKEND": "kali-ssh",
            "LUNA_KALI_SSH_HOST": "",
            "LUNA_KALI_SSH_USER": "",
            "LUNA_SUPERVISED_EXECUTOR": "true",
        }
        with (
            patch("app.luna_engine._ollama_is_available_sync", return_value=False),
            patch.dict(os.environ, env, clear=False),
        ):
            engine = LunaEngine()
            self.assertFalse(engine.supervised_executor.policy.enabled)
            engine.config["supervised_executor_enabled"] = True
            engine._refresh_supervised_executor_policy()
        self.assertFalse(engine.supervised_executor.policy.enabled)
        self.assertEqual(engine.supervised_executor.backend_name, "kali-ssh-unavailable")
        self.assertFalse(engine.get_local_diagnostics()["execution_backend"]["ready"])


if __name__ == "__main__":
    unittest.main()
