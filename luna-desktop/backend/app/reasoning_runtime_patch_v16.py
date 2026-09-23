"""Sixteenth-stage hardening: construction-grounded cyber conclusions.

V16 keeps strong vulnerability/exploit conclusions tied to an explicit causal
mechanism. It does not block hypothesis generation; it blocks promoting a
speculative attack idea into a confirmed result without mechanism/evidence.
"""

from __future__ import annotations

import re
from typing import Any

from . import reasoning_pipeline as _rp
from .construction_reasoning import construction_guidance
from .reasoning_runtime_patch_v15 import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)


_STRONG_VULN_CLAIM_RE = re.compile(
    r"(?is)(?:"
    r"(?:rce|sql\s+injection|sqli|auth(?:entication|orization)?\s+bypass|"
    r"bypass|privesc|privilege\s+escalation|reentrancy|buffer\s+overflow|"
    r"memory\s+corruption|xss).{0,80}"
    r"(?:confirmad[oa]|comprovad[oa]|garantid[oa]|explor[aá]vel|exploitable)|"
    r"(?:vulner[aá]vel|vulnerable).{0,80}"
    r"(?:rce|sql\s+injection|sqli|bypass|privesc|reentrancy|overflow|xss)|"
    r"(?:exploit|poc).{0,40}(?:funciona|works|confirmad[oa]|comprovad[oa])"
    r")"
)

_MECHANISM_MARKERS = (
    "mecanismo", "mechanism", "invariante", "invariant", "fronteira de confiança",
    "trust boundary", "transição de estado", "transicao de estado", "state transition",
    "fluxo", "flow", "parser", "autorização", "autorizacao", "authorization",
    "validação", "validacao", "validation", "controle", "control", "memória", "memoria",
    "memory", "authority", "signer", "pda", "call graph", "entry point",
)

_CALIBRATION_MARKERS = (
    "hipótese", "hipotese", "hypothesis", "inferência", "inferencia", "inference",
    "ainda não confirma", "ainda nao confirma", "não confirma", "nao confirma",
    "condicional", "se a", "se o ", "evidência insuficiente", "evidencia insuficiente",
)


def _construction_reasons(message: str, response: str, scenario: Any) -> list[str]:
    context = f"{message}\n" + "\n".join(
        str(item) for item in (getattr(scenario, "observed_facts", []) or [])
    )
    if not construction_guidance(context):
        return []

    if not _STRONG_VULN_CLAIM_RE.search(response):
        return []

    normalized_response = response.casefold()
    has_mechanism = any(marker in normalized_response for marker in _MECHANISM_MARKERS)
    calibrated = any(marker in normalized_response for marker in _CALIBRATION_MARKERS)

    reasons: list[str] = []
    if not has_mechanism and not calibrated:
        reasons.append("construction_strong_claim_without_mechanism")
    return reasons


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
    reasons.extend(_construction_reasons(message, response, scenario))
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
    if "construction_strong_claim_without_mechanism" not in set(validation.reasons):
        return base
    return (
        base
        + "\n\nBUILD-TO-BREAK HARDENING:\n"
        + "- não promova exploração/vulnerabilidade a fato confirmado sem ligar a conclusão "
        + "ao componente, interface/fluxo, fronteira de confiança ou transição de estado, "
        + "invariante violado e evidência observada. Se isso ainda não estiver estabelecido, "
        + "rebaixe a conclusão para hipótese e proponha o teste discriminador mínimo."
    )
