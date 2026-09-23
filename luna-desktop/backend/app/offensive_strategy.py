"""Context-aware offensive strategy scoring for operator-supervised Kali work.

This module does not execute anything. It scores proposed command strategy against
the operator context so a small local model can be steered by deterministic math
instead of generic tool defaults.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .command_ast import CommandAST


# High-value WEB APPLICATION profile. These are prioritization priors, not claims
# that a service is present. The model must still distinguish hypothesis from
# observed scan evidence.
WEB_APPLICATION_PORT_WEIGHTS: dict[int, float] = {
    80: 1.00,
    443: 1.00,
    8000: 0.86,
    8080: 0.96,
    8443: 0.93,
    9090: 0.80,
    10000: 0.76,
    3306: 0.74,
    5432: 0.80,
    1433: 0.70,
    27017: 0.77,
    6379: 0.82,
    11211: 0.64,
}

_WEB_MARKERS = (
    "http://", "https://", "web", "https", "http ", "api", "frontend",
    "aplicação web", "aplicacao web", "site", "servidor web",
)
_OPTIMIZE_MARKERS = (
    "otimiz", "maior valor", "alto valor", "mais relevantes", "principais portas",
    "portas relevantes", "foco", "focado", "cirúrg", "cirurg", "prioriz",
)


@dataclass(frozen=True)
class ContextualPortAssessment:
    profile: str
    selected_ports: tuple[int, ...]
    weighted_recall: float
    weighted_precision: float
    f_beta: float
    context_utility: float
    reasons: tuple[str, ...]


def is_web_application_context(value: str) -> bool:
    normalized = value.casefold()
    return any(marker in normalized for marker in _WEB_MARKERS)


def asks_high_value_port_optimization(value: str) -> bool:
    normalized = value.casefold()
    return any(marker in normalized for marker in _OPTIMIZE_MARKERS)


def recommended_web_ports() -> tuple[int, ...]:
    return tuple(WEB_APPLICATION_PORT_WEIGHTS)


def recommended_web_port_argument() -> str:
    return ",".join(str(port) for port in recommended_web_ports())


def _parse_explicit_ports(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()
    ports: set[int] = set()
    for part in value.split(","):
        token = part.strip()
        if not token:
            continue
        if re.fullmatch(r"\d{1,5}", token):
            number = int(token)
            if 1 <= number <= 65535:
                ports.add(number)
            continue
        range_match = re.fullmatch(r"(\d{1,5})-(\d{1,5})", token)
        if range_match:
            start, end = map(int, range_match.groups())
            if 1 <= start <= end <= 65535 and end - start <= 512:
                ports.update(range(start, end + 1))
    return tuple(sorted(ports))


def assess_nmap_port_strategy(context: str, ast: CommandAST) -> ContextualPortAssessment:
    """Score context fit using weighted F-beta and a small complexity penalty.

    For a WEB APPLICATION scan or optimization request:
      recall = weighted coverage of the high-value context profile
      precision = relevant weight / (relevant weight + 0.22 * irrelevant ports)
      F_beta uses beta=1.35 to favor useful coverage over extreme narrowness
      U_ctx = F_beta * exp(-0.012 * max(0, |P|-13))

    --top-ports receives a deterministic context penalty because it optimizes
    global service frequency rather than this application-specific profile.
    """
    normalized = context.casefold()
    applicable = (
        ast.tool == "nmap"
        and is_web_application_context(context)
        and (
            asks_high_value_port_optimization(context)
            or any(marker in normalized for marker in ("scan", "varredura", "nmap", "recon"))
        )
    )
    if not applicable:
        return ContextualPortAssessment("not_applicable", (), 1.0, 1.0, 1.0, 1.0, ())

    options = {option.casefold() for option in ast.options}
    values = {key.casefold(): value for key, value in ast.option_values}
    reasons: list[str] = []

    if "--top-ports" in options:
        reasons.append("nmap_top_ports_generic_for_web_context")
        return ContextualPortAssessment("web_application", (), 0.45, 0.60, 0.49, 0.441, tuple(reasons))

    selected = _parse_explicit_ports(values.get("-p"))
    if not selected:
        reasons.append("nmap_web_optimization_ports_not_explicit")
        return ContextualPortAssessment("web_application", (), 0.0, 0.0, 0.0, 0.0, tuple(reasons))

    total_weight = sum(WEB_APPLICATION_PORT_WEIGHTS.values())
    relevant_weight = sum(WEB_APPLICATION_PORT_WEIGHTS.get(port, 0.0) for port in selected)
    recall = relevant_weight / total_weight if total_weight else 1.0
    irrelevant = sum(1 for port in selected if port not in WEB_APPLICATION_PORT_WEIGHTS)
    precision_den = relevant_weight + 0.22 * irrelevant
    precision = relevant_weight / precision_den if precision_den else 0.0

    beta = 1.35
    beta2 = beta * beta
    denominator = beta2 * precision + recall
    f_beta = ((1.0 + beta2) * precision * recall / denominator) if denominator else 0.0
    complexity_penalty = math.exp(-0.012 * max(0, len(selected) - len(WEB_APPLICATION_PORT_WEIGHTS)))
    utility = f_beta * complexity_penalty

    minimum_recall = 0.45 if asks_high_value_port_optimization(context) else 0.28
    if recall < minimum_recall:
        reasons.append("nmap_web_port_profile_low_coverage")

    return ContextualPortAssessment(
        "web_application",
        selected,
        round(recall, 4),
        round(precision, 4),
        round(f_beta, 4),
        round(utility, 4),
        tuple(reasons),
    )


def nmap_context_guidance(context: str) -> str:
    if not is_web_application_context(context):
        return ""
    normalized = context.casefold()
    if not (
        asks_high_value_port_optimization(context)
        or any(marker in normalized for marker in ("scan", "varredura", "nmap", "recon"))
    ):
        return ""
    ports = recommended_web_port_argument()
    return (
        "WEB HIGH-VALUE PORT PROFILE (priorização, não evidência): prefira -p "
        f"{ports} em vez de limitar o baseline apenas a 80,443 ou usar --top-ports. "
        "A lista prioriza superfície web/admin e exposições de dados/cache; serviços só viram "
        "fatos depois do resultado do scan."
    )
