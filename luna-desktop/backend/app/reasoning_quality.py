"""Quantitative quality scoring for Luna's model-first pipeline.

This module does not try to replace the language model.  It converts explicit
operator intent into a small contract and scores the model response on the
properties that matter most for a technical copilot: instruction fidelity,
target fidelity, command executability, factual discipline, and calibration.

The score uses a weighted geometric mean followed by logistic calibration.  The
multiplicative form is deliberate: one near-zero critical dimension (for example
using the wrong tool or the wrong target) should pull the total score down much
more strongly than several cosmetic strengths can pull it up.
"""

from __future__ import annotations

import math
import re
import shlex
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlsplit

from .reasoning_runtime_patch import extract_commands


_KNOWN_TOOLS = (
    "nmap", "masscan", "rustscan", "curl", "wget", "httpx", "whatweb",
    "ffuf", "gobuster", "feroxbuster", "dirsearch", "nikto", "nuclei",
    "sqlmap", "wpscan", "dig", "nslookup", "dnsenum", "dnsrecon", "amass",
    "subfinder", "traceroute", "ping", "enum4linux", "enum4linux-ng",
    "smbclient", "netexec", "crackmapexec", "hydra", "medusa", "john",
    "hashcat", "searchsploit", "msfconsole", "sslscan", "testssl", "tcpdump",
    "tshark", "rpcclient", "ldapsearch", "burpsuite", "mitmproxy", "mitmweb",
    "zaproxy", "wireshark", "proxychains4", "proxychains", "tor", "torsocks",
    "openvpn", "wg-quick", "wg", "yara", "capa", "floss", "rizin", "radare2",
    "file", "sha256sum", "strings", "xxd", "objdump", "readelf", "binwalk",
    "volatility3", "vol", "olevba", "apktool", "jadx", "wine", "java", "dotnet",
    "mono", "wscript", "cscript",
)
_URL_RE = re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE)


@dataclass(frozen=True)
class OperatorContract:
    requested_tool: str | None
    target_hosts: tuple[str, ...]
    wants_command: bool
    wants_bash: bool
    one_command: bool
    operator_executes: bool

    @property
    def active(self) -> bool:
        return bool(self.requested_tool or self.wants_command or self.target_hosts)

    def to_prompt(self) -> str:
        parts: list[str] = []
        if self.requested_tool:
            parts.append(f"ferramenta={self.requested_tool}")
        if self.target_hosts:
            parts.append("targets_observados=" + ",".join(self.target_hosts))
        if self.wants_command:
            parts.append("entrega=comando_executavel")
        if self.wants_bash:
            parts.append("shell=bash")
        if self.one_command:
            parts.append("quantidade_comandos=1")
        if self.operator_executes:
            parts.append("execucao=operador")
        return "; ".join(parts)


@dataclass(frozen=True)
class QualityScore:
    total: float
    raw_geometric: float
    components: dict[str, float]
    contract: OperatorContract


def _contains_tool_name(value: str, tool: str) -> bool:
    haystack = value.casefold()
    needle = tool.casefold()
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index < 0:
            return False
        before = haystack[index - 1] if index > 0 else ""
        after_index = index + len(needle)
        after = haystack[after_index] if after_index < len(haystack) else ""
        before_blocked = bool(before) and (before.isalnum() or before in "_.-")
        after_blocked = bool(after) and (after.isalnum() or after in "_-")
        if not before_blocked and not after_blocked:
            return True
        start = index + 1


def _requested_tool(message: str) -> str | None:
    normalized = message.casefold()
    for tool in sorted(_KNOWN_TOOLS, key=len, reverse=True):
        if _contains_tool_name(normalized, tool):
            return tool
    return None

def _target_hosts(message: str) -> tuple[str, ...]:
    hosts: list[str] = []
    for url in _URL_RE.findall(message):
        try:
            parsed = urlsplit(url.strip("`'\".,;"))
        except ValueError:
            continue
        if parsed.hostname:
            hosts.append(parsed.hostname.casefold())

    for match in re.finditer(
        r"(?i)\b(?:alvo|target|host|dom[ií]nio)\s*(?:é|e|:)?\s*"
        r"([A-Za-z0-9][A-Za-z0-9.-]*(?::\d+)?)",
        message,
    ):
        value = match.group(1).split(":", 1)[0].rstrip(".").casefold()
        if value and "." in value:
            hosts.append(value)

    return tuple(dict.fromkeys(hosts))


def build_operator_contract(message: str) -> OperatorContract:
    normalized = message.casefold()
    strong_command_request = any(
        marker in normalized
        for marker in (
            "me dê o comando", "me de o comando", "forneça o comando", "forneca o comando",
            "forneça exatamente um comando", "forneca exatamente um comando",
            "apenas um comando", "somente um comando", "exatamente um comando",
            "um único comando", "um unico comando", "um comando bash", "o comando bash",
            "pra eu executar", "para eu executar",
        )
    )
    negated_command_request = bool(
        re.search(
            r"(?is)\b(?:não|nao|sem|do not|don't|without)\b.{0,48}"
            r"\b(?:execut(?:e|ar)|rod(?:e|ar)|forne[cç](?:a|er)|ger(?:e|ar)|produza|"
            r"run|execute|provide|generate|give)\b.{0,48}"
            r"\b(?:comando|comandos|command|commands)\b",
            normalized,
        )
        or re.search(
            r"(?is)\b(?:não|nao)\s+(?:quero|preciso)\b.{0,32}"
            r"\b(?:comando|comandos|command|commands)\b",
            normalized,
        )
    )
    generic_command_signal = any(
        marker in normalized
        for marker in ("comando", "command", "rode", "rodar", "execute")
    )
    wants_command = strong_command_request or (
        generic_command_signal and not negated_command_request
    )
    wants_bash = "bash" in normalized or "kali" in normalized
    one_command = any(
        marker in normalized
        for marker in (
            "apenas um comando", "somente um comando", "exatamente um comando",
            "um único comando", "um unico comando", "um comando bash", "o comando bash",
        )
    )
    operator_executes = any(
        marker in normalized
        for marker in ("pra eu executar", "para eu executar", "eu executo", "no meu kali")
    )
    return OperatorContract(
        requested_tool=_requested_tool(message),
        target_hosts=_target_hosts(message),
        wants_command=wants_command,
        wants_bash=wants_bash,
        one_command=one_command,
        operator_executes=operator_executes,
    )


def _command_tool(command: str) -> str:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    if not tokens:
        return ""
    return tokens[0].casefold().removesuffix(".exe")


def _command_mentions_host(command: str, hosts: Iterable[str]) -> bool:
    normalized = command.casefold()
    return any(host in normalized for host in hosts)


def _weighted_geometric_mean(components: dict[str, float], weights: dict[str, float]) -> float:
    eps = 0.03
    weighted_log = 0.0
    total_weight = 0.0
    for name, weight in weights.items():
        value = max(eps, min(1.0, float(components.get(name, 1.0))))
        weighted_log += weight * math.log(value)
        total_weight += weight
    if total_weight <= 0:
        return 1.0
    return math.exp(weighted_log / total_weight)


def _logistic(value: float, midpoint: float = 0.72, slope: float = 10.0) -> float:
    return 1.0 / (1.0 + math.exp(-slope * (value - midpoint)))


def score_response_quality(
    message: str,
    response: str,
    validation_reasons: Iterable[str] = (),
) -> QualityScore:
    """Score response quality in [0, 1] against explicit operator intent.

    This score is a reliability signal, not a truth oracle.  Existing hard
    validators remain authoritative for concrete hallucinations and unsafe
    regressions; the score catches combinations of smaller instruction failures.
    """
    contract = build_operator_contract(message)
    reasons = set(validation_reasons)
    commands = extract_commands(response)

    command_presence = 1.0
    tool_fidelity = 1.0
    target_fidelity = 1.0
    cardinality = 1.0

    if contract.wants_command:
        command_presence = 1.0 if commands else 0.0
    if contract.requested_tool and contract.wants_command:
        tool_fidelity = (
            1.0
            if commands and all(_command_tool(command) == contract.requested_tool for command in commands)
            else 0.0
        )
    if contract.target_hosts and commands:
        target_fidelity = 1.0 if all(
            _command_mentions_host(command, contract.target_hosts) for command in commands
        ) else 0.0
    elif contract.target_hosts and contract.wants_command:
        target_fidelity = 0.0

    if contract.one_command:
        cardinality = 1.0 if len(commands) == 1 else 0.0

    factual_penalties = {
        "unobserved_endpoint_mentioned",
        "invented_input_not_observed",
        "invented_role_mutation",
        "status_claim_for_untested_endpoint",
        "unsupported_client_behavior_claim",
    }
    calibration_penalties = {
        "definitive_outcome_for_untested_endpoint",
        "regressed_to_root_baseline_after_large_delta",
        "proposed_action_already_resolved",
    }
    command_penalties = {
        "requested_nmap_command_missing",
        "nmap_target_must_be_host_not_url",
        "nmap_target_does_not_match_observed_host",
        "invented_nmap_product_name",
        "invalid_curl_target",
        "unknown_curl_option",
    }

    factual_discipline = 0.0 if reasons & factual_penalties else 1.0
    uncertainty_calibration = 0.0 if reasons & calibration_penalties else 1.0
    command_correctness = 0.0 if reasons & command_penalties else 1.0

    components = {
        "instruction_fidelity": min(command_presence, tool_fidelity),
        "target_fidelity": target_fidelity,
        "command_correctness": command_correctness,
        "factual_discipline": factual_discipline,
        "uncertainty_calibration": uncertainty_calibration,
        "command_cardinality": cardinality,
    }
    weights = {
        "instruction_fidelity": 0.24,
        "target_fidelity": 0.20,
        "command_correctness": 0.22,
        "factual_discipline": 0.18,
        "uncertainty_calibration": 0.10,
        "command_cardinality": 0.06,
    }
    raw = _weighted_geometric_mean(components, weights)
    calibrated = _logistic(raw)
    return QualityScore(
        total=round(calibrated, 4),
        raw_geometric=round(raw, 4),
        components=components,
        contract=contract,
    )


def quality_replan_instruction(message: str, score: QualityScore) -> str:
    contract = score.contract
    requirements: list[str] = []
    if contract.requested_tool:
        requirements.append(
            f"use exatamente a ferramenta pedida pelo operador: {contract.requested_tool}; não renomeie nem substitua"
        )
    if contract.target_hosts:
        requirements.append(
            "preserve exatamente o target observado: " + ", ".join(contract.target_hosts)
        )
    if contract.requested_tool == "nmap" and contract.target_hosts:
        requirements.append(
            "Nmap recebe hostname/IP/CIDR como target; não inclua http://, https:// nem path de URL no argumento de alvo"
        )
    if contract.wants_command:
        requirements.append("entregue um comando realmente executável, sem placeholder inventado")
    if contract.one_command:
        requirements.append("entregue exatamente um comando")
    if contract.wants_bash:
        requirements.append("formate o comando em bloco bash")
    if contract.operator_executes:
        requirements.append("não alegue que o comando já foi executado; o operador fará a execução")

    weak = [name for name, value in score.components.items() if value < 0.5]
    if weak:
        requirements.append("corrija especificamente estas dimensões: " + ", ".join(weak))

    return (
        "CONTRATO OPERACIONAL DETERMINÍSTICO:\n"
        + ("\n".join(f"- {item}." for item in requirements) if requirements else "- siga literalmente a demanda atual.")
        + f"\n- score anterior={score.total:.4f}; reescreva para maximizar fidelidade sem inventar fatos."
    )
