"""Seventh-stage hardening: strategy-aware command validation.

Stages 1-6 establish factual discipline, canonical parsing and critical tool/target
vetoes. Stage 7 evaluates whether a syntactically valid command is strategically
appropriate for the operator's stated intent.
"""

from __future__ import annotations

from typing import Any

from . import reasoning_pipeline as _rp
from .command_ast import assess_nmap_strategy, parse_command
from .reasoning_runtime_patch_v6 import (
    build_replan_instruction as _previous_build_replan,
    extract_commands,
    validate_model_response as _previous_validate,
)

_INITIAL_NMAP_UTILITY_THRESHOLD = 0.38


def _strategy_reasons(message: str, response: str) -> list[str]:
    reasons: list[str] = []
    commands = extract_commands(response)

    for command in commands:
        ast = parse_command(command)
        if not ast or ast.tool != "nmap":
            continue
        assessment = assess_nmap_strategy(message, ast)
        reasons.extend(assessment.reasons)
        if assessment.intent == "initial" and assessment.utility < _INITIAL_NMAP_UTILITY_THRESHOLD:
            reasons.append("nmap_strategy_utility_below_threshold")

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
    reasons.extend(_strategy_reasons(message, response))
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

    if "nmap_overbroad_for_initial_recon" in reasons:
        additions.append(
            "o pedido é uma varredura inicial genérica: não use -A por padrão; escolha uma técnica focalizada de alto ganho de informação e menor ruído"
        )
    if "nmap_vuln_scripts_not_requested" in reasons:
        additions.append(
            "não use --script=vuln se o operador não pediu avaliação de vulnerabilidades"
        )
    if "nmap_initial_scan_mode_implicit" in reasons:
        additions.append(
            "para um comando Nmap inicial no Kali, torne a técnica explícita: prefira -sS com sudo quando raw sockets forem adequados; use -sT quando a execução precisar ser não privilegiada"
        )
    if "nmap_strategy_misses_host_discovery_intent" in reasons:
        additions.append(
            "o operador pediu descoberta de hosts; alinhe o comando a esse objetivo em vez de executar enumeração profunda"
        )
    if "nmap_strategy_utility_below_threshold" in reasons:
        additions.append(
            "a utilidade estratégica U=IG*K*exp(-(lambda_n*N+lambda_c*C)) ficou abaixo do limiar; maximize informação útil e controle explícito por custo/ruído"
        )

    if not additions:
        return base
    return base + "\n\nREPLANEJAMENTO ESTRATÉGICO:\n" + "\n".join(f"- {item}." for item in additions)
