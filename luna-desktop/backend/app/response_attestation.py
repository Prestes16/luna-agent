"""Attach deterministic quality/integrity metadata to Luna response_meta events.

V9 buffers model text until validation finishes, applies only target-preserving
mechanical command repairs, then emits the exact operator-visible text together
with a SHA-256 attestation for each executable command.
"""

from __future__ import annotations

import json
from typing import Any

from .command_ast import assess_nmap_strategy
from .command_execution import assess_command_execution
from .command_policy import parse_effective_command
from .execution_intent import build_execution_intent, operator_requested_execution
from .host_safety import assess_host_safety
from .kali_tool_readiness import assess_tool_readiness
from .network_privacy import privacy_intent, score_privacy_routes
from .offensive_strategy import assess_nmap_port_strategy
from .operational_transform import transform_response_commands
from .reasoning_quality import score_response_quality
from .reasoning_runtime_patch_v8 import command_attestations, extract_commands


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
            item["content"] = content
            return


def _strategy_attestations(engine: Any, session_id: str, message: str, response: str) -> list[dict]:
    scenario = engine.scenario_contexts.get(session_id)
    context_parts = [message]
    if scenario is not None:
        for attr in ("target", "current_goal", "environment"):
            value = getattr(scenario, attr, None)
            if value:
                context_parts.append(str(value))
    context = "\n".join(context_parts)

    metrics: list[dict] = []
    for command in extract_commands(response):
        ast = parse_effective_command(command)
        if not ast or ast.tool != "nmap":
            continue
        general = assess_nmap_strategy(context, ast)
        ports = assess_nmap_port_strategy(context, ast)
        metrics.append({
            "tool": "nmap",
            "intent": general.intent,
            "information_gain": general.information_gain,
            "noise": general.noise,
            "cost": general.cost,
            "utility": general.utility,
            "port_profile": ports.profile,
            "weighted_recall": ports.weighted_recall,
            "weighted_precision": ports.weighted_precision,
            "f_beta": ports.f_beta,
            "context_utility": ports.context_utility,
            "strategy_reasons": list(dict.fromkeys((*general.reasons, *ports.reasons))),
        })
    return metrics

def _privacy_attestation(engine: Any, session_id: str, message: str) -> dict | None:
    scenario = engine.scenario_contexts.get(session_id)
    context_parts = [message]
    if scenario is not None:
        for attr in ("target", "current_goal", "environment"):
            value = getattr(scenario, attr, None)
            if value:
                context_parts.append(str(value))
    context = "\n".join(context_parts)
    if not privacy_intent(context):
        return None

    ranked = score_privacy_routes(context)
    return {
        "top_profile": ranked[0].profile.name if ranked else None,
        "candidates": [
            {
                "profile": item.profile.name,
                "utility": item.utility,
                "mismatch_penalty": item.mismatch_penalty,
                "reasons": list(item.reasons),
            }
            for item in ranked[:4]
        ],
    }


def _host_safety_attestations(engine: Any, session_id: str, message: str, response: str) -> list[dict]:
    scenario = engine.scenario_contexts.get(session_id)
    context_parts = [message]
    if scenario is not None:
        for attr in ("environment", "scope", "current_goal", "target"):
            value = getattr(scenario, attr, None)
            if value:
                context_parts.append(str(value))
        context_parts.extend(str(item) for item in (getattr(scenario, "observed_facts", []) or []))
    context = "\n".join(context_parts)

    output: list[dict] = []
    for command in extract_commands(response):
        item = assess_host_safety(command, context=context).to_dict()
        output.append({key: value for key, value in item.items() if key != "command"})
    return output


def install_response_attestation(engine_cls: type) -> None:
    """Wrap LunaEngine.stream_agent once without changing the core engine file."""
    if getattr(engine_cls, "_response_attestation_installed", False):
        return

    original = engine_cls.stream_agent

    async def wrapped(self: Any, message: str, *args: Any, **kwargs: Any):
        full_text = ""
        emitted_final_text = False
        sid = _session_id(args, kwargs)
        final_visible_text: str | None = None
        history_needs_rewrite = False

        async for raw_event in original(self, message, *args, **kwargs):
            try:
                event = json.loads(raw_event)
            except (TypeError, json.JSONDecodeError):
                yield raw_event
                continue

            event_type = event.get("type")

            # The core engine already buffers generation until validation. V9
            # additionally withholds text for one deterministic normalization pass
            # before the exact operator-visible command is released.
            if event_type == "text_chunk":
                full_text += str(event.get("text", ""))
                continue

            if event_type == "response_meta":
                transformed, mutations = transform_response_commands(message, full_text)
                visible_text = transformed or full_text
                final_visible_text = visible_text
                history_needs_rewrite = visible_text != full_text

                reasons = event.get("validation_reasons") or ()
                score = score_response_quality(message, visible_text, reasons)
                attestations = command_attestations(message, visible_text)
                operator_requested = operator_requested_execution(message)
                scenario = self.scenario_contexts.get(sid)
                intent_context_parts = [message]
                if scenario is not None:
                    for attr in ("target", "current_goal", "environment", "scope"):
                        value = getattr(scenario, attr, None)
                        if value:
                            intent_context_parts.append(str(value))
                intent_context = "\n".join(intent_context_parts)
                scope_confirmed = any(
                    marker in intent_context.casefold()
                    for marker in (
                        "autorizado", "authorized", "ctf", "laboratório", "laboratorio",
                        "lab", "sandbox", "escopo confirmado", "scope confirmed",
                    )
                )
                response_commands = extract_commands(visible_text)
                execution_attestations = [
                    assess_command_execution(
                        command,
                        operator_requested_execution=operator_requested,
                        tool_execution_enabled=bool(
                            self.config.get("tool_execution_enabled", False)
                        ),
                    ).to_dict()
                    for command in response_commands
                ]
                execution_intents = [
                    build_execution_intent(
                        command,
                        context=intent_context,
                        operator_requested_execution=operator_requested_execution,
                        scope_confirmed=scope_confirmed,
                        rollback_ready=False,
                        verification_ready=True,
                        scope_target=(
                            str(getattr(scenario, "target", "") or "") or None
                            if scenario is not None else None
                        ),
                    ).to_dict()
                    for command in response_commands
                ]
                strategy_attestations = _strategy_attestations(self, sid, message, visible_text)
                host_safety_attestations = _host_safety_attestations(
                    self, sid, message, visible_text
                )
                readiness = assess_tool_readiness(message, scenario=self.scenario_contexts.get(sid))
                privacy_attestation = _privacy_attestation(self, sid, message)

                safe_attestations = []
                for item in attestations:
                    safe = {key: value for key, value in item.items() if key != "command"}
                    safe_attestations.append(safe)

                if visible_text:
                    yield json.dumps({"type": "text_chunk", "text": visible_text}, ensure_ascii=False)
                    emitted_final_text = True

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
                    "execution_attestations": [
                        {
                            key: value
                            for key, value in item.items()
                            if key != "command"
                        }
                        for item in execution_attestations
                    ],
                    "execution_policy_version": "supervised-execution-v1",
                    "execution_intents": [
                        {
                            key: value
                            for key, value in item.items()
                            if key != "command"
                        }
                        for item in execution_intents
                    ],
                    "strategy_attestations": strategy_attestations,
                    "host_safety_attestations": host_safety_attestations,
                    "privacy_attestation": privacy_attestation,
                    "tool_readiness": {
                        "tool": readiness.tool,
                        "ready": readiness.ready,
                        "missing": list(readiness.missing),
                    },
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
                        "execution_ready": (
                            all(item.get("execution_ready", False) for item in execution_attestations)
                            if execution_attestations
                            else None
                        ),
                        "execution_authorities": [
                            item.get("authority") for item in execution_intents
                        ],
                        "execution_risk_max": (
                            max(float(item.get("risk_index", 0.0)) for item in execution_intents)
                            if execution_intents else None
                        ),
                        "host_safety_ok": (
                            all(item.get("safe_to_recommend_now", False) for item in host_safety_attestations)
                            if host_safety_attestations
                            else None
                        ),
                        "privacy_profile": (
                            privacy_attestation.get("top_profile")
                            if isinstance(privacy_attestation, dict)
                            else None
                        ),
                    })

                yield json.dumps(event, ensure_ascii=False)
                continue

            yield raw_event

        # The core stream persists history only after yielding response_meta, so
        # rewrite it here, after the wrapped generator has fully completed.
        if history_needs_rewrite and final_visible_text is not None:
            _replace_latest_assistant_history(self, sid, final_visible_text)

        # Defensive fallback for providers/paths that ended without response_meta.
        if full_text and not emitted_final_text:
            yield json.dumps({"type": "text_chunk", "text": full_text}, ensure_ascii=False)

    engine_cls.stream_agent = wrapped
    engine_cls._response_attestation_installed = True
