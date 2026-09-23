"""Eighth-stage hardening: operational command policy and integrity metadata.

Stage 7 scores strategy. Stage 8 makes operator-readiness deterministic: commands
may be wrapped with sudo, privilege-sensitive Nmap modes must request elevation,
and output artifacts are enforced only when the operator explicitly requested
persistence. The exact approved command is also SHA-256 attestable.
"""

from __future__ import annotations

import re
from typing import Any

from . import reasoning_pipeline as _rp
from .command_policy import assess_command_policy, effective_tool, parse_effective_command
from .reasoning_runtime_patch_v7 import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)


_FENCE_RE = re.compile(r"```(?P<label>[A-Za-z0-9_+.-]*)[ \t]*(?P<body>.*?)```", re.DOTALL)
_INLINE_CURL_RE = re.compile(
    r"(?im)(?:^\s*(?:[-*]\s*)?|"
    r"\b(?:comando|command)(?:\s+(?:único|unico|sugerido|recomendado))?"
    r"\s*(?:\([^\r\n)]*\))?\s*:?\s*[*_`]*\s*|`)"
    r"((?:sudo\s+)?curl(?:\.exe)?\s+[^\r\n`]+)"
)
_EXEC_RE = re.compile(
    r"^(?:sudo(?:\s+(?:-[A-Za-z]+|--[^\s]+))*\s+)?"
    r"(?:curl(?:\.exe)?|wget|http|httpie|nmap|masscan|rustscan|ffuf|gobuster|"
    r"feroxbuster|dirsearch|nikto|nuclei|sqlmap|wpscan|dig|nslookup|dnsenum|"
    r"dnsrecon|amass|subfinder|traceroute|ping|whatweb|httpx|enum4linux(?:-ng)?|"
    r"smbclient|netexec|crackmapexec|hydra|medusa|john|hashcat|searchsploit|"
    r"sslscan|testssl|tcpdump|tshark|rpcclient|ldapsearch|burpsuite|mitmproxy|"
    r"mitmweb|zaproxy|wireshark|proxychains4|proxychains|tor|torsocks|openvpn|"
    r"wg-quick|wg|file|sha256sum|strings|xxd|yara|capa|floss|rizin|radare2|objdump|readelf|binwalk|"
    r"volatility3|vol|olevba|apktool|jadx|wine|java|dotnet|mono|wscript|cscript|"
    r"msfconsole|python(?:3)?|pwsh|"
    r"powershell|invoke-webrequest|iwr|apt|apt-get|dnf|yum|pacman|rm|rmdir|shred|mkfs(?:\.[a-z0-9]+)?|"
    r"wipefs|fdisk|cfdisk|sfdisk|parted|dd|chmod|chown|systemctl|nft|iptables|"
    r"ufw|firewall-cmd|ip|route|resolvectl|tee|sed|cp|mv|mount|umount|"
    r"grub-install|grub-mkconfig|update-grub|efibootmgr|reg(?:\.exe)?|bcdedit|"
    r"bootrec|bootsect|diskpart|format(?:\.com)?|schtasks|sc(?:\.exe)?)\b",
    re.IGNORECASE,
)


def extract_commands(response: str) -> list[str]:
    """Canonical command extraction with an optional sudo wrapper."""
    commands: list[str] = []
    for match in _FENCE_RE.finditer(response):
        body = re.sub(r"\\\s*\r?\n\s*", " ", match.group("body"))
        for line in body.splitlines() or [body]:
            compact = line.strip()
            if compact.startswith("$ "):
                compact = compact[2:].lstrip()
            if compact.startswith("PS> "):
                compact = compact[4:].lstrip()
            if compact and not compact.startswith("#") and _EXEC_RE.match(compact):
                commands.append(compact)

    if not commands:
        commands.extend(match.group(1).strip().strip("`") for match in _INLINE_CURL_RE.finditer(response))
    return list(dict.fromkeys(commands))


def _operational_reasons(message: str, response: str) -> list[str]:
    reasons: list[str] = []
    for command in extract_commands(response):
        assessment = assess_command_policy(message, command)
        if assessment.effective_tool != "nmap":
            continue
        if assessment.requires_elevation and not assessment.has_sudo:
            reasons.append("nmap_privileged_mode_missing_sudo")
        if assessment.artifact_required and not assessment.artifact_present:
            reasons.append("nmap_scan_artifact_missing")
        if assessment.expected_targets and not assessment.target_verified:
            reasons.append("command_policy_target_not_verified")
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
    commands = extract_commands(response)

    # Earlier stages predate sudo-aware parsing.  Reconcile stale tool-detection
    # failures when the effective executable still matches the operator contract.
    effective_tools = [effective_tool(command) for command in commands]
    if effective_tools and all(tool == "nmap" for tool in effective_tools):
        reasons = [
            reason for reason in reasons
            if reason not in {"requested_nmap_command_missing", "critical_tool_veto"}
        ]

    reasons.extend(_operational_reasons(message, response))
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
        command_count=len(commands),
    )


def build_replan_instruction(validation, scenario_prompt: str, current_message: str = "") -> str:
    base = _previous_build_replan(validation, scenario_prompt, current_message)
    reasons = set(validation.reasons)
    additions: list[str] = []

    # Output paths are operator-controlled. Never invent a filename merely
    # because a scan command was requested.
    sample = assess_command_policy(current_message, "nmap target.invalid")
    artifact = sample.recommended_artifact

    if "nmap_privileged_mode_missing_sudo" in reasons:
        additions.append(
            "o modo Nmap escolhido usa recursos privilegiados/raw sockets: prefixe o comando com sudo antes de aprová-lo"
        )
    if "nmap_scan_artifact_missing" in reasons:
        if artifact:
            additions.append(
                f"o operador pediu persistência e informou este artefato: use literalmente {artifact}; não invente outro caminho"
            )
        else:
            additions.append(
                "o operador pediu persistência, mas nenhum caminho/nome de arquivo factual foi observado; não invente .txt nem path"
            )
    if "command_policy_target_not_verified" in reasons:
        additions.append(
            "copie literalmente o alvo factual do contrato operacional; o policy engine não verificou o target do comando"
        )

    if not additions:
        return base
    return base + "\n\nPOLÍTICA OPERACIONAL DETERMINÍSTICA:\n" + "\n".join(
        f"- {item}." for item in additions
    )


def command_attestations(message: str, response: str) -> list[dict]:
    """Return UI-safe attestations for exact executable commands in a response."""
    return [assess_command_policy(message, command).to_dict() for command in extract_commands(response)]
