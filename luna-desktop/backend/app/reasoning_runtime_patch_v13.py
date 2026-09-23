"""Thirteenth-stage hardening: malware-analysis specimen safety.

V13 prevents the model from presenting direct execution of an untrusted
specimen on the operator host as an analysis step. Dynamic execution remains
possible only as operator-run guidance when the current request explicitly
establishes an isolated disposable sandbox.
"""

from __future__ import annotations

import re
from typing import Any

from . import reasoning_pipeline as _rp
from .malware_analysis import malware_intent, ransomware_intent
from .reasoning_runtime_patch_v12 import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)
from .reasoning_runtime_patch_v8 import extract_commands


_ISOLATED_SANDBOX_MARKERS = (
    "isolated sandbox", "sandbox isolada", "sandbox isolado", "vm isolada",
    "vm isolado", "disposable vm", "vm descartável", "vm descartavel",
    "cuckoo", "cape sandbox",
)

_DIRECT_SAMPLE_EXECUTION = (
    re.compile(r"^\s*\./[^\s]+", re.IGNORECASE),
    re.compile(r"^\s*wine\s+[^\s]+\.(?:exe|scr|dll)\b", re.IGNORECASE),
    re.compile(r"^\s*(?:python|python3)\s+[^\s]+\.(?:py|pyc)\b", re.IGNORECASE),
    re.compile(r"^\s*(?:pwsh|powershell)\b.*(?:-file\s+)?[^\s]+\.(?:ps1|psm1)\b", re.IGNORECASE),
    re.compile(r"^\s*(?:wscript|cscript)\s+[^\s]+\.(?:js|jse|vbs|vbe)\b", re.IGNORECASE),
    re.compile(r"^\s*java\s+-jar\s+[^\s]+\.jar\b", re.IGNORECASE),
    re.compile(r"^\s*(?:dotnet|mono)\s+[^\s]+\.(?:dll|exe)\b", re.IGNORECASE),
)

_DECRYPTION_OVERCLAIM_RE = re.compile(
    r"(?is)(?:garant(?:e|ido|ida)|certeza|100%).{0,80}(?:descriptograf|decrypt|recuperar arquivos)"
)


def _sandbox_explicit(message: str) -> bool:
    normalized = message.casefold()
    return any(marker in normalized for marker in _ISOLATED_SANDBOX_MARKERS)


def _direct_specimen_execution(command: str) -> bool:
    return any(pattern.search(command) for pattern in _DIRECT_SAMPLE_EXECUTION)


def _malware_reasons(message: str, response: str) -> list[str]:
    if not malware_intent(f"{message}\n{response}"):
        return []

    reasons: list[str] = []
    sandbox = _sandbox_explicit(message)

    for command in extract_commands(response):
        if _direct_specimen_execution(command) and not sandbox:
            reasons.append("malware_direct_execution_without_isolated_sandbox")
            break

    if ransomware_intent(message) and _DECRYPTION_OVERCLAIM_RE.search(response):
        reasons.append("ransomware_decryption_overclaim")

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
    reasons.extend(_malware_reasons(message, response))
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

    if "malware_direct_execution_without_isolated_sandbox" in reasons:
        additions.append(
            "não execute nem instrua execução direta da amostra no host; use análise estática "
            "ou peça/estabeleça uma VM/sandbox descartável e isolada antes da análise dinâmica"
        )
    if "ransomware_decryption_overclaim" in reasons:
        additions.append(
            "não garanta descriptografia; condicione recuperação a família conhecida, chave "
            "recuperada ou fraqueza criptográfica demonstrada pela evidência"
        )

    if not additions:
        return base
    return base + "\n\nMALWARE ANALYSIS HARDENING:\n" + "\n".join(
        f"- {item}." for item in additions
    )
