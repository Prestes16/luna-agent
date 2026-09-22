"""Structured command parsing for Luna's reasoning pipeline.

The validator should reason over command structure, not raw strings.  This module
provides a small deterministic AST for executable commands and a focused Nmap
strategy assessment used by later quality gates.
"""

from __future__ import annotations

import math
import re
import shlex
from dataclasses import dataclass
from typing import Iterable


_NMAP_VALUE_OPTIONS = {
    "-p", "--top-ports", "--exclude-ports", "--script", "--script-args",
    "-oN", "-oX", "-oG", "-oA", "-iL", "--exclude", "--dns-servers",
    "--source-port", "-g", "--max-retries", "--host-timeout", "--scan-delay",
    "--max-rate", "--min-rate", "-S", "-e", "-D", "--proxies",
}


@dataclass(frozen=True)
class CommandAST:
    raw: str
    tool: str
    argv: tuple[str, ...]
    options: tuple[str, ...]
    option_values: tuple[tuple[str, str], ...]
    positionals: tuple[str, ...]

    def has_option(self, *names: str) -> bool:
        wanted = {name.casefold() for name in names}
        return any(option.casefold() in wanted for option in self.options)

    def value_for(self, name: str) -> str | None:
        target = name.casefold()
        for key, value in self.option_values:
            if key.casefold() == target:
                return value
        return None


@dataclass(frozen=True)
class NmapStrategyAssessment:
    intent: str
    information_gain: float
    noise: float
    cost: float
    utility: float
    reasons: tuple[str, ...]


def parse_command(command: str) -> CommandAST | None:
    """Parse a shell command into a deterministic lightweight AST."""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not tokens:
        return None

    tool = tokens[0].casefold().removesuffix(".exe")
    options: list[str] = []
    option_values: list[tuple[str, str]] = []
    positionals: list[str] = []

    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--") and "=" in token:
            key, value = token.split("=", 1)
            options.append(key)
            option_values.append((key, value))
            index += 1
            continue

        if token in _NMAP_VALUE_OPTIONS and index + 1 < len(tokens):
            options.append(token)
            option_values.append((token, tokens[index + 1]))
            index += 2
            continue

        # Common compact Nmap forms such as -p80,443, -T4 and -oNscan.txt.
        compact_match = re.match(r"^(-p|-T|-oN|-oX|-oG|-oA)(.+)$", token)
        if compact_match:
            key, value = compact_match.groups()
            options.append(key)
            option_values.append((key, value))
            index += 1
            continue

        if token.startswith("-"):
            options.append(token)
            index += 1
            continue

        positionals.append(token)
        index += 1

    return CommandAST(
        raw=command,
        tool=tool,
        argv=tuple(tokens),
        options=tuple(options),
        option_values=tuple(option_values),
        positionals=tuple(positionals),
    )


def infer_nmap_intent(message: str) -> str:
    """Infer the operator's requested scan depth from explicit language only."""
    normalized = message.casefold()

    if any(marker in normalized for marker in (
        "agressivo", "aggressive", "scan completo", "varredura completa",
        "comprehensive", "detecção de os", "deteccao de os", "os detection",
    )) or re.search(r"(?<!\w)-A(?!\w)", message):
        return "comprehensive"

    if any(marker in normalized for marker in (
        "vulnerab", "--script=vuln", "script vuln", "cve", "vuln scan",
    )):
        return "vulnerability"

    if any(marker in normalized for marker in (
        "todas as portas", "todos os ports", "all ports", "full port", "-p-",
    )):
        return "full_ports"

    if any(marker in normalized for marker in (
        "descobrir hosts", "host discovery", "ping scan", "-sn",
    )):
        return "host_discovery"

    return "initial"


def _contains_option(ast: CommandAST, prefixes: Iterable[str]) -> bool:
    folded = tuple(option.casefold() for option in ast.options)
    return any(any(option == p.casefold() or option.startswith(p.casefold()) for p in prefixes) for option in folded)


def assess_nmap_strategy(message: str, ast: CommandAST) -> NmapStrategyAssessment:
    """Score Nmap strategy as information gain discounted by noise and cost.

    U = IG * exp(-(lambda_n * N + lambda_c * C))

    The score is contextual.  A noisy command can be appropriate when the
    operator explicitly requested a comprehensive/aggressive scan, but it should
    not be the default answer to a generic initial reconnaissance request.
    """
    if ast.tool != "nmap":
        return NmapStrategyAssessment("not_nmap", 1.0, 0.0, 0.0, 1.0, ())

    intent = infer_nmap_intent(message)
    options = {option.casefold() for option in ast.options}
    values = {key.casefold(): value.casefold() for key, value in ast.option_values}

    aggressive = "-a" in options
    service_detection = "-sv" in options or aggressive
    os_detection = "-o" in options or aggressive
    default_scripts = "-sc" in options or aggressive
    traceroute = "--traceroute" in options or aggressive
    full_ports = values.get("-p") == "-" or "-p-" in options
    vuln_scripts = "vuln" in values.get("--script", "")
    host_discovery_only = "-sn" in options

    # Information gain estimates are deliberately coarse and deterministic.
    information_gain = 0.52
    if service_detection:
        information_gain += 0.22
    if os_detection:
        information_gain += 0.08
    if default_scripts:
        information_gain += 0.07
    if traceroute:
        information_gain += 0.03
    if full_ports:
        information_gain += 0.06
    if vuln_scripts:
        information_gain += 0.08
    if host_discovery_only:
        information_gain = 0.42
    information_gain = min(1.0, information_gain)

    noise = 0.14
    cost = 0.16
    if service_detection:
        noise += 0.10
        cost += 0.12
    if os_detection:
        noise += 0.12
        cost += 0.10
    if default_scripts:
        noise += 0.18
        cost += 0.15
    if traceroute:
        noise += 0.05
        cost += 0.04
    if full_ports:
        noise += 0.18
        cost += 0.35
    if vuln_scripts:
        noise += 0.28
        cost += 0.30
    if aggressive:
        noise = max(noise, 0.82)
        cost = max(cost, 0.70)

    noise = min(1.0, noise)
    cost = min(1.0, cost)

    # For explicitly comprehensive/vulnerability scans, high noise is expected
    # and should not be penalized as a strategy mismatch.
    lambda_noise = 0.20 if intent in {"comprehensive", "vulnerability"} else 0.90
    lambda_cost = 0.25 if intent in {"comprehensive", "vulnerability", "full_ports"} else 0.60
    utility = information_gain * math.exp(-(lambda_noise * noise + lambda_cost * cost))

    reasons: list[str] = []
    if intent == "initial" and aggressive:
        reasons.append("nmap_overbroad_for_initial_recon")
    if intent == "initial" and vuln_scripts:
        reasons.append("nmap_vuln_scripts_not_requested")
    if intent == "host_discovery" and not host_discovery_only:
        reasons.append("nmap_strategy_misses_host_discovery_intent")

    return NmapStrategyAssessment(
        intent=intent,
        information_gain=round(information_gain, 4),
        noise=round(noise, 4),
        cost=round(cost, 4),
        utility=round(utility, 4),
        reasons=tuple(reasons),
    )
