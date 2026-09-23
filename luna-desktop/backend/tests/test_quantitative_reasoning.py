import math
import unittest

from app.quantitative_reasoning import (
    birthday_collision_probability,
    conservation_residual,
    integer_bounds,
    integer_margin,
    max_unsigned_input_before_mul_overflow,
    floor_rounding_loss_numerator,
    mul_div_floor,
    quantitative_guidance,
    scale_decimal_exact,
    select_quantitative_profile,
    shannon_capacity_bps,
    shannon_entropy_bits,
    wavelength_m,
)


class QuantitativeReasoningTests(unittest.TestCase):
    def test_exact_base_unit_scaling_avoids_binary_float(self) -> None:
        self.assertEqual(scale_decimal_exact("1.234567", 6), 1_234_567)
        with self.assertRaises(ValueError):
            scale_decimal_exact("1.2345678", 6)

    def test_integer_bounds_and_margin_cover_signed_unsigned(self) -> None:
        self.assertEqual(integer_bounds(8, False), (0, 255))
        self.assertEqual(integer_bounds(8, True), (-128, 127))
        self.assertEqual(integer_margin(250, 8, False), 5)
        self.assertLess(integer_margin(256, 8, False), 0)

    def test_u64_fee_multiplier_threshold_is_exact(self) -> None:
        threshold = max_unsigned_input_before_mul_overflow(64, 125)
        self.assertEqual(threshold, 147_573_952_589_676_412)
        self.assertLessEqual(threshold * 125, (1 << 64) - 1)
        self.assertGreater((threshold + 1) * 125, (1 << 64) - 1)

    def test_floor_rounding_loss_is_bounded_by_one_base_unit(self) -> None:
        remainder = floor_rounding_loss_numerator(79, 125, 10_000)
        self.assertEqual(remainder, 9_875)
        self.assertLess(remainder, 10_000)

    def test_mul_div_exposes_discarded_remainder(self) -> None:
        quotient, remainder = mul_div_floor(100, 1, 3)
        self.assertEqual(quotient, 33)
        self.assertEqual(remainder, 1)

    def test_conservation_residual_detects_value_creation_or_loss(self) -> None:
        self.assertEqual(conservation_residual([1000], [700, 200, 100]), 0)
        self.assertEqual(conservation_residual([1000], [700, 200, 99]), 1)

    def test_entropy_and_collision_math_are_calibrated(self) -> None:
        self.assertAlmostEqual(shannon_entropy_bits([0.5, 0.5]), 1.0)
        low = birthday_collision_probability(10, 32)
        high = birthday_collision_probability(100_000, 32)
        self.assertGreater(high, low)

    def test_physics_helpers_keep_units_explicit(self) -> None:
        wavelength = wavelength_m(2.4e9)
        self.assertTrue(0.12 < wavelength < 0.13)
        capacity = shannon_capacity_bps(20e6, 10.0)
        self.assertGreater(capacity, 20e6)
        self.assertTrue(math.isfinite(capacity))

    def test_anchor_context_selects_blockchain_financial_math(self) -> None:
        profile = select_quantitative_profile(
            "Auditoria Anchor Solana: USDC SPL, fee, u64, rounding e randomness VRF."
        )
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "blockchain_financial")
        guidance = quantitative_guidance(
            "Auditoria Anchor Solana: USDC SPL, fee, u64, rounding e randomness VRF."
        )
        self.assertIn("base-unit", guidance)
        self.assertIn("rounding", guidance)
        self.assertIn("invariant", guidance)

    def test_rf_context_selects_physics_profile(self) -> None:
        profile = select_quantitative_profile("Wi-Fi RF com RSSI, SNR e frequência de 2.4 GHz.")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "network_signal_physics")

    def test_irrelevant_greeting_does_not_inject_quantitative_context(self) -> None:
        self.assertEqual(quantitative_guidance("Olá, bom dia!"), "")


if __name__ == "__main__":
    unittest.main()
