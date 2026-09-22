"""Fifth-stage reasoning hardening: critical veto + target string distance.

Stage 4 produces a soft quantitative quality score.  This layer adds a hard
contract veto for non-compensable failures (wrong requested tool or wrong target)
and a normalized Levenshtein similarity for diagnostics/replanning.

The rule is intentionally asymmetric: textual style can be imperfect, but a
command aimed at the wrong host or using the wrong explicitly requested tool
must never be rescued by strengths in unrelated dimensions.
"""

from __future__ import annotations

import re
import shlex
from typing import Any
from urllib.parse import urlsplit

from . import reasoning_pipeline as _rp
from .reasoning_quality import build_operator_contract, score_response_quality
from .reasoning_runtime_patch import extract_commands
from .reasoning_runtime_patch_v4 import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)

_CRITICAL_SIMILARITY_THRESHOLD = 0.999
_URL_RE = re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE)


def levenshtein_distance(a: str, b: str) -> int:
    """Exact Levenshtein edit distance using O(min(m,n)) memory."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) > len(b):
        a, b = b, a

    previous = list(range(len(a) + 1))
    for i, cb in enumerate(b, start=1):
        current = [i]
        for j, ca in enumerate(a, start=1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            substitute = previous[j - 1] + (ca != cb)
            current.append(min(insert, delete, substitute))
        previous = current
    return previous[-1]


def normalized_similarity(a: str, b: str) -> float:
    """Return 1 - normalized Levenshtein distance in [0,1]."""
    left = a.casefold().rstrip(".")
    right = b.casefold().rstrip(".")
    denominator = max(len(left), len(right), 1)
    return 1.0 - (levenshtein_distance(left, right) / denominator)


def _command_tool(command: str) -> str:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    return tokens[0].casefold().removesuffix(".exe") if tokens else ""


def _candidate_hosts(command: str) -> set[str]:
    """Extract explicit URL hosts and host-like command arguments."""
    hosts: set[str] = set()
    for raw_url in _URL_RE.findall(command):
        try:
            parsed = urlsplit(raw_url.strip("`'\".,;"))
        except ValueError:
            continue
        if parsed.hostname:
            hosts.add(parsed.hostname.casefold().rstrip("."))

    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()

    # Add host-like positional tokens.  This deliberately excludes option values
    # that do not resemble a hostname/IP; later comparison only considers values
    # containing a dot or a colon (IPv6) or localhost.
    for token in tokens[1:]:
        value = token.strip("`'\".,;")
        if value.startswith("-") or "/" in value and not value.startswith(("http://", "https://")):
            continue
        if value.startswith(("http://", "https://")):
            continue
        if value == "localhost" or "." in value or ":" in value:
            # Strip a simple :port suffix from DNS/IPv4 targets.
            if value.count(":") == 1 and not re.fullmatch(r"[0-9a-fA-F:]+", value):
                value = value.split(":", 1)[0]
            hosts.add(value.casefold().rstrip("."))
    return hosts


def _best_target_similarity(expected_hosts: tuple[str, ...], commands: list[str]) -> float:
    if not expected_hosts or not commands:
        return 1.0
    generated: set[str] = set()
    for command in commands:
        generated.update(_candidate_hosts(command))
    if not generated:
        return 0.0
    return max(
        normalized_similarity(generated_host, expected_host)
        for generated_host in generated
        for expected_host in expected_hosts
    )


def _critical_veto_reasons(message: str, response: str) -> list[str]:
    contract = build_operator_contract(message)
    if not contract.wants_command:
        return []

    commands = extract_commands(response)
    reasons: list[str] = []

    if contract.requested_tool and commands:
        if any(_command_tool(command) != contract.requested_tool for command in commands):
            reasons.append("critical_tool_veto")

    if contract.target_hosts:
        similarity = _best_target_similarity(contract.target_hosts, commands)
        if similarity < _CRITICAL_SIMILARITY_THRESHOLD:
            reasons.append("critical_target_veto")
            reasons.append("target_similarity_below_threshold")

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
    reasons.extend(_critical_veto_reasons(message, response))
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
    base = _previous_build_replan(validation, scenario_prompt, current_message)
    reasons = set(validation.reasons)
    additions: list[str] = []
    contract = build_operator_contract(current_message)

    if "critical_tool_veto" in reasons and contract.requested_tool:
        additions.append(
            f"VETO CRÍTICO: use exatamente {contract.requested_tool}; ferramenta diferente zera a qualidade"
        )
    if "critical_target_veto" in reasons and contract.target_hosts:
        additions.append(
            "VETO CRÍTICO: preserve exatamente o host observado (" + ", ".join(contract.target_hosts)
            + "); qualquer typo ou host diferente zera a qualidade"
        )
    if "target_similarity_below_threshold" in reasons:
        additions.append(
            "a similaridade Levenshtein normalizada do target ficou abaixo do limite crítico; copie o host factual literalmente"
        )

    if not additions:
        return base
    return base + "\n\nVETOS MATEMÁTICOS NÃO COMPENSÁVEIS:\n" + "\n".join(
        f"- {item}." for item in additions
    )
