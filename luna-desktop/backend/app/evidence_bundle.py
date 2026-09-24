"""Report-grade evidence bundles for supervised exploit validation.

This module is deliberately execution-agnostic. It turns raw artifacts produced by
operator-supervised validation into integrity-attested evidence records and computes
reproducibility statistics without asking the LLM to do arithmetic.

The bundle can carry logs, request/response transcripts, debugger output, PCAP bytes,
transactions and screenshots. Exact bytes are preserved and hashed.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable

from .quantitative_reasoning import (
    wilson_score_interval as _wilson_score_interval,
    zero_failure_probability_upper_bound as _zero_failure_probability_upper_bound,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class EvidenceArtifact:
    kind: str
    media_type: str
    source: str
    byte_length: int
    sha256: str
    observed_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReproducibilityMetrics:
    successes: int
    trials: int
    success_rate: float
    wilson_low: float
    wilson_high: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProofEvidenceBundle:
    target: str
    success_predicate: str
    command_sha256: str | None
    artifacts: tuple[EvidenceArtifact, ...]
    reproducibility: ReproducibilityMetrics | None

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "success_predicate": self.success_predicate,
            "command_sha256": self.command_sha256,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "reproducibility": (
                self.reproducibility.to_dict() if self.reproducibility else None
            ),
        }


def build_evidence_artifact(
    *,
    kind: str,
    data: bytes,
    media_type: str = "application/octet-stream",
    source: str = "operator-supervised-validation",
    observed_at: str | None = None,
) -> EvidenceArtifact:
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("evidence artifact data must be bytes")
    raw = bytes(data)
    if not raw:
        raise ValueError("evidence artifact must not be empty")
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError("single evidence artifact exceeds 64 MiB")
    clean_kind = str(kind or "").strip()
    clean_source = str(source or "").strip()
    clean_media = str(media_type or "").strip()
    if not clean_kind or len(clean_kind) > 80:
        raise ValueError("invalid evidence artifact kind")
    if not clean_source or len(clean_source) > 300:
        raise ValueError("invalid evidence source")
    if not clean_media or len(clean_media) > 120:
        raise ValueError("invalid media type")
    return EvidenceArtifact(
        kind=clean_kind,
        media_type=clean_media,
        source=clean_source,
        byte_length=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        observed_at=str(observed_at or _now()),
    )


def wilson_interval(
    successes: int,
    trials: int,
    *,
    z: float = 1.959963984540054,
) -> ReproducibilityMetrics:
    """Report wrapper over the shared deterministic quantitative math."""
    low, high = _wilson_score_interval(successes, trials, z=z)
    return ReproducibilityMetrics(
        successes=successes,
        trials=trials,
        success_rate=round(successes / trials, 10),
        wilson_low=low,
        wilson_high=high,
    )


def zero_failure_probability_upper_bound(
    trials: int,
    *,
    alpha: float = 0.05,
) -> float:
    return _zero_failure_probability_upper_bound(trials, alpha=alpha)

def build_proof_evidence_bundle(
    *,
    target: str,
    success_predicate: str,
    artifacts: Iterable[EvidenceArtifact],
    exact_command: str | None = None,
    successes: int | None = None,
    trials: int | None = None,
) -> ProofEvidenceBundle:
    clean_target = str(target or "").strip()
    clean_predicate = str(success_predicate or "").strip()
    if not clean_target:
        raise ValueError("target is required")
    if not clean_predicate:
        raise ValueError("success predicate is required")

    artifact_tuple = tuple(artifacts)
    if not artifact_tuple:
        raise ValueError("at least one evidence artifact is required")
    total_bytes = sum(item.byte_length for item in artifact_tuple)
    if total_bytes > 256 * 1024 * 1024:
        raise ValueError("evidence bundle exceeds 256 MiB")

    command_sha256 = None
    if exact_command is not None:
        command_sha256 = hashlib.sha256(
            exact_command.encode("utf-8")
        ).hexdigest()

    metrics = None
    if successes is not None or trials is not None:
        if successes is None or trials is None:
            raise ValueError("successes and trials must be provided together")
        metrics = wilson_interval(successes, trials)

    return ProofEvidenceBundle(
        target=clean_target,
        success_predicate=clean_predicate,
        command_sha256=command_sha256,
        artifacts=artifact_tuple,
        reproducibility=metrics,
    )


def evidence_bundle_guidance() -> str:
    return (
        "EVIDENCE BUNDLE: preserve exact raw artifacts and SHA-256 each item; bind target "
        "and success predicate before validation; hash the exact command/PoC invocation; "
        "capture logs/screenshots/transcripts needed for the report. For repeated trials, "
        "record successes/trials and compute the Wilson interval deterministically; after zero "
        "observed failures, use the exact one-sided binomial upper bound when relevant. Do not "
        "present a success fraction as certainty outside the tested environment."
    )
