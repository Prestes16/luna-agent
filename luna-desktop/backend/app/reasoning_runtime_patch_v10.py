"""Tenth-stage hardening: prerequisite-aware Kali command validation.

V10 prevents a command request from collapsing into a system error when the
operator has not yet supplied facts required by the requested tool. A factual
clarification is valid; invented endpoints, credentials and paths remain blocked
by all previous stages.
"""

from __future__ import annotations

from typing import Any

from . import reasoning_pipeline as _rp
from .kali_tool_readiness import assess_tool_readiness, response_requests_missing_facts
from .reasoning_runtime_patch_v8 import extract_commands
from .reasoning_runtime_patch_v9 import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)


_CLARIFICATION_RELAXATIONS = {
    "quality_gate_below_threshold",
    "requested_nmap_command_missing",
}


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
    readiness = assess_tool_readiness(message, scenario=scenario)

    if readiness.tool and not readiness.ready:
        commands = extract_commands(response)
        if commands:
            reasons.append("tool_prerequisites_missing")
        elif response_requests_missing_facts(response, readiness):
            # A request for missing factual inputs is the correct response. Keep
            # every factual guard (e.g. an invented /login path) but do not fail
            # merely because the operator originally asked for a command.
            reasons = [
                reason for reason in reasons
                if reason not in _CLARIFICATION_RELAXATIONS
                and not reason.startswith("expected_one_command_got_")
            ]
        else:
            reasons.append("tool_prerequisite_request_incomplete")

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
    if not reasons & {"tool_prerequisites_missing", "tool_prerequisite_request_incomplete"}:
        return base

    additions = (
        "A ferramenta pedida não possui pré-requisitos factuais suficientes. "
        "Não gere comando ainda. Peça apenas os dados ausentes; não invente endpoint, "
        "campos de formulário, usuário, senha, wordlist ou path local. "
        "Para Hydra, confirme serviço/módulo + fonte de identidade + fonte de segredo; "
        "se for formulário web, confirme também endpoint, campos e marcador de falha."
    )
    return base + "\n\nPRÉ-REQUISITOS DE FERRAMENTA:\n- " + additions
