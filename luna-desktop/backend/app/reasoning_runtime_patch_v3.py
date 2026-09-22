"""Third-stage response hardening for command fidelity.

This layer validates executable commands requested by the operator, with an
initial focus on Nmap because local CTF/audit prompts commonly provide a URL
while Nmap requires a host/IP/CIDR target rather than an http(s) URL.
"""

from __future__ import annotations

import re
import shlex
from urllib.parse import urlsplit
from typing import Any

from . import reasoning_pipeline as _rp
from .reasoning_runtime_patch import extract_commands
from .reasoning_runtime_patch_v2 import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)

_URL_RE = re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE)
_NMAP_ALIAS_RE = re.compile(r"(?i)\b([A-Za-z][A-Za-z0-9 +._-]{2,48})\s*\(\s*NMAP\s*\)")


def _requested_nmap(message: str) -> bool:
    normalized = message.casefold()
    return "nmap" in normalized and any(
        marker in normalized
        for marker in (
            "comando", "command", "bash", "executar", "execute", "rode", "rodar",
            "scan", "escan", "varredura",
        )
    )


def _observed_hosts(message: str) -> set[str]:
    hosts: set[str] = set()
    for url in _URL_RE.findall(message):
        try:
            parsed = urlsplit(url.strip("`'\".,;"))
        except ValueError:
            continue
        if parsed.hostname:
            hosts.add(parsed.hostname.casefold())

    # Also accept explicit host/IP tokens after common target markers when no URL
    # scheme was supplied.
    for match in re.finditer(
        r"(?i)\b(?:alvo|target|host|dom[ií]nio)\s*(?:é|e|:)?\s*"
        r"([A-Za-z0-9][A-Za-z0-9.-]*(?::\d+)?)",
        message,
    ):
        value = match.group(1).split(":", 1)[0].rstrip(".").casefold()
        if value:
            hosts.add(value)
    return hosts


def _nmap_targets(command: str) -> tuple[list[str], bool]:
    """Return positional Nmap targets and whether a URL scheme was used."""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    if not tokens or tokens[0].casefold() != "nmap":
        return [], False

    value_options = {
        "-p", "--top-ports", "--exclude-ports", "-s", "--script", "--script-args",
        "-oN", "-oX", "-oG", "-oA", "-iL", "--exclude", "--dns-servers",
        "--source-port", "-g", "--max-retries", "--host-timeout", "--scan-delay",
        "--max-rate", "--min-rate", "-S", "-e", "-D", "--proxies",
    }
    targets: list[str] = []
    has_scheme = False
    index = 1
    while index < len(tokens):
        token = tokens[index]
        lower = token.casefold()
        if lower.startswith(("http://", "https://")):
            has_scheme = True
            targets.append(token)
            index += 1
            continue
        if token in value_options and index + 1 < len(tokens):
            index += 2
            continue
        if any(token.startswith(opt + "=") for opt in value_options if opt.startswith("--")):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        # Output filenames and script arguments are consumed above. Remaining
        # positionals are target expressions.
        targets.append(token)
        index += 1
    return targets, has_scheme


def _command_fidelity_reasons(message: str, response: str) -> list[str]:
    reasons: list[str] = []
    commands = extract_commands(response)
    nmap_commands = [cmd for cmd in commands if cmd.casefold().startswith("nmap ")]

    if _requested_nmap(message):
        if not nmap_commands:
            reasons.append("requested_nmap_command_missing")
        else:
            observed_hosts = _observed_hosts(message)
            for command in nmap_commands:
                targets, has_scheme = _nmap_targets(command)
                if has_scheme:
                    reasons.append("nmap_target_must_be_host_not_url")
                if observed_hosts:
                    normalized_targets = {
                        target.split("/", 1)[0].split(":", 1)[0].rstrip(".").casefold()
                        for target in targets
                        if not target.casefold().startswith(("http://", "https://"))
                    }
                    if normalized_targets and not (normalized_targets & observed_hosts):
                        reasons.append("nmap_target_does_not_match_observed_host")

    for match in _NMAP_ALIAS_RE.finditer(response):
        label = " ".join(match.group(1).split()).casefold()
        if label not in {"nmap", "network mapper"}:
            reasons.append("invented_nmap_product_name")
            break

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
    reasons.extend(_command_fidelity_reasons(message, response))
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

    if "requested_nmap_command_missing" in reasons:
        additions.append(
            "o operador pediu Nmap: forneça um comando Nmap executável, sem trocar por outra ferramenta"
        )
    if "nmap_target_must_be_host_not_url" in reasons:
        additions.append(
            "Nmap recebe host/IP/CIDR como target; remova http:// ou https:// e use somente o hostname observado"
        )
    if "nmap_target_does_not_match_observed_host" in reasons:
        additions.append(
            "o target do comando Nmap deve corresponder exatamente ao host observado na mensagem do operador"
        )
    if "invented_nmap_product_name" in reasons:
        additions.append(
            "chame a ferramenta pelo nome canônico Nmap (Network Mapper); não invente produto, edição ou alias"
        )

    if not additions:
        return base
    return base + "\n\nCORREÇÕES DE FIDELIDADE DO COMANDO:\n" + "\n".join(
        f"- {item}." for item in additions
    )
