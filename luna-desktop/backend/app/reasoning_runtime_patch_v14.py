"""Fourteenth-stage hardening: operator host integrity guards.

V14 is fail-closed for commands that could damage the operator machine. Luna
remains instruction-only, but proposed commands are still validated before they
are displayed.
"""

from __future__ import annotations

import re
from typing import Any

from . import reasoning_pipeline as _rp
from .command_execution import assess_command_execution
from .host_safety import assess_host_safety
from .reasoning_runtime_patch_v13 import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)
from .reasoning_runtime_patch_v8 import extract_commands


_FENCE_RE = re.compile(
    r"```(?:bash|sh|shell|zsh|powershell|pwsh)?(?:[ \t]*\r?\n|[ \t]+)(.*?)```",
    re.IGNORECASE | re.DOTALL,
)

_ROLLBACK_MARKERS = (
    "rollback", "reverter", "reversão", "reversao", "desfazer", "restaurar",
    "restore", "backup", "snapshot", "disable novamente", "down novamente",
)


_APT_MUTATION_RE = re.compile(
    r"(?i)^\s*(?:sudo\s+)?apt(?:-get)?\b.*\b(?:install|remove|purge|upgrade|full-upgrade|dist-upgrade|autoremove)\b"
)
_APT_SIMULATION_RE = re.compile(
    r"(?i)^\s*(?:sudo\s+)?apt(?:-get)?\b.*(?:^|\s)(?:-s|--simulate|--dry-run)(?:\s|$)"
)
_APT_PREFLIGHT_CONFIRMED_MARKERS = (
    "dry-run confirmado", "dry run confirmado", "simulação confirmada",
    "simulacao confirmada", "apt simulation confirmed",
)


def _candidate_commands(response: str) -> list[str]:
    commands = list(extract_commands(response))
    for block in _FENCE_RE.findall(response):
        for line in block.splitlines():
            compact = line.strip()
            if compact.startswith("$ "):
                compact = compact[2:].lstrip()
            if compact.startswith("PS> "):
                compact = compact[4:].lstrip()
            if compact and not compact.startswith("#"):
                commands.append(compact)
    return list(dict.fromkeys(commands))


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
    response_lower = response.casefold()
    rollback_documented = any(marker in response_lower for marker in _ROLLBACK_MARKERS)
    context_lower = context.casefold()
    apt_preflight_confirmed = any(
        marker in context_lower for marker in _APT_PREFLIGHT_CONFIRMED_MARKERS
    )

    for command in _candidate_commands(response):
        assessment = assess_host_safety(command, context=context)
        lifecycle = assess_command_execution(command)

        if assessment.remote_pipe_execution:
            reasons.append("host_remote_pipe_to_shell")
        if (
            _APT_MUTATION_RE.search(command)
            and not _APT_SIMULATION_RE.search(command)
            and not apt_preflight_confirmed
        ):
            reasons.append("host_package_change_preflight_required")
        if assessment.system_tree_change:
            reasons.append("host_system_tree_recursive_mutation")
        if assessment.critical_storage and not assessment.safe_to_recommend_now:
            reasons.append("host_critical_storage_preflight_required")
        if assessment.boot_change and not assessment.safe_to_recommend_now:
            reasons.append("host_boot_change_preflight_required")
        if assessment.security_control_reduction and not assessment.safe_to_recommend_now:
            reasons.append("host_security_control_preflight_required")
        if "execution_environment_not_confirmed" in assessment.reasons:
            reasons.append("host_execution_environment_not_confirmed")
        if (
            assessment.rollback_required
            and (
                assessment.network_control_change
                or assessment.persistent_change
                or assessment.critical_storage
                or assessment.boot_change
            )
            and not rollback_documented
        ):
            reasons.append("host_rollback_plan_missing")

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
    if "host_package_change_preflight_required" in reasons:
        additions.append(
            "no Kali/Debian, antes de apt/apt-get install/remove/upgrade proponha uma simulação "
            "(-s/--simulate) com os mesmos pacotes e aguarde o resultado; não aplique a mutação no "
            "mesmo passo"
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
    if "host_security_control_preflight_required" in reasons:
        additions.append(
            "não desative Defender/firewall ou controles equivalentes no host; só considere redução "
            "temporária de controle em VM/lab descartável explicitamente confirmado, com snapshot, "
            "escopo mínimo, rollback e verificação"
        )
    if "host_execution_environment_not_confirmed" in reasons:
        additions.append(
            "não proponha mudança de estado de alto impacto sem saber se o comando será executado "
            "no Kali/VM, Windows host ou outro ambiente; peça/confirme o ambiente primeiro"
        )
    if "host_rollback_plan_missing" in reasons:
        additions.append(
            "para mudança persistente, firewall/rota, disco ou boot, inclua o rollback factual "
            "e a verificação pós-estado; se o operador pediu um passo por vez, entregue primeiro "
            "o precheck/backup e espere o resultado antes da mutação"
        )

    if not additions:
        return base
    return base + "\n\nHOST INTEGRITY HARDENING:\n" + "\n".join(
        f"- {item}." for item in additions
    )
