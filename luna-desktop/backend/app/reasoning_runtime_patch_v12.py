"""Twelfth-stage hardening: command lifecycle sequencing guards.

V12 prevents Luna from chaining an unverified system mutation into subsequent
actions and blocks destructive commands that were not explicitly requested.
This is an output validator; it does not execute shell commands.
"""

from __future__ import annotations

import re
from typing import Any

from . import reasoning_pipeline as _rp
from .command_execution import assess_command_execution
from .reasoning_runtime_patch_v11 import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)
from .reasoning_runtime_patch_v8 import extract_commands


_DESTRUCTIVE_INTENT_MARKERS = (
    "delete", "deletar", "apagar", "remover", "remove", "excluir",
    "destruir", "wipe", "formatar", "format", "resetar", "reset",
    "flush", "limpar regras", "kill", "encerrar processo",
)

_CHAIN_SPLIT_RE = re.compile(r"\s*(?:&&|;|\|\|)\s*")


def _explicit_destructive_intent(message: str) -> bool:
    normalized = message.casefold()
    return any(marker in normalized for marker in _DESTRUCTIVE_INTENT_MARKERS)


def _lifecycle_reasons(message: str, response: str) -> list[str]:
    reasons: list[str] = []
    destructive_requested = _explicit_destructive_intent(message)

    for command in extract_commands(response):
        assessment = assess_command_execution(command)
        if assessment.destructive and not destructive_requested:
            reasons.append("destructive_action_not_explicit")

        segments = [part.strip() for part in _CHAIN_SPLIT_RE.split(command) if part.strip()]
        if len(segments) <= 1:
            continue

        for index, segment in enumerate(segments[:-1]):
            current = assess_command_execution(segment)
            if current.mutates_state:
                reasons.append("unverified_state_change_chain")
                break

    return list(dict.fromkeys(reasons))


def validate_model_response(
    *,
    message: str,
    response: str,
    scenario: Any,
    evidence_delta_count: int,
):
    result = _previous_validate(
        message=message,
        response=response,
        scenario=scenario,
        evidence_delta_count=evidence_delta_count,
    )
    reasons = list(result.reasons)
    reasons.extend(_lifecycle_reasons(message, response))
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

    if "unverified_state_change_chain" in reasons:
        additions.append(
            "não encadeie mudança de estado com próxima ação; entregue uma única mutação, "
            "depois peça/verifique o pós-estado antes de continuar"
        )
    if "destructive_action_not_explicit" in reasons:
        additions.append(
            "não introduza ação destrutiva por iniciativa própria; peça confirmação/intenção "
            "explícita e prefira alternativa reversível"
        )

    if not additions:
        return base
    return base + "\n\nCOMMAND LIFECYCLE HARDENING:\n" + "\n".join(
        f"- {item}." for item in additions
    )
