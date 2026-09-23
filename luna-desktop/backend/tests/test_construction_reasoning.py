import unittest

from app.construction_reasoning import (
    ConstructionModel,
    break_readiness,
    construction_coverage,
    construction_gaps,
    construction_guidance,
)


class ConstructionReasoningTests(unittest.TestCase):
    def test_complete_model_has_high_coverage(self) -> None:
        model = ConstructionModel(
            topology=0.95, interfaces=0.95, data_flow=0.95, state_model=0.95,
            trust_boundaries=0.95, invariants=0.95, dependencies=0.95, controls=0.95,
        )
        self.assertGreater(construction_coverage(model), 0.9)

    def test_critical_unknown_cannot_be_hidden_by_other_strong_dimensions(self) -> None:
        model = ConstructionModel(
            topology=0.95, interfaces=0.95, data_flow=0.95, state_model=0.95,
            trust_boundaries=0.05, invariants=0.95, dependencies=0.95, controls=0.95,
        )
        self.assertLess(construction_coverage(model), 0.75)
        self.assertEqual(construction_gaps(model)[0], "trust_boundaries")

    def test_mechanism_linkage_and_construction_raise_break_readiness(self) -> None:
        grounded = break_readiness(
            construction=0.92, evidence=0.88, mechanism_linkage=0.94,
            discriminative_power=0.90, reversibility=0.95, safety=0.95,
            uncertainty=0.15, noise=0.10,
        )
        speculative = break_readiness(
            construction=0.25, evidence=0.45, mechanism_linkage=0.20,
            discriminative_power=0.70, reversibility=0.95, safety=0.95,
            uncertainty=0.75, noise=0.55,
        )
        self.assertGreater(grounded, speculative)

    def test_security_context_activates_build_to_break_guidance(self) -> None:
        guidance = construction_guidance(
            "CTF autorizado: preciso auditar uma API e entender a arquitetura antes do teste.",
        )
        self.assertIn("BUILD-TO-BREAK", guidance)
        self.assertIn("TRUST BOUNDARIES", guidance)
        self.assertIn("INVARIANTS", guidance)
        self.assertIn("instead of guessing an exploit", guidance)

    def test_irrelevant_greeting_does_not_inject_structural_framework(self) -> None:
        self.assertEqual(construction_guidance("Olá, bom dia!"), "")


if __name__ == "__main__":
    unittest.main()
