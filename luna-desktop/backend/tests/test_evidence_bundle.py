import hashlib
import unittest

from app.evidence_bundle import (
    build_evidence_artifact,
    build_proof_evidence_bundle,
    evidence_bundle_guidance,
    wilson_interval,
    zero_failure_probability_upper_bound,
)


class EvidenceBundleTests(unittest.TestCase):
    def test_exact_artifact_bytes_are_hashed(self) -> None:
        raw = b"HTTP/1.1 200 OK\r\nX-Proof: yes\r\n"
        item = build_evidence_artifact(
            kind="http-response",
            data=raw,
            media_type="message/http",
            source="curl",
        )
        self.assertEqual(item.byte_length, len(raw))
        self.assertEqual(item.sha256, hashlib.sha256(raw).hexdigest())

    def test_command_hash_binds_report_to_exact_invocation(self) -> None:
        item = build_evidence_artifact(kind="stdout", data=b"uid=0(root)")
        command = "id"
        bundle = build_proof_evidence_bundle(
            target="lab-host",
            success_predicate="effective uid is 0",
            artifacts=[item],
            exact_command=command,
        )
        self.assertEqual(
            bundle.command_sha256,
            hashlib.sha256(command.encode("utf-8")).hexdigest(),
        )

    def test_wilson_interval_is_bounded_and_not_equal_to_point_estimate(self) -> None:
        metrics = wilson_interval(8, 10)
        self.assertEqual(metrics.success_rate, 0.8)
        self.assertGreaterEqual(metrics.wilson_low, 0.0)
        self.assertLessEqual(metrics.wilson_high, 1.0)
        self.assertLess(metrics.wilson_low, metrics.success_rate)
        self.assertGreater(metrics.wilson_high, metrics.success_rate)

    def test_wilson_interval_handles_zero_successes(self) -> None:
        metrics = wilson_interval(0, 5)
        self.assertEqual(metrics.success_rate, 0.0)
        self.assertEqual(metrics.wilson_low, 0.0)
        self.assertGreater(metrics.wilson_high, 0.0)

    def test_zero_failure_upper_bound_is_exact_and_monotone(self) -> None:
        one = zero_failure_probability_upper_bound(1, alpha=0.05)
        ten = zero_failure_probability_upper_bound(10, alpha=0.05)
        fifty_nine = zero_failure_probability_upper_bound(59, alpha=0.05)
        self.assertAlmostEqual(one, 0.95, places=10)
        self.assertGreater(one, ten)
        self.assertGreater(ten, fifty_nine)
        self.assertGreater(fifty_nine, 0.0)
        self.assertLess(fifty_nine, 0.06)

    def test_zero_failure_upper_bound_rejects_invalid_domain(self) -> None:
        with self.assertRaises(ValueError):
            zero_failure_probability_upper_bound(0)
        with self.assertRaises(ValueError):
            zero_failure_probability_upper_bound(5, alpha=1.0)

    def test_bundle_requires_complete_reproducibility_pair(self) -> None:
        item = build_evidence_artifact(kind="log", data=b"proof")
        with self.assertRaises(ValueError):
            build_proof_evidence_bundle(
                target="target",
                success_predicate="predicate",
                artifacts=[item],
                successes=1,
            )

    def test_guidance_requires_exact_evidence_and_uncertainty(self) -> None:
        guidance = evidence_bundle_guidance()
        self.assertIn("SHA-256", guidance)
        self.assertIn("Wilson interval", guidance)
        self.assertIn("one-sided binomial upper bound", guidance)
        self.assertIn("tested environment", guidance)


if __name__ == "__main__":
    unittest.main()
