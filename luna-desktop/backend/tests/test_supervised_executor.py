import asyncio
import hashlib
import unittest

from app.execution_intent import L1_PROBE, L2_MUTATE, L3_HIGH_IMPACT
from app.supervised_executor import (
    ExecutionApproval,
    RunnerResult,
    SupervisedExecutionPolicy,
    SupervisedExecutor,
)


class FakeRunner:
    def __init__(self, *, stdout=b"ok\n", stderr=b"", exit_code=0):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.calls = []

    async def __call__(self, argv, timeout_seconds, max_output_bytes):
        self.calls.append((argv, timeout_seconds, max_output_bytes))
        return RunnerResult(
            exit_code=self.exit_code,
            stdout=self.stdout,
            stderr=self.stderr,
        )


class SupervisedExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_policy_never_calls_runner(self) -> None:
        runner = FakeRunner()
        executor = SupervisedExecutor(runner=runner)
        result = await executor.execute("cat /etc/hosts")
        self.assertEqual(result.status, "denied")
        self.assertIn("supervised_executor_disabled", result.denial_reasons)
        self.assertEqual(runner.calls, [])

    async def test_enabled_l0_executes_and_hashes_evidence(self) -> None:
        runner = FakeRunner(stdout=b"127.0.0.1 localhost\n")
        executor = SupervisedExecutor(
            SupervisedExecutionPolicy(enabled=True),
            runner=runner,
        )
        result = await executor.execute("cat /etc/hosts")
        self.assertEqual(result.status, "executed")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(len(result.evidence), 1)
        self.assertEqual(
            result.evidence[0].sha256,
            hashlib.sha256(b"127.0.0.1 localhost\n").hexdigest(),
        )

    async def test_l1_probe_requires_current_operator_request(self) -> None:
        runner = FakeRunner()
        executor = SupervisedExecutor(
            SupervisedExecutionPolicy(enabled=True),
            runner=runner,
        )
        result = await executor.execute(
            "nmap -sV 10.10.10.5",
            context="CTF autorizado",
            operator_requested_execution=False,
            scope_confirmed=True,
            scope_target="10.10.10.5",
        )
        self.assertEqual(result.status, "denied")
        self.assertIn("operator_execution_not_requested", result.denial_reasons)
        self.assertEqual(runner.calls, [])

    async def test_l1_probe_executes_on_demand_when_scope_and_target_match(self) -> None:
        runner = FakeRunner(stdout=b"80/tcp open http\n")
        executor = SupervisedExecutor(
            SupervisedExecutionPolicy(enabled=True),
            runner=runner,
        )
        result = await executor.execute(
            "nmap -sV 10.10.10.5",
            context="CTF autorizado",
            operator_requested_execution=True,
            scope_confirmed=True,
            scope_target="10.10.10.5",
        )
        self.assertEqual(result.status, "executed")
        self.assertEqual(result.intent["authority_level"], L1_PROBE)
        self.assertEqual(result.intent["target"], "10.10.10.5")
        self.assertEqual(len(runner.calls), 1)

    async def test_privileged_probe_requires_exact_approval(self) -> None:
        command = "sudo nmap -sS 10.10.10.5"
        runner = FakeRunner()
        executor = SupervisedExecutor(
            SupervisedExecutionPolicy(enabled=True),
            runner=runner,
        )
        denied = await executor.execute(
            command,
            context="CTF autorizado em Kali",
            operator_requested_execution=True,
            scope_confirmed=True,
            scope_target="10.10.10.5",
        )
        self.assertEqual(denied.status, "denied")
        self.assertIn("operator_approval_missing", denied.denial_reasons)

        preview = executor.preview(
            command,
            context="CTF autorizado em Kali",
            operator_requested_execution=True,
            scope_confirmed=True,
            scope_target="10.10.10.5",
        )
        approval = ExecutionApproval.issue(
            command=command,
            target=preview.target,
            authority_level=preview.authority_level,
            now=1000.0,
        )
        allowed = await executor.execute(
            command,
            context="CTF autorizado em Kali",
            operator_requested_execution=True,
            scope_confirmed=True,
            scope_target="10.10.10.5",
            approval=approval,
            now=1001.0,
        )
        self.assertEqual(allowed.status, "executed")
        self.assertEqual(len(runner.calls), 1)

    async def test_expired_or_command_mismatched_approval_is_rejected(self) -> None:
        command = "sudo nmap -sS 10.10.10.5"
        runner = FakeRunner()
        executor = SupervisedExecutor(
            SupervisedExecutionPolicy(enabled=True),
            runner=runner,
        )
        preview = executor.preview(
            command,
            context="CTF autorizado em Kali",
            operator_requested_execution=True,
            scope_confirmed=True,
            scope_target="10.10.10.5",
        )
        approval = ExecutionApproval.issue(
            command=command,
            target=preview.target,
            authority_level=preview.authority_level,
            ttl_seconds=10,
            now=1000.0,
        )
        result = await executor.execute(
            command,
            context="CTF autorizado em Kali",
            operator_requested_execution=True,
            scope_confirmed=True,
            scope_target="10.10.10.5",
            approval=approval,
            now=1011.0,
        )
        self.assertEqual(result.status, "denied")
        self.assertIn("operator_approval_mismatch_or_expired", result.denial_reasons)
        self.assertEqual(runner.calls, [])

    async def test_l2_local_mutation_needs_level_enable_and_approval(self) -> None:
        command = "sudo systemctl restart tor"
        runner = FakeRunner()
        disabled = SupervisedExecutor(
            SupervisedExecutionPolicy(enabled=True, allow_l2=False),
            runner=runner,
        )
        preview = disabled.preview(
            command,
            context="Kali VM laboratório autorizado",
            operator_requested_execution=True,
            scope_confirmed=True,
            rollback_ready=True,
        )
        self.assertEqual(preview.authority_level, L2_MUTATE)
        approval = ExecutionApproval.issue(
            command=command,
            target=preview.target,
            authority_level=preview.authority_level,
            now=1000.0,
        )
        denied = await disabled.execute(
            command,
            context="Kali VM laboratório autorizado",
            operator_requested_execution=True,
            scope_confirmed=True,
            rollback_ready=True,
            approval=approval,
            now=1001.0,
        )
        self.assertEqual(denied.status, "denied")
        self.assertIn("l2_mutate_disabled", denied.denial_reasons)

        enabled = SupervisedExecutor(
            SupervisedExecutionPolicy(enabled=True, allow_l2=True),
            runner=runner,
        )
        allowed = await enabled.execute(
            command,
            context="Kali VM laboratório autorizado",
            operator_requested_execution=True,
            scope_confirmed=True,
            rollback_ready=True,
            approval=approval,
            now=1001.0,
        )
        self.assertEqual(allowed.status, "executed")

    async def test_l3_destructive_requires_explicit_destructive_grant(self) -> None:
        command = "rm -rf /tmp/luna-proof"
        runner = FakeRunner()
        executor = SupervisedExecutor(
            SupervisedExecutionPolicy(enabled=True, allow_l3=True),
            runner=runner,
        )
        preview = executor.preview(
            command,
            context=(
                "Kali VM laboratório autorizado; alvo destrutivo exato "
                "/tmp/luna-proof"
            ),
            operator_requested_execution=True,
            scope_confirmed=True,
            rollback_ready=True,
        )
        self.assertEqual(preview.authority_level, L3_HIGH_IMPACT)

        weak = ExecutionApproval.issue(
            command=command,
            target=preview.target,
            authority_level=preview.authority_level,
            now=1000.0,
        )
        denied = await executor.execute(
            command,
            context=(
                "Kali VM laboratório autorizado; alvo destrutivo exato "
                "/tmp/luna-proof"
            ),
            operator_requested_execution=True,
            scope_confirmed=True,
            rollback_ready=True,
            approval=weak,
            now=1001.0,
        )
        self.assertEqual(denied.status, "denied")

        strong = ExecutionApproval.issue(
            command=command,
            target=preview.target,
            authority_level=preview.authority_level,
            allow_destructive=True,
            now=1000.0,
        )
        allowed = await executor.execute(
            command,
            context=(
                "Kali VM laboratório autorizado; alvo destrutivo exato "
                "/tmp/luna-proof"
            ),
            operator_requested_execution=True,
            scope_confirmed=True,
            rollback_ready=True,
            approval=strong,
            now=1001.0,
        )
        self.assertEqual(allowed.status, "executed")

    async def test_shell_control_chain_is_rejected_before_runner(self) -> None:
        runner = FakeRunner()
        executor = SupervisedExecutor(
            SupervisedExecutionPolicy(enabled=True),
            runner=runner,
        )
        result = await executor.execute("cat /etc/hosts && id")
        self.assertEqual(result.status, "denied")
        self.assertTrue(
            any(reason.startswith("invalid_argv:") for reason in result.denial_reasons)
        )
        self.assertEqual(runner.calls, [])


if __name__ == "__main__":
    unittest.main()
