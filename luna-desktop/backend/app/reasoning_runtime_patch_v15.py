"""Fifteenth-stage hardening: local privacy-preflight correctness.

V15 prevents Luna from asking for a remote target before local Tor/Proxychains
discovery when the operator explicitly says those prerequisites are unknown.
It also blocks configuration overclaims from binary/version-only checks.
"""

from __future__ import annotations

import re
from typing import Any

from . import reasoning_pipeline as _rp
from .network_privacy import local_privacy_preflight_needed
from .reasoning_runtime_patch_v14 import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)
from .reasoning_runtime_patch_v8 import extract_commands


_FENCE_RE = re.compile(
    r"```(?:bash|sh|shell|zsh|powershell|pwsh)?(?:[ \t]*\r?\n|[ \t]+)(.*?)```",
    re.IGNORECASE | re.DOTALL,
)


def _candidate_commands(response: str) -> list[str]:
    """Collect commands even when the generic parser does not know shell built-ins."""
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


_REMOTE_TARGET_PREREQ_RE = re.compile(
    r"(?is)(?:preciso\s+d[ao]\s+(?:base\s+)?url|forne[cç]a\s+(?:a\s+)?url|"
    r"host\s+completo\s+com\s+porta|com\s+o\s+alvo\s+definido|"
    r"antes\s+de\s+qualquer\s+teste.{0,120}(?:url|host|alvo))"
)

_CONFIG_OVERCLAIM_RE = re.compile(
    r"(?is)(?:confirma|comprova|garante|verifica).{0,100}"
    r"(?:configurad[oa]\s+corretamente|configura[cç][aã]o\s+correta|"
    r"configura[cç][aã]o\s+est[aá]\s+correta)"
)

_BINARY_DISCOVERY_RE = re.compile(
    r"(?i)(?:\bwhich\b|\bcommand\s+-v\b|\btype\s+-[ap]\b|--version\b)"
)

_DEEP_CONFIG_CHECK_RE = re.compile(
    r"(?i)(?:\bsystemctl\b|\bss\b|\bnetstat\b|\blsof\b|\bfind\b|"
    r"\blocate\b|proxy_dns|strict_chain|dynamic_chain|socks[45]\b)"
)


def _privacy_preflight_reasons(message: str, response: str) -> list[str]:
    if not local_privacy_preflight_needed(message):
        return []

    reasons: list[str] = []
    commands = _candidate_commands(response)
    command_text = "\n".join(commands)
    response_lower = response.casefold()

    if _REMOTE_TARGET_PREREQ_RE.search(response):
        reasons.append("privacy_local_preflight_blocked_by_remote_target_request")

    if (
        _CONFIG_OVERCLAIM_RE.search(response)
        and _BINARY_DISCOVERY_RE.search(command_text)
        and not _DEEP_CONFIG_CHECK_RE.search(command_text)
    ):
        reasons.append("privacy_binary_check_overclaims_configuration")

    if "proxychains" in message.casefold() and commands:
        command_lower = command_text.casefold()
        checks_proxychains = bool(re.search(r"\bproxychains\b", command_lower))
        checks_proxychains4 = bool(re.search(r"\bproxychains4\b", command_lower))
        if checks_proxychains and not checks_proxychains4:
            reasons.append("privacy_proxychains_variant_assumed")

    # If the response claims it cannot proceed without a target, that is a
    # conceptual block even when it happens to include a local command later.
    if (
        "não posso prosseguir" in response_lower
        or "nao posso prosseguir" in response_lower
    ) and any(term in response_lower for term in ("url", "host", "alvo")):
        reasons.append("privacy_local_preflight_blocked_by_remote_target_request")

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
    reasons.extend(_privacy_preflight_reasons(message, response))
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

    if "privacy_local_preflight_blocked_by_remote_target_request" in reasons:
        additions.append(
            "o target remoto não é pré-requisito para descobrir binários/config/listener locais; "
            "faça primeiro o preflight local solicitado e peça URL/host somente na etapa de egress"
        )
    if "privacy_binary_check_overclaims_configuration" in reasons:
        additions.append(
            "which/command -v/--version prova apenas presença/versão; não diga que isso confirma "
            "configuração, serviço, SOCKS listener, proxy_dns ou roteamento"
        )
    if "privacy_proxychains_variant_assumed" in reasons:
        additions.append(
            "quando a variante Proxychains é desconhecida, descubra proxychains4 e proxychains "
            "em vez de assumir o binário proxychains"
        )

    if not additions:
        return base
    return base + "\n\nLOCAL PRIVACY PREFLIGHT HARDENING:\n" + "\n".join(
        f"- {item}." for item in additions
    )
