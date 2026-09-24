import unittest

from app.evidence_bundle import (
    wilson_interval as evidence_wilson_interval,
    zero_failure_probability_upper_bound as evidence_zero_failure_upper_bound,
)
from app.exploit_proof import (
    wilson_score_interval as exploit_wilson_interval,
    zero_failure_upper_bound as exploit_zero_failure_upper_bound,
)
from app.quantitative_reasoning import (
    wilson_score_interval,
    zero_failure_probability_upper_bound,
)


class RepeatabilityMathAuthorityTests(unittest.TestCase):
    def test_wilson_interval_has_one_deterministic_authority(self) -> None:
        central = wilson_score_interval(8, 10)
        evidence = evidence_wilson_interval(8, 10)
        exploit = exploit_wilson_interval(8, 10)
        self.assertEqual((evidence.wilson_low, evidence.wilson_high), central)
        self.assertEqual(exploit, central)
        self.assertEqual(evidence.success_rate, 0.8)

    def test_zero_failure_bound_has_one_deterministic_authority(self) -> None:
        central = zero_failure_probability_upper_bound(59, alpha=0.05)
        self.assertEqual(
            evidence_zero_failure_upper_bound(59, alpha=0.05),
            central,
        )
        self.assertEqual(
            exploit_zero_failure_upper_bound(59, alpha=0.05),
            central,
        )

    def test_statistical_domains_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            wilson_score_interval(True, 10)
        with self.assertRaises(ValueError):
            wilson_score_interval(11, 10)
        with self.assertRaises(ValueError):
            zero_failure_probability_upper_bound(10, alpha=0.0)


if __name__ == "__main__":
    unittest.main()
