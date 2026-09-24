import base64
import hashlib
import unittest

from app.evidence_bundle import build_proof_evidence_bundle
from app.execution_intent import APPROVAL_REQUIRED, L3_HIGH_IMPACT
from app.exploit_proof import build_exploit_proof_contract
from app.supervised_executor import (
    ExecutionApproval,
    RunnerResult,
    SupervisedExecutionPolicy,
    SupervisedExecutor,
)
from app.visual_evidence import build_visual_evidence_manifest


class _ProofRunner:
    async def __call__(self, argv, timeout_seconds, max_output_bytes):
        return RunnerResult(
            exit_code=0,
            stdout=b"PROOF_OK target=10.10.10.5\n",
            stderr=b"",
        )


class SupervisedCopilotIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_exploit_proof_execution_and_evidence_chain(self) -> None:
        contract = build_exploit_proof_contract(
            "Validar achado HTTP RCE com PoC reproduzível para relatório."
        )
        self.assertIsNotNone(contract)
        self.assertEqual(contract.profile, "web_api")

        command = "python3 poc.py --target 10.10.10.5"
        executor = SupervisedExecutor(
            SupervisedExecutionPolicy(enabled=True, allow_l3=True),
            runner=_ProofRunner(),
            backend_name="kali-ssh-test",
        )
        preview = executor.preview(
            command,
            context="CTF autorizado em Kali; PoC para validar achado RCE HTTP",
            operator_requested_execution=True,
            scope_confirmed=True,
            rollback_ready=True,
            verification_ready=True,
            scope_target="10.10.10.5",
        )
        self.assertEqual(preview.authority_level, L3_HIGH_IMPACT)
        self.assertEqual(preview.authority, APPROVAL_REQUIRED)

        approval = ExecutionApproval.issue(
            command=command,
            target=preview.target,
            authority_level=preview.authority_level,
            ttl_seconds=120,
        )
        result = await executor.execute(
            command,
            context="CTF autorizado em Kali; PoC para validar achado RCE HTTP",
            operator_requested_execution=True,
            scope_confirmed=True,
            rollback_ready=True,
            verification_ready=True,
            scope_target="10.10.10.5",
            approval=approval,
        )
        self.assertEqual(result.status, "executed")
        self.assertEqual(result.backend, "kali-ssh-test")
        self.assertEqual(result.stdout, "PROOF_OK target=10.10.10.5\n")
        self.assertTrue(result.evidence)

        bundle = build_proof_evidence_bundle(
            target="10.10.10.5",
            success_predicate="raw output contains PROOF_OK for the bound target",
            artifacts=result.evidence,
            exact_command=command,
            successes=3,
            trials=3,
        )
        self.assertEqual(
            bundle.command_sha256,
            hashlib.sha256(command.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(bundle.reproducibility.success_rate, 1.0)
        self.assertLess(bundle.reproducibility.wilson_low, 1.0)

    def test_visual_report_artifact_hash_is_exact(self) -> None:
        raw = b"exact-screenshot-evidence"
        manifest = build_visual_evidence_manifest([
            {
                "data": base64.b64encode(raw).decode("ascii"),
                "mime": "image/png",
            }
        ])
        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest[0].byte_length, len(raw))
        self.assertEqual(
            manifest[0].sha256,
            hashlib.sha256(raw).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
