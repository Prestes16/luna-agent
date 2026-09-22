"""Second-stage validator hardening for URL-aware and semantic factual checks.

This layer keeps the strict factual guards while removing URL parser false positives
and rejecting a small class of high-impact semantic overclaims observed in real
local Ollama sessions.
"""

from __future__ import annotations

import re
from typing import Any

from . import reasoning_pipeline as _rp
from .reasoning_runtime_patch import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)

_URL_RE = re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE)


def _route_paths(value: str) -> set[str]:
    """Return actual route paths without treating URL authorities as paths."""
    urls = list(_URL_RE.findall(value))
    scrubbed = _URL_RE.sub(" ", value)
    paths = {
        path.casefold()
        for path in _rp._PATH_RE.findall(scrubbed)
        if path and path != "/"
    }

    for url in urls:
        try:
            _, resource = _rp._normalize_url(url)
        except (TypeError, ValueError):
            continue
        path = resource.split("?", 1)[0]
        if path and path != "/":
            paths.add(path.casefold())

    return paths


def _untested_paths(message: str) -> list[str]:
    paths: list[str] = []
    for path in dict.fromkeys(_rp._PATH_RE.findall(message)):
        if re.search(
            rf"{re.escape(path)}.{{0,100}}(?:não|nao).{{0,24}}test",
            message,
            re.IGNORECASE | re.DOTALL,
        ):
            paths.append(path)
    return paths


def _section(response: str, start: str, *ends: str) -> str:
    start_match = re.search(rf"(?im)^\s*\**{start}\**\s*:?\s*", response)
    if not start_match:
        return ""
    tail = response[start_match.end():]
    end_positions: list[int] = []
    for end in ends:
        match = re.search(rf"(?im)^\s*\**{end}\**\s*:?\s*", tail)
        if match:
            end_positions.append(match.start())
    return tail[:min(end_positions)] if end_positions else tail


def _semantic_overclaim_reasons(message: str, response: str) -> list[str]:
    """Catch claims that convert an explicitly untested endpoint into a result."""
    reasons: list[str] = []
    untested = _untested_paths(message)
    if not untested:
        return reasons

    facts = _section(response, "FATOS", "INFER(?:Ê|E)NCIAS", "HIP(?:Ó|O)TESES", "PR(?:Ó|O)XIMO")
    hypotheses = _section(response, "HIP(?:Ó|O)TESES", "PR(?:Ó|O)XIMO", "COMANDO")

    for path in untested:
        escaped = re.escape(path)
        # An endpoint explicitly described as untested cannot have an observed
        # HTTP status promoted into the FATOS section.
        if re.search(
            rf"(?is)(?:\b[1-5]\d{{2}}\b.{{0,80}}{escaped}|{escaped}.{{0,80}}\b[1-5]\d{{2}}\b)",
            facts,
        ):
            reasons.append("status_claim_for_untested_endpoint")

        # A hypothesis may discuss possible outcomes, but must not predict one as
        # certain before the request is actually made.
        if re.search(
            rf"(?is){escaped}.{{0,120}}(?:será|sera|vai\s+retornar|retornará|retornara)"
            rf".{{0,40}}\b[1-5]\d{{2}}\b",
            hypotheses,
        ):
            reasons.append("definitive_outcome_for_untested_endpoint")

    normalized_message = message.casefold()
    normalized_response = response.casefold()
    unsupported_negative_markers = (
        "não realiza chamadas api",
        "nao realiza chamadas api",
        "não faz chamadas api",
        "nao faz chamadas api",
        "não realiza requisições",
        "nao realiza requisicoes",
    )
    if any(marker in normalized_response for marker in unsupported_negative_markers) and not any(
        marker in normalized_message for marker in unsupported_negative_markers
    ):
        reasons.append("unsupported_client_behavior_claim")

    return reasons


def validate_model_response(
    *,
    message: str,
    response: str,
    scenario: Any,
    evidence_delta_count: int,
):
    """Remove URL-parser false positives and reject semantic factual overclaims."""
    result = _previous_validate(
        message=message,
        response=response,
        scenario=scenario,
        evidence_delta_count=evidence_delta_count,
    )
    reasons = list(result.reasons)

    if "unobserved_endpoint_mentioned" in reasons:
        scenario_facts = "\n".join(getattr(scenario, "observed_facts", []) or [])
        factual_context = f"{message}\n{scenario_facts}"
        observed = _route_paths(factual_context)
        response_paths = _route_paths(response)
        truly_unobserved = response_paths - observed
        if not truly_unobserved:
            reasons.remove("unobserved_endpoint_mentioned")

    reasons.extend(_semantic_overclaim_reasons(message, response))
    reasons = list(dict.fromkeys(reasons))

    loop_guard = result.loop_guard
    if not reasons and loop_guard == "replan_required":
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
    """Extend the existing replan with precise semantic corrections."""
    base = _previous_build_replan(validation, scenario_prompt, current_message)
    reasons = set(validation.reasons)
    additions: list[str] = []
    if "status_claim_for_untested_endpoint" in reasons:
        additions.append(
            "endpoint explicitamente não testado não possui status observado; remova qualquer 200/401/403 dele da seção FATOS"
        )
    if "definitive_outcome_for_untested_endpoint" in reasons:
        additions.append(
            "em HIPÓTESES use linguagem condicional (pode, seria compatível, se... então); não diga que um status futuro certamente ocorrerá"
        )
    if "unsupported_client_behavior_claim" in reasons:
        additions.append(
            "não afirme que o frontend faz ou não faz chamadas de API se isso não foi observado no Network/código fornecido"
        )
    if not additions:
        return base
    return base + "\n\nCORREÇÕES SEMÂNTICAS OBRIGATÓRIAS:\n" + "\n".join(
        f"- {item}." for item in additions
    )
