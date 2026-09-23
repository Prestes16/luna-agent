"""Privacy-aware network routing guidance for supervised Kali operation.

This module does not claim anonymity and does not execute network changes. It
turns operator intent into deterministic routing advice with explicit leak,
transport, compatibility and fallback constraints.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass


_PRIVACY_SUBSTRING_MARKERS = (
    "proxychains", "proxychains4", "torsocks", "wireguard", "openvpn",
    "tunel", "túnel", "privacidade", "anonim", "rastre",
    "dns leak", "vazamento dns", "kill switch", "killswitch", "socks5",
)
_PRIVACY_WORD_MARKERS = ("tor", "vpn")

_TCP_WEB_MARKERS = (
    "http", "https", "web", "browser", "navegador", "curl", "ffuf", "gobuster",
    "feroxbuster", "httpx", "whatweb", "burp", "mitmproxy", "zaproxy",
)

_UDP_MARKERS = ("udp", "dns udp", "quic", "wireguard", "-su", "icmp")


@dataclass(frozen=True)
class PrivacyRouteProfile:
    name: str
    privacy: float
    compatibility: float
    latency_efficiency: float
    leak_resilience: float
    complexity: float
    supports_udp: bool
    notes: tuple[str, ...]


@dataclass(frozen=True)
class PrivacyRouteScore:
    profile: PrivacyRouteProfile
    utility: float
    mismatch_penalty: float
    reasons: tuple[str, ...]


PROFILES: tuple[PrivacyRouteProfile, ...] = (
    PrivacyRouteProfile(
        "vpn", 0.72, 0.95, 0.84, 0.82, 0.28, True,
        (
            "system-level routing is suitable for mixed TCP/UDP workloads",
            "privacy depends on provider policy and local leak controls",
        ),
    ),
    PrivacyRouteProfile(
        "tor", 0.90, 0.66, 0.44, 0.86, 0.34, False,
        (
            "Tor SOCKS is TCP-oriented; do not assume UDP/raw-socket coverage",
            "destination sees a Tor exit, not the operator source address",
        ),
    ),
    PrivacyRouteProfile(
        "proxychains_tor", 0.87, 0.62, 0.42, 0.88, 0.42, False,
        (
            "works only for applications whose connect calls can be proxied",
            "proxy_dns must be verified if DNS resolution should traverse the proxy chain",
        ),
    ),
    PrivacyRouteProfile(
        "vpn_then_tor", 0.93, 0.55, 0.30, 0.90, 0.62, False,
        (
            "higher complexity is not automatically higher effective privacy",
            "use only when the operator explicitly wants layered routing and validates each hop",
        ),
    ),
)


def _has_word(value: str, word: str) -> bool:
    """Unicode-safe token boundary check without regex lookaround ambiguity."""
    haystack = value.casefold()
    needle = word.casefold()
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index < 0:
            return False
        before = haystack[index - 1] if index > 0 else ""
        after_index = index + len(needle)
        after = haystack[after_index] if after_index < len(haystack) else ""
        before_is_word = bool(before) and (before.isalnum() or before == "_")
        after_is_word = bool(after) and (after.isalnum() or after == "_")
        if not before_is_word and not after_is_word:
            return True
        start = index + 1


def privacy_intent(value: str) -> bool:
    normalized = value.casefold()
    return (
        any(marker in normalized for marker in _PRIVACY_SUBSTRING_MARKERS)
        or any(_has_word(normalized, marker) for marker in _PRIVACY_WORD_MARKERS)
    )


def _mismatch_penalty(context: str, profile: PrivacyRouteProfile) -> tuple[float, list[str]]:
    normalized = context.casefold()
    reasons: list[str] = []
    penalty = 0.0

    if any(marker in normalized for marker in _UDP_MARKERS) and not profile.supports_udp:
        penalty += 0.85
        reasons.append("transport_requires_udp_or_raw_socket")

    if "nmap" in normalized and profile.name in {"tor", "proxychains_tor", "vpn_then_tor"}:
        if any(marker in normalized for marker in ("-ss", "-su", "syn", "raw socket")):
            penalty += 0.90
            reasons.append("nmap_raw_scan_not_proxyable_through_socks")
        elif "-st" not in normalized and "connect scan" not in normalized:
            penalty += 0.28
            reasons.append("nmap_proxy_mode_requires_connect_scan_semantics")

    if any(marker in normalized for marker in _TCP_WEB_MARKERS):
        if profile.name in {"tor", "proxychains_tor", "vpn_then_tor"}:
            penalty = max(0.0, penalty - 0.08)

    # Respect an explicitly requested route when the operator named one family.
    # If several families are mentioned, treat the turn as a comparison instead.
    named_families = {
        family
        for family, markers in {
            "proxychains": ("proxychains", "proxychains4"),
            "tor": ("tor", "torsocks"),
            "vpn": ("vpn", "openvpn", "wireguard", "wg-quick"),
        }.items()
        if any(
            (_has_word(normalized, marker) if marker in {"tor", "vpn"} else marker in normalized)
            for marker in markers
        )
    }
    if len(named_families) == 1:
        requested = next(iter(named_families))
        compatible_profiles = {
            "proxychains": {"proxychains_tor"},
            "tor": {"tor", "proxychains_tor", "vpn_then_tor"},
            "vpn": {"vpn", "vpn_then_tor"},
        }[requested]
        if profile.name not in compatible_profiles:
            penalty += 0.75
            reasons.append("explicit_route_family_mismatch")

    return min(1.0, penalty), reasons


def score_privacy_routes(context: str) -> tuple[PrivacyRouteScore, ...]:
    """Rank privacy routes with a multiplicative utility model.

    U = P^1.55 * C^1.10 * L^0.60 * R^1.35 * exp(-1.05*X - 0.70*K)

    P privacy prior, C compatibility, L latency efficiency, R leak resilience,
    X context mismatch, K operational complexity.
    """
    ranked: list[PrivacyRouteScore] = []
    for profile in PROFILES:
        mismatch, reasons = _mismatch_penalty(context, profile)
        utility = (
            profile.privacy ** 1.55
            * profile.compatibility ** 1.10
            * profile.latency_efficiency ** 0.60
            * profile.leak_resilience ** 1.35
            * math.exp(-1.05 * mismatch - 0.70 * profile.complexity)
        )
        ranked.append(
            PrivacyRouteScore(
                profile=profile,
                utility=round(utility, 4),
                mismatch_penalty=round(mismatch, 4),
                reasons=tuple(reasons),
            )
        )
    ranked.sort(key=lambda item: (-item.utility, item.profile.name))
    return tuple(ranked)


def best_privacy_route(context: str) -> PrivacyRouteScore:
    return score_privacy_routes(context)[0]


def privacy_guidance(context: str) -> str:
    if not privacy_intent(context):
        return ""

    ranked = score_privacy_routes(context)
    top = ranked[:3]
    ranking = "; ".join(
        f"{item.profile.name}[U={item.utility:.3f},mismatch={item.mismatch_penalty:.2f}]"
        for item in top
    )
    return (
        "PRIVACY ROUTING ENGINE (proteção de egress, não garantia de anonimato): "
        + ranking
        + ". Regras obrigatórias: nunca prometa não-rastreabilidade; confirme o caminho real "
        "do tráfego por aplicação; não faça fallback silencioso para conexão direta se VPN/Tor "
        "falhar; confirme DNS pelo mesmo caminho quando essa for a intenção; verifique IPv4 e "
        "IPv6 separadamente; portas SOCKS e paths de configuração devem ser detectados localmente, "
        "não inventados. Proxychains/Tor não transportam UDP/raw sockets: Nmap -sS/-sU/ICMP não "
        "devem ser tratados como proxyáveis; para aplicações TCP, valide compatibilidade antes. "
        "Camadas adicionais (VPN+Tor) só são recomendadas quando o ganho esperado supera custo, "
        "latência e risco operacional. Roteamento não remove identidade de aplicação: cookies, "
        "login em contas pessoais, fingerprint do navegador, WebRTC e correlação temporal devem "
        "ser tratados como superfícies separadas de privacidade."
    )


def privacy_configuration_guidance(context: str) -> str:
    """Return a deterministic configuration workflow for the requested layer."""
    if not privacy_intent(context):
        return ""

    normalized = context.casefold()
    phases = "DISCOVER -> CONFIGURE -> VERIFY -> FAIL-CLOSED -> ROLLBACK"
    rules: list[str] = [
        "DISCOVER: detect installed binary/service, active interfaces, current default route, DNS and IPv6 state before editing anything",
        "VERIFY: compare application egress, DNS path and IPv4/IPv6 behavior after each layer; do not infer success from service=active alone",
        "FAIL-CLOSED: if the requested privacy layer is mandatory, direct fallback must be treated as failure rather than success",
        "ROLLBACK: preserve the prior route/config and provide a reversible recovery step before persistent changes",
    ]

    if "proxychains" in normalized:
        rules.extend((
            "PROXYCHAINS: detect whether proxychains4 or proxychains is installed and locate its active config rather than assuming a fixed path",
            "PROXYCHAINS: verify chain mode, proxy_dns behavior and factual SOCKS endpoint; use only compatible TCP applications",
        ))
    if _has_word(normalized, "tor") or "torsocks" in normalized:
        rules.extend((
            "TOR: verify daemon/listener and local SOCKS endpoint; do not hardcode 9050 or 9150 without evidence",
            "TOR: do not route UDP/raw-socket operations through Tor wrappers; choose a compatible TCP workflow instead",
        ))
    if any(marker in normalized for marker in ("vpn", "openvpn", "wireguard", "wg-quick")):
        rules.extend((
            "VPN: require an operator-provided or observed profile/interface; never invent provider endpoints or credentials",
            "VPN: verify default route, DNS, IPv4/IPv6 and reconnect/failure behavior before calling the tunnel ready",
            "VPN: kill-switch/firewall changes must be explicit, reversible and scoped to the intended interface/profile",
        ))
    if _has_word(normalized, "tor") and _has_word(normalized, "vpn"):
        rules.append(
            "LAYER ORDER: VPN->Tor and Tor->VPN are not equivalent trust models; state the requested order explicitly and do not configure Tor->VPN unless the VPN/profile actually supports that transport"
        )
    if "nmap" in normalized and (
        "proxychains" in normalized
        or "torsocks" in normalized
        or _has_word(normalized, "tor")
    ):
        rules.append(
            "NMAP: SOCKS/proxy wrappers are incompatible with -sS/-sU/raw discovery; if proxying is required, use only connect-style semantics that are actually supported and verify target/DNS handling"
        )

    return "PRIVACY CONFIG WORKFLOW [" + phases + "]: " + " | ".join(rules)


def local_privacy_preflight_needed(context: str) -> bool:
    """True when local Tor/Proxychains prerequisites are explicitly unknown."""
    if not privacy_intent(context):
        return False
    normalized = context.casefold()
    unknown_markers = (
        "não sei se", "nao sei se", "não confirmado", "nao confirmado",
        "não confirmei", "nao confirmei", "não sei qual", "nao sei qual",
        "desconheço", "desconheco", "unknown",
    )
    local_markers = (
        "instalad", "arquivo de configuração", "arquivo de configuracao",
        "config", "porta socks", "socks", "listener", "binário", "binario",
    )
    return (
        any(marker in normalized for marker in unknown_markers)
        and any(marker in normalized for marker in local_markers)
        and ("proxychains" in normalized or _has_word(normalized, "tor"))
    )


def privacy_preflight_guidance(context: str) -> str:
    """Deterministic first-step rules for unknown local privacy prerequisites."""
    if not local_privacy_preflight_needed(context):
        return ""

    return (
        "LOCAL PRIVACY PREFLIGHT: a remote target/base URL is NOT required to discover local "
        "Tor/Proxychains prerequisites. Do not ask for the target before this local inventory. "
        "The first step must be read-only and should discover the available binaries for tor, "
        "proxychains4 and proxychains without assuming which Proxychains variant exists. Prefer "
        "one local inventory command: command -v tor proxychains4 proxychains. Explain that "
        "this proves only binary presence/on-PATH; it does NOT prove package health, active "
        "service, config path, chain mode, proxy_dns, SOCKS listener or correct routing. Ask for "
        "the remote target only later, when an actual egress/application validation requires it."
    )

def privacy_tooling_summary() -> str:
    return (
        "Ferramentas conhecidas: proxychains4/proxychains (encadeamento por connect), "
        "tor/torsocks (egress TCP via Tor), WireGuard/wg-quick e OpenVPN (túnel de sistema). "
        "Configuração deve preservar rota/DNS esperados e ser verificada de forma fail-closed."
    )
