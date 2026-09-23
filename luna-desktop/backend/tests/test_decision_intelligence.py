import unittest

from app.decision_intelligence import (
    DecisionCandidate,
    binary_entropy,
    decision_guidance,
    evidence_confidence,
    rank_candidates,
    score_candidate,
)


class DecisionIntelligenceTests(unittest.TestCase):
    def test_safe_discriminator_beats_noisy_aggressive_action(self) -> None:
        discriminator = DecisionCandidate(
            name="safe_discriminator",
            evidence_support=0.82,
            information_gain=0.91,
            discriminative_power=0.94,
            scope_fit=0.98,
            reversibility=0.98,
            safety=0.97,
            cost=0.18,
            noise=0.12,
            novelty=0.72,
            downstream_leverage=0.91,
        )
        noisy = DecisionCandidate(
            name="noisy_aggressive",
            evidence_support=0.46,
            information_gain=0.62,
            discriminative_power=0.40,
            scope_fit=0.90,
            reversibility=0.35,
            safety=0.42,
            cost=0.78,
            noise=0.86,
            novelty=0.88,
            downstream_leverage=0.55,
        )
        ranked = rank_candidates((noisy, discriminator))
        self.assertEqual(ranked[0].name, "safe_discriminator")
        self.assertGreater(ranked[0].utility, ranked[1].utility)

    def test_structurally_grounded_candidate_beats_speculative_candidate(self) -> None:
        grounded = DecisionCandidate(
            name="grounded", evidence_support=0.75, information_gain=0.82,
            discriminative_power=0.86, scope_fit=0.95, reversibility=0.95,
            safety=0.95, cost=0.20, noise=0.15, novelty=0.70,
            downstream_leverage=0.90, construction_coverage=0.92,
            mechanism_linkage=0.94,
        )
        speculative = DecisionCandidate(
            name="speculative", evidence_support=0.75, information_gain=0.82,
            discriminative_power=0.86, scope_fit=0.95, reversibility=0.95,
            safety=0.95, cost=0.20, noise=0.15, novelty=0.70,
            downstream_leverage=0.90, construction_coverage=0.25,
            mechanism_linkage=0.20,
        )
        ranked = rank_candidates((speculative, grounded))
        self.assertEqual(ranked[0].name, "grounded")
        self.assertGreater(ranked[0].utility, ranked[1].utility)
    def test_weak_evidence_reduces_confidence_even_if_information_gain_is_high(self) -> None:
        candidate = DecisionCandidate(
            name="uncertain_probe",
            evidence_support=0.15,
            information_gain=0.95,
            discriminative_power=0.82,
            scope_fit=0.90,
            reversibility=0.95,
            safety=0.95,
            cost=0.15,
            noise=0.10,
            novelty=0.85,
            downstream_leverage=0.85,
        )
        score = score_candidate(candidate)
        self.assertLess(score.confidence, 0.6)
        self.assertGreater(score.uncertainty, 0.8)

    def test_weak_construction_lowers_confidence_even_with_same_evidence(self) -> None:
        strong = DecisionCandidate(
            name="strong-model", evidence_support=0.85, information_gain=0.80,
            discriminative_power=0.85, scope_fit=0.95, reversibility=0.95,
            safety=0.95, cost=0.15, noise=0.10, novelty=0.65,
            downstream_leverage=0.85, construction_coverage=0.92,
            mechanism_linkage=0.94,
        )
        weak = DecisionCandidate(
            name="weak-model", evidence_support=0.85, information_gain=0.80,
            discriminative_power=0.85, scope_fit=0.95, reversibility=0.95,
            safety=0.95, cost=0.15, noise=0.10, novelty=0.65,
            downstream_leverage=0.85, construction_coverage=0.20,
            mechanism_linkage=0.25,
        )
        self.assertGreater(score_candidate(strong).confidence, score_candidate(weak).confidence)

    def test_contradiction_penalty_reduces_claim_confidence(self) -> None:
        clean = evidence_confidence(
            direct_observation=0.95,
            reproducibility=0.90,
            source_independence=0.85,
            contradiction_penalty=0.0,
        )
        contradicted = evidence_confidence(
            direct_observation=0.95,
            reproducibility=0.90,
            source_independence=0.85,
            contradiction_penalty=0.70,
        )
        self.assertGreater(clean, contradicted)

    def test_binary_entropy_peaks_near_half_confidence(self) -> None:
        self.assertGreater(binary_entropy(0.5), binary_entropy(0.95))
        self.assertGreater(binary_entropy(0.5), binary_entropy(0.05))

    def test_investigative_context_activates_decision_guidance(self) -> None:
        guidance = decision_guidance(
            "CTF autorizado: analise a evidência e escolha o próximo teste de maior valor.",
        )
        self.assertIn("FACTS, HYPOTHESES, UNKNOWNs and ACTIONS", guidance)
        self.assertIn("highest useful information per unit risk/cost", guidance)
        self.assertIn("Never convert an inference into a fact", guidance)

    def test_greeting_does_not_inject_decision_framework(self) -> None:
        self.assertEqual(decision_guidance("Olá, bom dia!"), "")


if __name__ == "__main__":
    unittest.main()
