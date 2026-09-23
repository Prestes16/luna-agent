"""Fourteenth-stage hardening: operator host integrity guards.

V14 is fail-closed for commands that could damage the operator machine. Luna
remains instruction-only, but proposed commands are still validated before they
are displayed.
"""

from __future__ import annotations

from typing import Any

from . import reasoning_pipeline as _rp
from .host_safety import assess_host_safety
from .reasoning_runtime_patch_v13 import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)
from .reasoning_runtime_patch_v8 import extract_commands


def _context_text(message: str, scenario: Any) -> str:
    parts = [message]
    for attr in ("environment", "scope", "current_goal", "target"):
        value = getattr(scenario, attr, None)
        if value:
            parts.append(str(value))
    parts.extend(str(item) for item in (getattr(scenario, "observed_facts", []) or []))
    return "\n".join(parts)


def _host_safety_reasons(message: str, response: str, scenario: Any) -> list[str]:
    context = _context_text(message, scenario)
    reasons: list[str] = []

    for command in extract_commands(response):
        assessment = assess_host_safety(command, context=context)

        if assessment.remote_pipe_execution:
            reasons.append("host_remote_pipe_to_shell")
        if assessment.system_tree_change:
            reasons.append("host_system_tree_recursive_mutation")
        if assessment.critical_storage and not assessment.safe_to_recommend_now:
            reasons.append("host_critical_storage_preflight_required")
        if assessment.boot_change and not assessment.safe_to_recommend_now:
            reasons.append("host_boot_change_preflight_required")
        if "execution_environment_not_confirmed" in assessment.reasons:
            reasons.append("host_execution_environment_not_confirmed")

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
    reasons.extend(_host_safety_reasons(message, response, scenario))
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

    if "host_remote_pipe_to_shell" in reasons:
        additions.append(
            "não use curl|sh, wget|bash ou PowerShell download|IEX; primeiro baixe para um path "
            "factual, inspecione/hash e só então proponha execução separada se apropriado"
        )
    if "host_system_tree_recursive_mutation" in reasons:
        additions.append(
            "não proponha rm/chmod/chown recursivo sobre árvore de sistema; reduza o escopo ao "
            "artefato factual e use alternativa reversível"
        )
    if "host_critical_storage_preflight_required" in reasons:
        additions.append(
            "para disco/partição exija ambiente explicitamente identificado, snapshot/backup "
            "confirmado e alvo de dispositivo factual antes de qualquer comando mutável"
        )
    if "host_boot_change_preflight_required" in reasons:
        additions.append(
            "para bootloader/BCD/EFI comece por diagnóstico somente-leitura; exija snapshot/backup "
            "e plano de recuperação antes de propor alteração"
        )
    if "host_execution_environment_not_confirmed" in reasons:
        additions.append(
            "não proponha mudança de alto impacto sem saber se o comando será executado no Kali/VM, "
            "Windows host ou outro ambiente; peça/confirme o ambiente primeiro"
        )

    if not additions:
        return base
    return base + "\n\nHOST INTEGRITY HARDENING:\n" + "\n".join(
        f"- {item}." for item in additions
    )
