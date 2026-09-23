import unittest

from app.construction_reasoning import (
    ConstructionModel,
    MechanismChain,
    break_readiness,
    construction_coverage,
    construction_gaps,
    construction_guidance,
    mechanism_chain_score,
    select_construction_profile,
    structural_discovery_priority,
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

    def test_web_api_profile_focuses_auth_state_and_server_boundary(self) -> None:
        profile = select_construction_profile(
            "Auditoria web API REST com JWT, cookie e autorização backend."
        )
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "web_api")
        joined = " ".join(profile.structural_questions)
        self.assertIn("authorization", joined)
        self.assertIn("state transition", joined)

    def test_blockchain_profile_focuses_authority_and_asset_flow(self) -> None:
        profile = select_construction_profile(
            "Auditoria Solana Anchor com PDA, SPL e instruções on-chain."
        )
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "blockchain_web3")
        joined = " ".join(profile.structural_questions)
        self.assertIn("authority", joined)
        self.assertIn("asset flow", joined)

    def test_mechanism_chain_penalizes_missing_invariant(self) -> None:
        complete = MechanismChain(
            component=0.95, interface=0.95, trust_boundary=0.95,
            state_transition=0.95, invariant=0.95, evidence=0.95,
            expected_observation=0.95,
        )
        weak = MechanismChain(
            component=0.95, interface=0.95, trust_boundary=0.95,
            state_transition=0.95, invariant=0.05, evidence=0.95,
            expected_observation=0.95,
        )
        self.assertGreater(mechanism_chain_score(complete), mechanism_chain_score(weak))

    def test_structural_discovery_prioritizes_weighted_critical_gap(self) -> None:
        model = ConstructionModel(
            topology=0.90, interfaces=0.90, data_flow=0.90, state_model=0.90,
            trust_boundaries=0.90, invariants=0.10, dependencies=0.20, controls=0.90,
        )
        ranked = structural_discovery_priority(model)
        self.assertEqual(ranked[0][0], "invariants")
        self.assertGreater(ranked[0][1], ranked[1][1])

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
