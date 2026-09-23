"""Construction-first reasoning for cyber analysis: build the model before breaking it.

The operator still executes every action. This module gives Luna a compact
mathematical representation of how well a system is structurally understood
before an attack/audit hypothesis is promoted.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass


def _clip(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


@dataclass(frozen=True)
class ConstructionModel:
    topology: float
    interfaces: float
    data_flow: float
    state_model: float
    trust_boundaries: float
    invariants: float
    dependencies: float
    controls: float

    def to_dict(self) -> dict:
        return asdict(self)


_COVERAGE_WEIGHTS = {
    "topology": 0.90,
    "interfaces": 1.20,
    "data_flow": 1.25,
    "state_model": 1.15,
    "trust_boundaries": 1.40,
    "invariants": 1.50,
    "dependencies": 0.85,
    "controls": 1.20,
}


def construction_coverage(model: ConstructionModel) -> float:
    """Weighted geometric coverage in [0, 1].

    K = exp(sum(w_i * ln(max(x_i, eps))) / sum(w_i))

    A geometric mean is deliberate: one nearly-unknown critical dimension
    cannot be hidden by strong scores elsewhere.
    """
    eps = 1e-6
    values = model.to_dict()
    numerator = sum(
        weight * math.log(max(_clip(values[name]), eps))
        for name, weight in _COVERAGE_WEIGHTS.items()
    )
    denominator = sum(_COVERAGE_WEIGHTS.values())
    return round(math.exp(numerator / denominator), 6)


def construction_gaps(model: ConstructionModel) -> tuple[str, ...]:
    """Rank missing structural knowledge by weighted deficit."""
    values = model.to_dict()
    ranked = sorted(
        values,
        key=lambda name: (
            -_COVERAGE_WEIGHTS[name] * (1.0 - _clip(values[name])),
            name,
        ),
    )
    return tuple(ranked)


def break_readiness(
    *,
    construction: float,
    evidence: float,
    mechanism_linkage: float,
    discriminative_power: float,
    reversibility: float,
    safety: float,
    uncertainty: float,
    noise: float,
) -> float:
    """Readiness for the next audit/attack test.

    R = K^1.60 * E^1.35 * M^1.45 * D^1.20 * V^1.00 * S^1.10
        * exp(-(1.10*U + 0.75*N))

    K=construction coverage, E=evidence, M=mechanism linkage, D=ability to
    discriminate hypotheses, V=reversibility, S=safety, U=uncertainty, N=noise.
    """
    k = _clip(construction)
    e = _clip(evidence)
    m = _clip(mechanism_linkage)
    d = _clip(discriminative_power)
    v = _clip(reversibility)
    s = _clip(safety)
    u = _clip(uncertainty)
    n = _clip(noise)
    value = (
        k ** 1.60
        * e ** 1.35
        * m ** 1.45
        * d ** 1.20
        * v ** 1.00
        * s ** 1.10
        * math.exp(-(1.10 * u + 0.75 * n))
    )
    return round(value, 6)


def construction_guidance(context: str) -> str:
    """Inject a compact build-before-break discipline only for technical work."""
    normalized = context.casefold()
    markers = (
        "auditoria", "audit", "pentest", "ctf", "ataque", "attack", "exploit",
        "reverse", "revers", "malware", "ransomware", "web", "api", "rede",
        "network", "linux", "windows", "solana", "blockchain", "smart contract",
        "vulnerab", "segurança", "security",
    )
    if not any(marker in normalized for marker in markers):
        return ""

    return (
        "BUILD-TO-BREAK: reconstruct the minimum viable construction model before promoting "
        "a break/audit hypothesis: COMPONENTS/TOPOLOGY -> INTERFACES -> DATA/CONTROL FLOW -> "
        "STATE -> TRUST BOUNDARIES -> INVARIANTS -> DEPENDENCIES/CONTROLS. Map every proposed "
        "test to a concrete mechanism and the invariant it could violate. If structural coverage "
        "is weak, the next action must gather the highest-weight missing structural fact instead "
        "of guessing an exploit. Black-box inference is allowed only when labeled as inference "
        "and updated from operator evidence."
    )
