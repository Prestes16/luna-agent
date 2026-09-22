"""Attach deterministic quality/integrity metadata to Luna response_meta events.

V9 buffers model text until validation finishes, applies only target-preserving
mechanical command repairs, then emits the exact operator-visible text together
with a SHA-256 attestation for each executable command.
"""

from __future__ import annotations

import json
from typing import Any

from .operational_transform import transform_response_commands
from .reasoning_pipeline import redact_sensitive_text
from .reasoning_quality import score_response_quality
from .reasoning_runtime_patch_v8 import command_attestations


def _quality_band(score: float) -> str:
    if score >= 0.85:
        return "green"
    if score >= 0.62:
        return "amber"
    return "red"


def _session_id(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    value = kwargs.get("session_id")
    if value is None and args:
        value = args[0]
    return str(value or "default")


def _replace_latest_assistant_history(engine: Any, session_id: str, content: str) -> None:
    history = engine.histories.get(session_id) or []
    for item in reversed(history):
        if item.get("role") == "assistant" and isinstance(item.get("content"), str):
            item["content"] = redact_sensitive_text(content)
            return


def install_response_attestation(engine_cls: type) -> None:
    """Wrap LunaEngine.stream_agent once without changing the core engine file."""
    if getattr(engine_cls, "_response_attestation_installed", False):
        return

    original = engine_cls.stream_agent

    async def wrapped(self: Any, message: str, *args: Any, **kwargs: Any):
        full_text = ""
        emitted_final_text = False
        sid = _session_id(args, kwargs)

        async for raw_event in original(self, message, *args, **kwargs):
            try:
                event = json.loads(raw_event)
            except (TypeError, json.JSONDecodeError):
                yield raw_event
                continue

            event_type = event.get("type")

            # The core engine already buffers generation until validation.  V9
            # additionally withholds those text chunks for a final deterministic
            # command normalization pass before anything reaches the operator.
            if event_type == "text_chunk":
                full_text += str(event.get("text", ""))
                continue

            if event_type == "response_meta":
                transformed, mutations = transform_response_commands(message, full_text)
                visible_text = transformed or full_text
                reasons = event.get("validation_reasons") or ()
                score = score_response_quality(message, visible_text, reasons)
                attestations = command_attestations(message, visible_text)

                safe_attestations = []
                for item in attestations:
                    safe = {key: value for key, value in item.items() if key != "command"}
                    safe_attestations.append(safe)

                if visible_text:
                    yield json.dumps({"type": "text_chunk", "text": visible_text}, ensure_ascii=False)
                    emitted_final_text = True

                if visible_text != full_text:
                    _replace_latest_assistant_history(self, sid, visible_text)

                safe_mutations = [mutation.to_safe_dict() for mutation in mutations]
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
                    "operational_transform_applied": bool(mutations),
                    "operational_mutations": safe_mutations,
                })

                # Keep backend diagnostics in sync with what the operator saw.
                turn_meta = self.turn_metadata.get(sid)
                if isinstance(turn_meta, dict):
                    turn_meta.update({
                        "quality_score": score.total,
                        "quality_band": _quality_band(score.total),
                        "target_verified": event.get("target_verified"),
                        "operational_transform_applied": bool(mutations),
                    })

                yield json.dumps(event, ensure_ascii=False)
                continue

            yield raw_event

        # Defensive fallback for providers/paths that ended without response_meta.
        if full_text and not emitted_final_text:
            yield json.dumps({"type": "text_chunk", "text": full_text}, ensure_ascii=False)

    engine_cls.stream_agent = wrapped
    engine_cls._response_attestation_installed = True
