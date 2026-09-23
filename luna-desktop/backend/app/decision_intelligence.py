"""Decision-intelligence layer for high-uncertainty cyber investigations.

This module does not execute actions. It gives Luna a mathematically explicit
way to prefer evidence-rich, discriminative, reversible next steps over noisy
or speculative ones.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class DecisionCandidate:
    name: str
    evidence_support: float
    information_gain: float
    discriminative_power: float
    scope_fit: float
    reversibility: float
    safety: float
    cost: float
    noise: float
    novelty: float
    downstream_leverage: float
    construction_coverage: float = 1.0
    mechanism_linkage: float = 1.0


@dataclass(frozen=True)
class DecisionScore:
    name: str
    utility: float
    confidence: float
    uncertainty: float
    positive_term: float
    penalty_term: float

    def to_dict(self) -> dict:
        return asdict(self)


def _clip(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def binary_entropy(probability: float) -> float:
    """Normalized binary entropy in [0, 1]."""
    p = min(1.0 - 1e-9, max(1e-9, probability))
    entropy = -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))
    return round(entropy, 6)


def score_candidate(candidate: DecisionCandidate) -> DecisionScore:
    """Score a candidate next action.

    Positive dimensions are combined geometrically so one weak dimension can
    pull the score down. Cost and noise are exponential penalties.

    U = E^1.25 * IG^1.55 * D^1.35 * S^1.20 * R^1.10 * H^1.15 *
        N^0.45 * L^0.90 * K^1.40 * M^1.25 * exp(-(0.80*C + 0.95*Z))

    E=evidence support, IG=expected information gain, D=discriminative power,
    S=scope fit, R=reversibility, H=safety, N=novelty, L=downstream leverage,
    K=construction coverage, M=mechanism linkage, C=cost, Z=noise.
    """
    evidence = _clip(candidate.evidence_support)
    info = _clip(candidate.information_gain)
    discriminative = _clip(candidate.discriminative_power)
    scope = _clip(candidate.scope_fit)
    reversibility = _clip(candidate.reversibility)
    safety = _clip(candidate.safety)
    cost = _clip(candidate.cost)
    noise = _clip(candidate.noise)
    novelty = _clip(candidate.novelty)
    leverage = _clip(candidate.downstream_leverage)
    construction = _clip(candidate.construction_coverage)
    mechanism = _clip(candidate.mechanism_linkage)

    positive = (
        evidence ** 1.25
        * info ** 1.55
        * discriminative ** 1.35
        * scope ** 1.20
        * reversibility ** 1.10
        * safety ** 1.15
        * max(novelty, 0.05) ** 0.45
        * max(leverage, 0.05) ** 0.90
        * max(construction, 0.05) ** 1.40
        * max(mechanism, 0.05) ** 1.25
    )
    penalty = math.exp(-(0.80 * cost + 0.95 * noise))
    utility = positive * penalty

    # Confidence is evidence-led and construction-aware. A plausible action must
    # not look highly certain when the mechanism or system model is weak.
    confidence = _clip(
        0.50 * evidence
        + 0.08 * scope
        + 0.10 * discriminative
        + 0.08 * safety
        + 0.12 * construction
        + 0.12 * mechanism
    )
    uncertainty = binary_entropy(confidence)

    return DecisionScore(
        name=candidate.name,
        utility=round(utility, 6),
        confidence=round(confidence, 6),
        uncertainty=uncertainty,
        positive_term=round(positive, 6),
        penalty_term=round(penalty, 6),
    )


def rank_candidates(candidates: Iterable[DecisionCandidate]) -> tuple[DecisionScore, ...]:
    ranked = [score_candidate(candidate) for candidate in candidates]
    ranked.sort(key=lambda item: (-item.utility, -item.confidence, item.name))
    return tuple(ranked)


def evidence_confidence(
    *,
    direct_observation: float,
    reproducibility: float,
    source_independence: float,
    contradiction_penalty: float = 0.0,
) -> float:
    """Calibrated confidence for an investigative claim."""
    direct = _clip(direct_observation)
    repeat = _clip(reproducibility)
    independence = _clip(source_independence)
    contradiction = _clip(contradiction_penalty)
    support = (
        direct ** 1.45
        * repeat ** 1.10
        * independence ** 0.95
        * math.exp(-1.40 * contradiction)
    )
    return round(_clip(support), 6)


def decision_guidance(context: str) -> str:
    normalized = context.casefold()
    markers = (
        "analise", "análise", "investig", "auditoria", "audit", "attack", "ataque",
        "exploit", "malware", "ransomware", "reverse", "ctf", "evidência", "evidencia",
        "qual o próximo", "qual o proximo", "e agora", "difícil", "dificil", "complexo",
    )
    if not any(marker in normalized for marker in markers):
        return ""

    return (
        "DECISION INTELLIGENCE: separate FACTS, HYPOTHESES, UNKNOWNs and ACTIONS. "
        "For each plausible next step, reason over evidence support, expected information gain, "
        "discriminative power between competing hypotheses, scope fit, reversibility, host safety, "
        "noise, cost, novelty and downstream leverage. Prefer the action with the highest useful "
        "information per unit risk/cost, not the most aggressive action. Construction coverage and "
        "mechanism linkage are first-class factors: understand how the relevant component is built "
        "and which invariant the test targets. When uncertainty is high, "
        "choose a discriminator that can falsify at least one important hypothesis. After the "
        "operator returns evidence, update confidence rather than defending the previous theory. "
        "Never convert an inference into a fact. Final reports must separate observed evidence, "
        "reproducible result, inference, impact, uncertainty and remediation."
    )
