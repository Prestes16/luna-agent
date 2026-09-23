"""Stage 18: exact arithmetic response validation."""

from __future__ import annotations

import re
from typing import Any

from . import reasoning_pipeline as _rp
from .reasoning_runtime_patch_v17 import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)

_PLAIN_MUL_SATURATION_RE = re.compile(
    r"(?is)(?:multiplica[cç][aã]o\s+(?:direta|normal)|operador\s+\*)" 
    r".{0,120}(?:saturar|saturate|saturation)"
)
_CURRENCY_TOLERANCE_RE = re.compile(
    r"(?is)(?:toler[aâ]ncia|erro\s+absoluto).{0,80}(?:\$\s*0[\.,]01|centavo|cent)"
)
_UNBOUNDED_ROUNDING_RE = re.compile(
    r"(?is)(?:rounding|arredondamento|truncamento).{0,100}"
    r"(?:erro|perda|desvio).{0,80}(?:significativ|grande|large)"
)


def _exact_arithmetic_reasons(message: str, response: str, scenario: Any) -> list[str]:
    normalized_message = message.casefold()
    normalized_response = response.casefold()
    reasons: list[str] = []

    if _PLAIN_MUL_SATURATION_RE.search(response):
        reasons.append("plain_integer_multiplication_saturation_overclaim")

    prompt_has_currency = any(
        marker in normalized_message
        for marker in ("$", "usd", "dólar", "dolar", "centavo", "cent")
    )
    if not prompt_has_currency and _CURRENCY_TOLERANCE_RE.search(response):
        reasons.append("invented_currency_tolerance")

    if _UNBOUNDED_ROUNDING_RE.search(response):
        has_bound = any(
            marker in normalized_response
            for marker in (
                "<1 base unit", "< 1 base unit", "menos de 1 base unit",
                "remainder", "resto", "módulo", "modulo", "%",
            )
        )
        if not has_bound:
            reasons.append("rounding_loss_not_bounded")

    return reasons


def validate_model_response(*, message: str, response: str, scenario: Any, evidence_delta_count: int):
    result = _previous_validate(
        message=message, response=response, scenario=scenario,
        evidence_delta_count=evidence_delta_count,
    )
    reasons = list(result.reasons)
    reasons.extend(_exact_arithmetic_reasons(message, response, scenario))
    reasons = list(dict.fromkeys(reasons))
    loop_guard = result.loop_guard
    if not reasons and loop_guard in {"replan_required", "blocked_repeat"}:
        loop_guard = "clear"
    elif reasons and loop_guard in {"clear", "retest_allowed"}:
        loop_guard = "replan_required"
    return _rp.ValidationResult(
        valid=not reasons, reasons=tuple(reasons), loop_guard=loop_guard,
        proposed_action_fingerprint=result.proposed_action_fingerprint,
        command_count=result.command_count,
    )


def build_replan_instruction(validation, scenario_prompt: str, current_message: str = "") -> str:
    base = _previous_build_replan(validation, scenario_prompt, current_message)
    reasons = set(validation.reasons)
    additions: list[str] = []
    if "plain_integer_multiplication_saturation_overclaim" in reasons:
        additions.append("inteiro com operador * não satura implicitamente; saturação exige operação explícita")
    if "invented_currency_tolerance" in reasons:
        additions.append("não invente moeda ou tolerância monetária; use somente escala/base unit observadas")
    if "rounding_loss_not_bounded" in reasons:
        additions.append("quantifique truncamento pelo resto e dê um limite antes de chamar a perda significativa")
    if not additions:
        return base
    return base + "\n\nEXACT ARITHMETIC:\n" + "\n".join(f"- {item}." for item in additions)
