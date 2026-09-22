"""Attach deterministic quality/integrity metadata to Luna response_meta events."""

from __future__ import annotations

import json
from typing import Any

from .reasoning_quality import score_response_quality
from .reasoning_runtime_patch_v8 import command_attestations


def _quality_band(score: float) -> str:
    if score >= 0.85:
        return "green"
    if score >= 0.62:
        return "amber"
    return "red"


def install_response_attestation(engine_cls: type) -> None:
    """Wrap LunaEngine.stream_agent once without changing the core engine file."""
    if getattr(engine_cls, "_response_attestation_installed", False):
        return

    original = engine_cls.stream_agent

    async def wrapped(self: Any, message: str, *args: Any, **kwargs: Any):
        full_text = ""
        async for raw_event in original(self, message, *args, **kwargs):
            output = raw_event
            try:
                event = json.loads(raw_event)
            except (TypeError, json.JSONDecodeError):
                yield output
                continue

            if event.get("type") == "text_chunk":
                full_text += str(event.get("text", ""))

            if event.get("type") == "response_meta":
                reasons = event.get("validation_reasons") or ()
                score = score_response_quality(message, full_text, reasons)
                attestations = command_attestations(message, full_text)

                # Do not duplicate command text (which may contain credentials) in
                # metadata.  The UI hashes the displayed code and compares it with
                # this digest instead.
                safe_attestations = []
                for item in attestations:
                    safe = {key: value for key, value in item.items() if key != "command"}
                    safe_attestations.append(safe)

                event.update({
                    "quality_score": score.total,
                    "quality_raw": score.raw_geometric,
                    "quality_band": _quality_band(score.total),
                    "quality_components": score.components,
                    "target_verified": (
                        all(item.get("target_verified", False) for item in safe_attestations)
                        if safe_attestations else None
                    ),
                    "command_attestations": safe_attestations,
                })
                output = json.dumps(event, ensure_ascii=False)

            yield output

    engine_cls.stream_agent = wrapped
    engine_cls._response_attestation_installed = True
