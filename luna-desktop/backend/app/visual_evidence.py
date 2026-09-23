"""Visual evidence manifest and reasoning contract for screenshots/images.

The transport path supports image content. This module makes screenshots first-class
evidence: exact bytes are hashed, metadata is bounded, and the model is told to
separate visible observations from interpretation. Runtime must additionally verify
that the selected local model reports a real vision capability before semantic reading.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Iterable


_ALLOWED_MIME = frozenset({"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"})
MAX_VISUAL_EVIDENCE_ITEMS = 8
MAX_VISUAL_EVIDENCE_BYTES = 12 * 1024 * 1024


@dataclass(frozen=True)
class VisualEvidenceArtifact:
    index: int
    mime: str
    byte_length: int
    sha256: str

    def to_dict(self) -> dict:
        return asdict(self)


def build_visual_evidence_manifest(
    images: Iterable[dict[str, str]] | None,
) -> tuple[VisualEvidenceArtifact, ...]:
    if not images:
        return ()

    artifacts: list[VisualEvidenceArtifact] = []
    total_bytes = 0
    for index, image in enumerate(images, start=1):
        if index > MAX_VISUAL_EVIDENCE_ITEMS:
            raise ValueError("too many visual evidence items")
        mime = str(image.get("mime", "image/png")).casefold()
        if mime not in _ALLOWED_MIME:
            raise ValueError(f"unsupported visual evidence mime: {mime}")
        encoded = image.get("data")
        if not encoded:
            raise ValueError("visual evidence item missing base64 data")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError("invalid visual evidence base64") from exc
        total_bytes += len(raw)
        if total_bytes > MAX_VISUAL_EVIDENCE_BYTES:
            raise ValueError("visual evidence exceeds byte limit")
        artifacts.append(
            VisualEvidenceArtifact(
                index=index,
                mime=mime,
                byte_length=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
            )
        )
    return tuple(artifacts)


def visual_evidence_guidance(
    manifest: tuple[VisualEvidenceArtifact, ...],
    *,
    max_chars: int = 1_300,
) -> str:
    if not manifest:
        return ""
    entries = ", ".join(
        f"image#{item.index}:{item.mime}:{item.byte_length}B:sha256={item.sha256}"
        for item in manifest
    )
    guidance = (
        "VISUAL EVIDENCE: inspect the attached pixels as evidence, not decoration. "
        "Separate OBSERVED visual facts (exact visible text, UI state, codes, values, paths, "
        "controls, timestamps) from INFERENCE and HYPOTHESIS. Never invent obscured/cropped text. "
        "When relevant, identify the screen region or control that supports the observation and "
        "preserve exact strings for later report reproduction. If image quality is insufficient, "
        "state exactly what cannot be resolved. Evidence manifest: "
        + entries
    )
    return guidance[:max_chars]
