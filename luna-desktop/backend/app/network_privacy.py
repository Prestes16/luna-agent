"""Privacy-aware network routing guidance for supervised Kali operation.

This module does not claim anonymity and does not execute network changes. It
turns operator intent into deterministic routing advice with explicit leak,
transport, compatibility and fallback constraints.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


_PRIVACY_MARKERS = (
    "proxychains", "proxychains4", "tor", "torsocks", "vpn", "wireguard",
    "openvpn", "tunel", "túnel", "privacidade", "anonim", "rastre",
    "dns leak", "vazamento dns", "kill switch", "killswitch", "socks5",
)

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


def privacy_intent(value: str) -> bool:
    normalized = value.casefold()
    return any(marker in normalized for marker in _PRIVACY_MARKERS)


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
        "latência e risco operacional."
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
    if "tor" in normalized or "torsocks" in normalized:
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
    if "nmap" in normalized and any(marker in normalized for marker in ("proxychains", "tor", "torsocks")):
        rules.append(
            "NMAP: SOCKS/proxy wrappers are incompatible with -sS/-sU/raw discovery; if proxying is required, use only connect-style semantics that are actually supported and verify target/DNS handling"
        )

    return "PRIVACY CONFIG WORKFLOW [" + phases + "]: " + " | ".join(rules)


def privacy_tooling_summary() -> str:
    return (
        "Ferramentas conhecidas: proxychains4/proxychains (encadeamento por connect), "
        "tor/torsocks (egress TCP via Tor), WireGuard/wg-quick e OpenVPN (túnel de sistema). "
        "Configuração deve preservar rota/DNS esperados e ser verificada de forma fail-closed."
    )
