"""Stage 19: execution-semantics and epistemic-section consistency.

This stage keeps the deterministic harness authoritative when the model labels a
proposed command, and rejects a narrow class of claims that turn an explicitly
untested endpoint into negative evidence.
"""

from __future__ import annotations

import re
from typing import Any

from . import reasoning_pipeline as _rp
from .execution_intent import build_execution_intent
from .reasoning_runtime_patch_v18 import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)


def _section(response: str, start_pattern: str, *end_patterns: str) -> str:
    start = re.search(rf"(?im)^\s*(?:\d+[.)]\s*)?\**(?:{start_pattern})\**\s*:?\s*", response)
    if not start:
        return ""
    tail = response[start.end():]
    ends: list[int] = []
    for pattern in end_patterns:
        match = re.search(rf"(?im)^\s*(?:\d+[.)]\s*)?\**(?:{pattern})\**\s*:?\s*", tail)
        if match:
            ends.append(match.start())
    return tail[:min(ends)] if ends else tail


def _untested_paths(message: str) -> tuple[str, ...]:
    paths: list[str] = []
    for path in sorted(_rp._observed_route_paths(message)):
        if re.search(
            rf"{re.escape(path)}[\s.,;:)]*.{{0,100}}(?:não|nao).{{0,30}}test",
            message,
            re.IGNORECASE | re.DOTALL,
        ):
            paths.append(path)
    return tuple(paths)


def _explicit_authority_level(response: str) -> str | None:
    match = re.search(
        r"(?im)\b(?:classifica(?:ção|cao)|authority(?:\s+level)?|nível|nivel)"
        r"\s*(?:da\s+ação|da\s+acao)?\s*[:=-]\s*(L[0-3])\b",
        response,
    )
    if match:
        return match.group(1).upper()
    match = re.search(r"(?im)^\s*(L[0-3])\s*\((?:OBSERVE|PROBE|MUTATE|HIGH IMPACT)\)", response)
    return match.group(1).upper() if match else None


def _stage19_reasons(message: str, response: str, scenario: Any) -> list[str]:
    reasons: list[str] = []
    normalized_message = message.casefold()
    normalized_response = response.casefold()

    facts = _section(
        response,
        r"FACTS|FATOS",
        r"HYPOTHESIS|HYPOTHESES|HIP(?:Ó|O)TESE(?:S)?",
        r"NEXT\s+TEST|PR(?:Ó|O)XIMO\s+TESTE",
    )
    hypotheses = _section(
        response,
        r"HYPOTHESIS|HYPOTHESES|HIP(?:Ó|O)TESE(?:S)?",
        r"NEXT\s+TEST|PR(?:Ó|O)XIMO\s+TESTE",
    )

    if facts and re.search(
        r"(?i)\b(?:hipótese|hipotese|hypothesis|talvez|provavelmente|pode\s+indicar|sugerindo\s+que)\b",
        facts,
    ):
        reasons.append("hypothesis_leaked_into_facts")

    for path in _untested_paths(message):
        escaped = re.escape(path)
        unsupported_absence = re.search(
            rf"(?is)(?:ausência|ausencia|sem)\s+(?:de\s+)?(?:resposta|status)"
            rf".{{0,35}}\b[1-5]\d{{2}}\b.{{0,120}}{escaped}"
            rf"|{escaped}.{{0,120}}(?:não\s+retornou|nao\s+retornou|ausência|ausencia|sem\s+resposta)"
            rf".{{0,35}}\b[1-5]\d{{2}}\b",
            hypotheses,
        )
        if unsupported_absence:
            reasons.append("untested_endpoint_negative_evidence_claim")
            break

    commands = _rp.extract_commands(response)
    explicit_level = _explicit_authority_level(response)
    if commands and explicit_level:
        target = getattr(scenario, "target", None)
        scope = bool(getattr(scenario, "scope", None))
        intent = build_execution_intent(
            commands[0],
            context=message,
            operator_requested_execution=False,
            scope_confirmed=scope,
            scope_target=target,
        )
        expected_level = str(intent.authority_level).split("_", 1)[0]
        if explicit_level != expected_level:
            reasons.append("authority_level_mismatch")

    if "proposed_action" in normalized_message and "executed_action" in normalized_message:
        proposed_named = "proposed_action" in normalized_response
        executed_negated = bool(
            re.search(
                r"(?is)(?:não|nao|not)\s+(?:é|e|is)?\s*executed_action"
                r"|executed_action\s*[:=-]\s*(?:não|nao|no|false)",
                response,
            )
        )
        if not proposed_named or not executed_negated:
            reasons.append("execution_state_not_explicit")

    return reasons


def validate_model_response(*, message: str, response: str, scenario: Any, evidence_delta_count: int):
    result = _previous_validate(
        message=message,
        response=response,
        scenario=scenario,
        evidence_delta_count=evidence_delta_count,
    )
    reasons = list(result.reasons)
    reasons.extend(_stage19_reasons(message, response, scenario))
    reasons = list(dict.fromkeys(reasons))

    loop_guard = result.loop_guard
    if not reasons and loop_guard in {"replan_required", "blocked_repeat"}:
        loop_guard = "clear"
    elif reasons and loop_guard in {"clear", "retest_allowed"}:
        loop_guard = "replan_required"

    return _rp.ValidationResult(
        valid=not reasons,
        reasons=tuple(reasons),
        loop_guard=loop_guard,
        proposed_action_fingerprint=result.proposed_action_fingerprint,
        command_count=result.command_count,
    )


def build_replan_instruction(validation, scenario_prompt: str, current_message: str = "") -> str:
    base = _previous_build_replan(validation, scenario_prompt, current_message)
    reasons = set(validation.reasons)
    additions: list[str] = []

    if "hypothesis_leaked_into_facts" in reasons:
        additions.append(
            "FACTS deve conter somente observações; mova explicações possíveis para HYPOTHESIS"
        )
    if "untested_endpoint_negative_evidence_claim" in reasons:
        additions.append(
            "endpoint não testado não possui ausência de 200/403/401 observada; o resultado permanece UNKNOWN"
        )
    if "authority_level_mismatch" in reasons:
        additions.append(
            "classifique request ativa via curl/HTTP contra o alvo como L1 PROBE quando não há mutação; L0 é observação local/passiva"
        )
    if "execution_state_not_explicit" in reasons:
        additions.append(
            "quando pedido, declare literalmente PROPOSED_ACTION e que NÃO é EXECUTED_ACTION"
        )

    if not additions:
        return base
    return base + "\n\nSTAGE 19 — CONSISTÊNCIA OPERACIONAL:\n" + "\n".join(
        f"- {item}." for item in additions
    )
