"""Seventh-stage hardening: strategy-aware command validation.

Stages 1-6 establish factual discipline, canonical parsing and critical tool/target
vetoes. Stage 7 evaluates whether a syntactically valid command is strategically
appropriate for the operator's stated intent.
"""

from __future__ import annotations

from typing import Any

from . import reasoning_pipeline as _rp
from .command_ast import assess_nmap_strategy, parse_command
from .offensive_strategy import assess_nmap_port_strategy, recommended_web_port_argument
from .reasoning_runtime_patch_v6 import (
    build_replan_instruction as _previous_build_replan,
    extract_commands,
    validate_model_response as _previous_validate,
)

_INITIAL_NMAP_UTILITY_THRESHOLD = 0.38


def _strategy_reasons(message: str, response: str, scenario: Any = None) -> list[str]:
    reasons: list[str] = []
    commands = extract_commands(response)
    context_parts = [message]
    for attr in ("target", "current_goal", "environment"):
        value = getattr(scenario, attr, None) if scenario is not None else None
        if value:
            context_parts.append(str(value))
    context_text = "\n".join(context_parts)

    for command in commands:
        ast = parse_command(command)
        if not ast or ast.tool != "nmap":
            continue
        assessment = assess_nmap_strategy(context_text, ast)
        reasons.extend(assessment.reasons)
        port_assessment = assess_nmap_port_strategy(context_text, ast)
        reasons.extend(port_assessment.reasons)
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
    reasons.extend(_strategy_reasons(message, response, scenario))
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
    if "nmap_top_ports_generic_for_web_context" in reasons:
        additions.append(
            "o contexto é uma otimização de superfície web: --top-ports usa frequência global e não contexto da aplicação; prefira -p "
            + recommended_web_port_argument()
            + " como priorização heurística, sem afirmar que esses serviços estão abertos antes do scan"
        )
    if "nmap_web_optimization_ports_not_explicit" in reasons:
        additions.append(
            "o operador pediu portas de maior valor no contexto web; torne o vetor -p explícito usando "
            + recommended_web_port_argument()
        )
    if "nmap_web_port_profile_low_coverage" in reasons:
        additions.append(
            "a lista explícita cobre pouco do perfil web de alto valor; reavalie cobertura ponderada sem transformar portas candidatas em fatos"
        )

    if not additions:
        return base
    return base + "\n\nREPLANEJAMENTO ESTRATÉGICO:\n" + "\n".join(f"- {item}." for item in additions)
