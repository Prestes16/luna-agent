"""Seventeenth-stage hardening: quantitative and physical claim integrity.

V17 keeps numeric-security conclusions tied to an explicit mathematical domain
and physical side-channel conclusions tied to measurable evidence. Hypotheses
remain allowed; unsupported promotion to confirmed findings is rejected.
"""

from __future__ import annotations

import re
from typing import Any

from . import reasoning_pipeline as _rp
from .quantitative_reasoning import quantitative_guidance
from .reasoning_runtime_patch_v16 import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)


_STRONG_QUANT_CLAIM_RE = re.compile(
    r"(?is)(?:"
    r"(?:overflow|underflow|rounding|arredondamento|precision|precisão|precisao|"
    r"modulo\s+bias|modulo\s+bias|bias|entropy|entropia|collision|colisão|colisao|"
    r"dust|fee\s+bug|randomness\s+bias).{0,90}"
    r"(?:confirmad[oa]|comprovad[oa]|explor[aá]vel|vulner[aá]vel|guaranteed|confirmed|proven|exploitable)|"
    r"(?:confirmad[oa]|comprovad[oa]|confirmed|proven).{0,90}"
    r"(?:overflow|underflow|rounding|arredondamento|bias|entropy|entropia|collision|colisão|colisao|dust)"
    r")"
)

_STRONG_PHYSICS_CLAIM_RE = re.compile(
    r"(?is)(?:timing|side[- ]channel|power\s+analysis|electromagnetic|\bem\b|"
    r"rf\s+leak|thermal).{0,100}"
    r"(?:confirmad[oa]|comprovad[oa]|confirmed|proven|explor[aá]vel|exploitable)"
)

_CALIBRATION_MARKERS = (
    "hipótese", "hipotese", "hypothesis", "inferência", "inferencia", "inference",
    "não confirma", "nao confirma", "ainda não", "ainda nao", "condicional",
    "evidência insuficiente", "evidencia insuficiente",
)

_NUMERIC_MECHANISM_MARKERS = (
    "u8", "u16", "u32", "u64", "u128", "i8", "i16", "i32", "i64", "i128",
    "signed", "unsigned", "checked_", "wrapping", "saturating", "overflowing_",
    "min", "max", "bound", "limite", "bits", "decimals", "base unit", "base-unit",
    "lamport", "basis point", "bps", "floor", "ceil", "round", "remainder", "resto",
    "mod ", "modulo", "módulo", "%", "invariante", "invariant", "conserv",
    "sample space", "distribution", "distribuição", "distribuicao", "entropy", "entropia",
)

_MEASUREMENT_MARKERS = (
    "sample", "amostra", "median", "mediana", "mean", "média", "media", "variance",
    "variância", "variancia", "standard deviation", "desvio", "confidence interval",
    "effect size", "noise", "ruído", "ruido", "snr", "resolution", "resolução", "resolucao",
    "hz", "khz", "mhz", "ghz", "ns", "µs", "us", "ms", "db", "dbm", "volt", "amp", "watt",
)


def _quantitative_reasons(message: str, response: str, scenario: Any) -> list[str]:
    context = f"{message}\n" + "\n".join(
        str(item) for item in (getattr(scenario, "observed_facts", []) or [])
    )
    if not quantitative_guidance(context):
        return []

    normalized = response.casefold()
    calibrated = any(marker in normalized for marker in _CALIBRATION_MARKERS)
    reasons: list[str] = []

    if _STRONG_QUANT_CLAIM_RE.search(response) and not calibrated:
        if not any(marker in normalized for marker in _NUMERIC_MECHANISM_MARKERS):
            reasons.append("quantitative_strong_claim_without_numeric_mechanism")

    if _STRONG_PHYSICS_CLAIM_RE.search(response) and not calibrated:
        if not any(marker in normalized for marker in _MEASUREMENT_MARKERS):
            reasons.append("physics_strong_claim_without_measurement")

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
    reasons.extend(_quantitative_reasons(message, response, scenario))
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
    if "quantitative_strong_claim_without_numeric_mechanism" in reasons:
        additions.append(
            "para conclusão matemática forte, declare representação/domínio, limites, ordem das "
            "operações/arredondamento e o invariante; se faltar evidência, mantenha como hipótese"
        )
    if "physics_strong_claim_without_measurement" in reasons:
        additions.append(
            "para conclusão física/timing/side-channel, exija mecanismo mensurável, unidades, "
            "amostragem e ruído/resolução antes de chamar o efeito de confirmado"
        )
    if not additions:
        return base
    return base + "\n\nQUANTITATIVE HARDENING:\n" + "\n".join(
        f"- {item}." for item in additions
    )
