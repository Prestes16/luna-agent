import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from app.luna_engine import LunaEngine
from app.scenario_context import ScenarioContext
from app.supervised_executor import RunnerResult


class SupervisedExecutionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_engine = main.luna_engine
        with patch("app.luna_engine._ollama_is_available_sync", return_value=False):
            self.engine = LunaEngine()
        scenario = ScenarioContext()
        scenario.update("CTF autorizado em http://10.10.10.5")
        self.engine.scenario_contexts["api-exec"] = scenario

        self.calls = []

        async def fake_runner(argv, timeout_seconds, max_output_bytes):
            self.calls.append((argv, timeout_seconds, max_output_bytes))
            return RunnerResult(
                exit_code=0,
                stdout=b"probe-ok\n",
                stderr=b"",
            )

        self.engine.supervised_executor._runner = fake_runner
        main.luna_engine = self.engine
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.client.close()
        main.luna_engine = self.previous_engine

    def _body(self, command: str) -> dict:
        return {
            "command": command,
            "session_id": "api-exec",
            "operator_request_text": "Luna, rode esse teste no alvo autorizado.",
            "rollback_ready": False,
            "verification_ready": True,
        }

    def test_preview_binds_scope_and_target(self) -> None:
        response = self.client.post(
            "/api/execution/preview",
            json=self._body("nmap -sV 10.10.10.5"),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["authority"], "ON_DEMAND")
        self.assertEqual(data["target"], "10.10.10.5")

    def test_l1_run_is_denied_until_executor_is_enabled(self) -> None:
        denied = self.client.post(
            "/api/execution/run",
            json=self._body("nmap -sV 10.10.10.5"),
        )
        self.assertEqual(denied.status_code, 200)
        self.assertEqual(denied.json()["status"], "denied")
        self.assertIn(
            "supervised_executor_disabled",
            denied.json()["denial_reasons"],
        )
        self.assertEqual(self.calls, [])

        updated = self.client.post(
            "/api/config",
            json={"supervised_executor_enabled": True},
        )
        self.assertEqual(updated.status_code, 200)

        allowed = self.client.post(
            "/api/execution/run",
            json=self._body("nmap -sV 10.10.10.5"),
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json()["status"], "executed")
        self.assertEqual(allowed.json()["stdout"], "probe-ok\n")
        self.assertEqual(len(self.calls), 1)

    def test_privileged_probe_requires_one_shot_operator_approval(self) -> None:
        self.client.post(
            "/api/config",
            json={"supervised_executor_enabled": True},
        )
        command = "sudo nmap -sS 10.10.10.5"
        approval_body = {
            **self._body(command),
            "operator_confirmed": True,
            "ttl_seconds": 120,
            "allow_destructive": False,
            "allow_persistent_change": False,
        }
        approved = self.client.post(
            "/api/execution/approve",
            json=approval_body,
        )
        self.assertEqual(approved.status_code, 200)
        token = approved.json()["approval_token"]
        self.assertTrue(token)

        first = self.client.post(
            "/api/execution/run",
            json={**self._body(command), "approval_token": token},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "executed")
        self.assertEqual(len(self.calls), 1)

        second = self.client.post(
            "/api/execution/run",
            json={**self._body(command), "approval_token": token},
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["status"], "denied")
        self.assertIn(
            "approval_token_invalid_or_expired",
            second.json()["denial_reasons"],
        )
        self.assertEqual(len(self.calls), 1)

    def test_approval_token_is_bound_to_session_scope(self) -> None:
        self.client.post(
            "/api/config",
            json={"supervised_executor_enabled": True},
        )
        other = ScenarioContext()
        other.update("CTF autorizado em http://10.10.10.5")
        self.engine.scenario_contexts["api-other"] = other

        command = "sudo nmap -sS 10.10.10.5"
        approved = self.client.post(
            "/api/execution/approve",
            json={
                **self._body(command),
                "operator_confirmed": True,
                "ttl_seconds": 120,
            },
        )
        self.assertEqual(approved.status_code, 200)
        token = approved.json()["approval_token"]

        cross_scope = self.client.post(
            "/api/execution/run",
            json={
                **self._body(command),
                "session_id": "api-other",
                "approval_token": token,
            },
        )
        self.assertEqual(cross_scope.status_code, 200)
        self.assertEqual(cross_scope.json()["status"], "denied")
        self.assertIn(
            "operator_approval_mismatch_or_expired",
            cross_scope.json()["denial_reasons"],
        )
        self.assertEqual(self.calls, [])

    def test_approval_requires_explicit_operator_confirmation(self) -> None:
        command = "sudo nmap -sS 10.10.10.5"
        response = self.client.post(
            "/api/execution/approve",
            json={
                **self._body(command),
                "operator_confirmed": False,
                "ttl_seconds": 120,
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_target_mismatch_stays_blocked(self) -> None:
        response = self.client.post(
            "/api/execution/preview",
            json=self._body("nmap -sV 10.10.10.6"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["authority"], "BLOCKED")
        self.assertIn(
            "target_scope_mismatch",
            response.json()["reasons"],
        )

    def test_supervised_config_rejects_wrong_types_and_bounds(self) -> None:
        wrong_bool = self.client.post(
            "/api/config",
            json={"supervised_executor_enabled": "true"},
        )
        self.assertEqual(wrong_bool.status_code, 422)

        wrong_timeout = self.client.post(
            "/api/config",
            json={"supervised_timeout_seconds": 0},
        )
        self.assertEqual(wrong_timeout.status_code, 422)

        valid = self.client.post(
            "/api/config",
            json={
                "supervised_executor_enabled": True,
                "supervised_timeout_seconds": 30,
                "supervised_max_output_bytes": 4096,
            },
        )
        self.assertEqual(valid.status_code, 200)
        policy = self.engine.supervised_executor.public_policy()
        self.assertTrue(policy["enabled"])
        self.assertEqual(policy["timeout_seconds"], 30)
        self.assertEqual(policy["max_output_bytes"], 4096)

    def test_generic_config_does_not_enable_l3(self) -> None:
        response = self.client.post(
            "/api/config",
            json={"supervised_allow_l3": True},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.engine.config["supervised_allow_l3"])


if __name__ == "__main__":
    unittest.main()
