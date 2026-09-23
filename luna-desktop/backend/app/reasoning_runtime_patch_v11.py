"""Eleventh-stage hardening: privacy-routing factual and transport validation.

V11 keeps privacy guidance operationally honest: no anonymity guarantees, no
silent direct fallback, no raw-socket-over-SOCKS fiction, and no invented
Proxychains/Tor configuration endpoints.
"""

from __future__ import annotations

import re
import shlex
from typing import Any

from . import reasoning_pipeline as _rp
from .network_privacy import privacy_intent
from .reasoning_runtime_patch_v10 import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)
from .reasoning_runtime_patch_v8 import extract_commands


_ANONYMITY_OVERCLAIM_RE = re.compile(
    r"(?is)(?:100%|totalmente|completamente|garant(?:e|ido|ida)|imposs[ií]vel)"
    r".{0,80}(?:rastre|identific|anonim|descobrir.{0,20}(?:ip|origem))"
)
_DIRECT_FALLBACK_RE = re.compile(
    r"(?is)(?:se|caso).{0,40}(?:tor|vpn|proxy).{0,40}(?:falh|cair|indispon)"
    r".{0,80}(?:sem proxy|diretamente|conex[aã]o direta|rota direta)"
)
_CONFIG_PATHS = ("/etc/proxychains4.conf", "/etc/proxychains.conf")
_SOCKS_ENDPOINT_RE = re.compile(r"(?<!\d)(?:127\.0\.0\.1|localhost)[:\s]+(?:9050|9150)(?!\d)", re.IGNORECASE)


def _scenario_facts(scenario: Any) -> str:
    parts: list[str] = []
    target = getattr(scenario, "target", None)
    if target:
        parts.append(str(target))
    parts.extend(str(item) for item in (getattr(scenario, "observed_facts", []) or []))
    return "\n".join(parts)


def _privacy_reasons(message: str, response: str, scenario: Any) -> list[str]:
    factual_context = f"{message}\n{_scenario_facts(scenario)}".casefold()
    response_lower = response.casefold()
    if not privacy_intent(f"{message}\n{response}"):
        return []

    reasons: list[str] = []
    if _ANONYMITY_OVERCLAIM_RE.search(response):
        reasons.append("privacy_anonymity_overclaim")
    if _DIRECT_FALLBACK_RE.search(response):
        reasons.append("privacy_direct_fallback_suggested")

    for path in _CONFIG_PATHS:
        if path in response_lower and path not in factual_context:
            reasons.append("privacy_unobserved_config_path")
            break
    if _SOCKS_ENDPOINT_RE.search(response) and not _SOCKS_ENDPOINT_RE.search(factual_context):
        reasons.append("privacy_unobserved_socks_endpoint")

    commands = extract_commands(response)
    for command in commands:
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError:
            tokens = command.split()
        lowered = [token.casefold() for token in tokens]
        wrapped_by_privacy = bool(
            lowered
            and lowered[0] in {"proxychains", "proxychains4", "torsocks"}
        )
        if wrapped_by_privacy and "nmap" in lowered:
            if any(flag in lowered for flag in ("-ss", "-su")):
                reasons.append("privacy_raw_socket_proxy_mismatch")

    if re.search(r"(?is)tor.{0,50}(?:suporta|transporta|proxy).{0,30}(?:udp|raw socket)", response):
        reasons.append("privacy_transport_overclaim")

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
    reasons.extend(_privacy_reasons(message, response, scenario))
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

    if "privacy_anonymity_overclaim" in reasons:
        additions.append("não prometa anonimato ou não-rastreabilidade; descreva redução de exposição e limitações")
    if "privacy_direct_fallback_suggested" in reasons:
        additions.append("quando a camada é obrigatória, falha de VPN/Tor/proxy deve ser fail-closed, não fallback direto")
    if "privacy_raw_socket_proxy_mismatch" in reasons:
        additions.append("Proxychains/Tor não tornam Nmap -sS/-sU/raw-socket proxyável; alinhe a técnica ao transporte realmente suportado")
    if "privacy_unobserved_config_path" in reasons:
        additions.append("detecte o path real de configuração antes de editar; não assuma /etc/proxychains*.conf")
    if "privacy_unobserved_socks_endpoint" in reasons:
        additions.append("detecte o listener SOCKS local antes de usar host/porta; não assuma 9050/9150")
    if "privacy_transport_overclaim" in reasons:
        additions.append("não afirme que Tor transporta UDP/raw sockets; diferencie TCP SOCKS de tráfego não suportado")

    if not additions:
        return base
    return base + "\n\nPRIVACY ROUTING HARDENING:\n" + "\n".join(
        f"- {item}." for item in additions
    )
