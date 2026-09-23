"""Lazy capability ranking for Luna Kali guidance.

The router does not execute tools. It ranks a small subset of the structured
Kali registry from current intent, target context and recent conversation so
the local model sees only relevant capabilities.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .kali_tool_dictionary import KALI_TOOL_DICTIONARY


_FAMILY_MARKERS: dict[str, tuple[str, ...]] = {
    "network": ("porta", "port", "scan", "rede", "host", "serviço", "servico"),
    "web": ("http", "https", "web", "api", "site", "endpoint", "frontend"),
    "dns": ("dns", "domínio", "dominio", "subdom", "registro", "record"),
    "tls": ("tls", "ssl", "certificado", "certificate", "https"),
    "windows": ("smb", "windows", "active directory", "share"),
    "authentication": ("login", "autentica", "credencial", "senha", "password"),
    "offline": ("hash", "digest", "arquivo de hash", "hash file"),
    "web_proxy": (
        "intercept", "interceptar", "interceptação", "interceptacao", "proxy",
        "requisição", "requisicao", "request", "replay", "http history",
    ),
    "packet_capture": (
        "pacote", "packet", "pcap", "sniff", "wireshark", "captura de rede",
        "capturar tráfego", "capturar trafego",
    ),
    "privacy": (
        "proxychains", "tor", "torsocks", "vpn", "wireguard", "openvpn",
        "privacidade", "anonim", "rastre", "túnel", "tunel", "socks5",
        "dns leak", "vazamento dns", "kill switch", "killswitch",
    ),
}

_SELECTION_MARKERS = (
    "outras possibilidades", "outras ferramentas", "qual ferramenta",
    "qual tool", "o que usar", "próximo", "proximo", "e agora",
    "continue", "mais eficiente", "melhor ferramenta", "melhor app",
    "interceptar", "interceptação", "interceptacao", "proxy",
    "mais algum", "mais alguma", "alternativa", "alternativas",
    "proxychains", "tor", "vpn", "wireguard", "openvpn", "privacidade",
    "anonim", "rastre", "túnel", "tunel", "dns leak", "kill switch",
)

_ALTERNATIVE_MARKERS = (
    "mais algum", "mais alguma", "outra ferramenta", "outras ferramentas",
    "outra opção", "outra opcao", "alternativa", "alternativas",
)


@dataclass(frozen=True)
class CapabilityCandidate:
    tool: str
    family: str
    purpose: str
    relevance: float
    continuity: float
    context_fit: float
    utility: float

    def to_prompt(self) -> str:
        return (
            f"{self.tool}[family={self.family},purpose={self.purpose},"
            f"U={self.utility:.3f},R={self.relevance:.2f},C={self.continuity:.2f}]"
        )


def _history_text(history: Sequence[Mapping[str, Any]]) -> str:
    parts: list[str] = []
    for item in history[-4:]:
        content = item.get("content", "")
        if isinstance(content, str):
            parts.append(content[:600])
    return "\n".join(parts)


def _family_scores(context: str) -> dict[str, float]:
    normalized = context.casefold()
    result: dict[str, float] = {}
    for family, markers in _FAMILY_MARKERS.items():
        hits = sum(marker in normalized for marker in markers)
        if hits:
            result[family] = min(1.0, 0.35 + 0.18 * hits)
    return result


def rank_capabilities(
    message: str,
    *,
    scenario=None,
    history: Sequence[Mapping[str, Any]] = (),
    limit: int = 4,
) -> tuple[CapabilityCandidate, ...]:
    """Rank relevant tools with a bounded multi-objective utility function."""
    history_text = _history_text(history)
    context_parts = [message]
    if scenario is not None:
        for attr in ("target", "current_goal", "environment", "last_result"):
            value = getattr(scenario, attr, None)
            if value:
                context_parts.append(str(value))
    context_parts.append(history_text)
    context = "\n".join(context_parts)
    family_scores = _family_scores(context)

    ranked: list[CapabilityCandidate] = []
    message_lower = message.casefold()
    history_lower = history_text.casefold()
    has_target = bool(getattr(scenario, "target", None)) if scenario is not None else False
    alternative_request = any(
        marker in message_lower for marker in _ALTERNATIVE_MARKERS
    )

    for name, spec in KALI_TOOL_DICTIONARY.items():
        explicit = 1.0 if name.casefold() in message_lower else 0.0
        family_fit = family_scores.get(spec.family, 0.0)
        continuity = 1.0 if name.casefold() in history_lower else 0.0
        target_fit = 0.65 if has_target else 0.25

        relevance = min(1.0, 0.72 * explicit + 0.56 * family_fit)
        context_fit = min(1.0, family_fit + 0.22 * target_fit)
        history_term = (-0.90 if alternative_request else 0.75) * continuity
        z = 2.2 * relevance + 1.15 * context_fit + history_term - 1.30
        utility = 1.0 / (1.0 + math.exp(-z))
        ranked.append(
            CapabilityCandidate(
                tool=name,
                family=spec.family,
                purpose=spec.purpose,
                relevance=round(relevance, 4),
                continuity=round(continuity, 4),
                context_fit=round(context_fit, 4),
                utility=round(utility, 4),
            )
        )

    ranked.sort(key=lambda item: (-item.utility, item.tool))
    return tuple(ranked[: max(1, limit)])


def capability_guidance(
    message: str,
    *,
    scenario=None,
    history: Sequence[Mapping[str, Any]] = (),
) -> str:
    normalized = message.casefold()
    if not any(marker in normalized for marker in _SELECTION_MARKERS):
        return ""
    candidates = rank_capabilities(
        message,
        scenario=scenario,
        history=history,
        limit=4,
    )
    if not candidates:
        return ""
    return (
        "KALI CAPABILITY ROUTER (candidatos, não ações automáticas): "
        + "; ".join(candidate.to_prompt() for candidate in candidates)
        + ". Escolha somente ferramentas cujos pré-requisitos factuais estejam satisfeitos. "
        "Para pedidos de recomendação, compare papéis técnicos antes de escolher: "
        "proxy de interceptação HTTP(S) != captura de pacotes. Restrições de entrega de "
        "turnos anteriores (por exemplo 'apenas um comando') não persistem se o turno atual "
        "não as repetir. Não emita comando quando o operador pediu apenas orientação."
    )
