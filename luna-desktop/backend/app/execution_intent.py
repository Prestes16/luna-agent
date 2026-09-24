"""Deterministic execution-intent and capability-authority model.

Luna Cyber is a supervised copilot. This module classifies the semantics of a
proposed command before any future executor sees it. It does not execute tools.

Authority levels:
- AUTO: local low-impact observation capability;
- ON_DEMAND: active probe inside operator-defined scope;
- APPROVAL_REQUIRED: mutation, privilege or high-impact action;
- BLOCKED: current host/scope invariants do not permit recommendation/execution.

The current build remains instruction-only; this model is the contract that a
future supervised executor must satisfy.
"""

from __future__ import annotations

import math
import re
import shlex
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from .command_execution import assess_command_execution
from .host_safety import assess_host_safety
from .kali_tool_dictionary import execution_baseline_for_tool


L0_OBSERVE = "L0_OBSERVE"
L1_PROBE = "L1_PROBE"
L2_MUTATE = "L2_MUTATE"
L3_HIGH_IMPACT = "L3_HIGH_IMPACT"

AUTO = "AUTO"
ON_DEMAND = "ON_DEMAND"
APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
BLOCKED = "BLOCKED"

_LEVEL_RANK = {
    L0_OBSERVE: 0,
    L1_PROBE: 1,
    L2_MUTATE: 2,
    L3_HIGH_IMPACT: 3,
}

_LOCAL_OBSERVE_TOOLS = frozenset(
    {
        "cat", "head", "tail", "grep", "rg", "find", "ls", "pwd", "which",
        "whereis", "command", "type", "id", "whoami", "uname", "hostname",
        "ip", "ss", "netstat", "route", "resolvectl", "systemctl", "journalctl",
        "ps", "pgrep", "file", "sha256sum", "sha512sum", "md5sum", "strings",
        "xxd", "readelf", "objdump", "yara", "capa", "floss", "rizin", "radare2",
        "binwalk", "volatility3", "vol", "olevba", "apktool", "jadx", "wg",
        "apt", "apt-get",
    }
)

_INTERPRETER_OR_SHELL_TOOLS = frozenset(
    {
        "sh", "bash", "zsh", "dash", "fish", "python", "python3", "perl", "ruby",
        "php", "node", "pwsh", "powershell", "cmd", "wscript", "cscript",
    }
)

_ACTIVE_PROBE_TOOLS = frozenset(
    {
        "nmap", "curl", "wget", "httpx", "whatweb", "nikto", "ffuf", "gobuster",
        "feroxbuster", "dig", "nslookup", "host", "whois", "sslscan", "testssl",
        "tshark", "tcpdump", "sqlmap", "hydra", "smbclient", "rpcclient",
        "ldapsearch", "snmpwalk", "nc", "netcat",
    }
)

_HIGH_IMPACT_TOOLS = frozenset(
    {
        "msfconsole", "msfvenom", "chisel", "socat",
        *_INTERPRETER_OR_SHELL_TOOLS,
    }
)

_HIGH_IMPACT_PATTERNS = (
    re.compile(r"(?i)\b(?:reverse[_ -]?shell|bind[_ -]?shell|meterpreter)\b"),
    re.compile(r"(?i)\bexploit/"),
    re.compile(r"(?i)\b(?:cron|crontab|systemd|rc\.local)\b.*\b(?:persist|enable|write|append)\b"),
    re.compile(r"(?i)\b(?:setuid|suid)\b.*\b(?:chmod|cp|install)\b"),
)

_HTTP_MUTATION_PATTERNS = (
    re.compile(r"(?i)\bcurl\b.*(?:\s-X\s*(?:POST|PUT|PATCH|DELETE)\b)"),
    re.compile(r"(?i)\bcurl\b.*(?:\s--request\s+(?:POST|PUT|PATCH|DELETE)\b)"),
    re.compile(r"(?i)\bcurl\b.*(?:\s(?:-d|--data|--data-raw|--data-binary|--json)\b)"),
    re.compile(r"(?i)\bcurl\b.*(?:\s(?:-T|--upload-file)\b)"),
)

_OPERATOR_EXECUTION_PATTERNS = (
    re.compile(r"(?i)\b(?:execute|executa|execute-a|rode|roda|rodar|use|usar|teste|testa|explore|explorar|valide|validar|comprove|comprovar|reproduza|reproduzir)\b"),
    re.compile(r"(?i)\b(?:vamos|pode|quero)\s+(?:executar|rodar|usar|testar|explorar|validar|comprovar|reproduzir)\b"),
)

_TOOL_HIGH_IMPACT_PATTERNS = (
    re.compile(r"(?i)\bnmap\b.*--script(?:=|\s+)[^\n]*(?:exploit|dos|intrusive)"),
    re.compile(r"(?i)\bsqlmap\b.*--(?:os-shell|os-pwn|sql-shell|file-write|file-dest)\b"),
    re.compile(r"(?i)\b(?:nc|netcat|ncat)\b[^\n]*\s-e\s"),
)

_ARTIFACT_EXECUTION_MARKERS = (
    "poc", "proof of concept", "prova de conceito", "exploit", "reproducer",
    "comprovar achado", "validar achado", "reproduzir vulnerabilidade", "crash",
)


def _explicit_artifact_execution(tool: str, context: str) -> bool:
    """Recognize an operator-scoped PoC/reproducer artifact as L3, never as unknown-safe."""
    normalized_tool = str(tool or "").strip()
    pathish = (
        normalized_tool.startswith(("./", "../", "/"))
        or "\\" in normalized_tool
        or normalized_tool.casefold().endswith((".exe", ".elf", ".bin"))
    )
    if not pathish:
        return False
    normalized_context = str(context or "").casefold()
    return any(marker in normalized_context for marker in _ARTIFACT_EXECUTION_MARKERS)



@dataclass(frozen=True)
class ExecutionIntent:
    command: str
    tool: str
    target: str | None
    capability: str
    authority_level: str
    authority: str
    expected_effect: str
    evidence_expected: tuple[str, ...]
    privilege_required: bool
    mutates_state: bool
    persistent_change: bool
    destructive: bool
    rollback_required: bool
    verification_required: bool
    risk_index: float
    readiness_index: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def operator_requested_execution(text: str) -> bool:
    """Conservative current-turn execution intent detector."""
    return any(pattern.search(text or "") for pattern in _OPERATOR_EXECUTION_PATTERNS)


def _target_from_command(command: str) -> str | None:
    url = re.search(r"(?i)\bhttps?://[^\s'\"<>]+", command)
    if url:
        try:
            parsed = urlsplit(url.group(0))
            return parsed.hostname or url.group(0)
        except ValueError:
            return url.group(0)

    ipv4 = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", command)
    if ipv4:
        return ipv4.group(0)

    domain = re.search(
        r"(?i)(?<![/\\\w-])(?:[a-z0-9-]+\.)+[a-z]{2,63}(?![\w-])",
        command,
    )
    if domain:
        return domain.group(0)
    return None


def _normalize_scope_target(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if text.casefold().startswith(("http://", "https://")):
        try:
            return urlsplit(text).hostname
        except ValueError:
            return None
    return _target_from_command(text) or text.casefold().strip("[]")


def _effective_tool(command: str) -> str:
    tokens = _tokens(command)
    if not tokens:
        return ""
    if tokens[0].casefold() != "sudo":
        return tokens[0].casefold()
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            break
        if token in {"-u", "--user", "-g", "--group", "-h", "--host"} and index + 1 < len(tokens):
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        break
    return tokens[index].casefold() if index < len(tokens) else ""


def _is_high_impact_command(command: str, tool: str) -> bool:
    lowered = command.casefold()
    return (
        tool in _HIGH_IMPACT_TOOLS
        or any(pattern.search(command) for pattern in _HIGH_IMPACT_PATTERNS)
        or any(pattern.search(command) for pattern in _TOOL_HIGH_IMPACT_PATTERNS)
        or "privilege escalation" in lowered
        or "persistência" in lowered
        or "persistence" in lowered
    )


def _semantic_remote_mutation(command: str) -> bool:
    """Detect target-state mutation that generic local lifecycle analysis cannot see."""
    return any(pattern.search(command) for pattern in _HTTP_MUTATION_PATTERNS)


def _risk_index(*, lifecycle, host, active_probe: bool, semantic_mutation: bool,
                high_impact_semantic: bool) -> float:
    """Bounded nonlinear risk index.

    This is not a probability of compromise. It is a monotone engineering index:
    R = 1 - Π(1 - w_i*x_i), with x_i in {0,1} plus the existing host-risk term.
    Independent severe dimensions therefore compound without allowing a single
    benign dimension to cancel a dangerous one.
    """
    dimensions = (
        (0.14, active_probe),
        (0.24, lifecycle.privilege_required),
        (0.38, lifecycle.mutates_state or semantic_mutation),
        (0.52, lifecycle.persistent_change),
        (0.82, lifecycle.destructive),
        (0.58, not lifecycle.reversible),
        (0.60, high_impact_semantic),
    )
    survival = 1.0 - min(1.0, max(0.0, float(host.risk)))
    for weight, active in dimensions:
        if active:
            survival *= 1.0 - weight
    return round(1.0 - survival, 4)


def _readiness_index(*, scope_confirmed: bool, operator_requested: bool, rollback_ready: bool,
                     target_bound: bool, verification_ready: bool, authority_level: str) -> float:
    """Weighted geometric readiness score with critical-floor penalty."""
    dimensions = {
        "scope": 1.0 if scope_confirmed else 0.20,
        "operator": 1.0 if operator_requested else 0.25,
        "rollback": 1.0 if rollback_ready else (0.45 if authority_level == L0_OBSERVE else 0.18),
        "target": 1.0 if target_bound else (1.0 if authority_level == L0_OBSERVE else 0.30),
        "verification": 1.0 if verification_ready else 0.35,
    }
    weights = {
        "scope": 1.4,
        "operator": 1.2,
        "rollback": 1.0,
        "target": 1.3,
        "verification": 1.1,
    }
    total_weight = sum(weights.values())
    log_sum = sum(weights[key] * math.log(max(1e-6, dimensions[key])) for key in dimensions)
    geometric = math.exp(log_sum / total_weight)
    critical = min(dimensions["scope"], dimensions["operator"], dimensions["target"])
    score = geometric * (0.55 + 0.45 * critical)
    return round(max(0.0, min(1.0, score)), 4)


def build_execution_intent(
    command: str,
    *,
    context: str = "",
    operator_requested_execution: bool = False,
    scope_confirmed: bool = False,
    rollback_ready: bool = False,
    verification_ready: bool = True,
    scope_target: str | None = None,
) -> ExecutionIntent:
    lifecycle = assess_command_execution(
        command,
        operator_requested_execution=operator_requested_execution,
        tool_execution_enabled=False,
    )
    host = assess_host_safety(command, context=context)
    tool = lifecycle.tool or _effective_tool(command)
    target = _target_from_command(command)
    active_probe = tool in _ACTIVE_PROBE_TOOLS
    semantic_mutation = _semantic_remote_mutation(command)
    artifact_execution = _explicit_artifact_execution(tool, context)
    high_impact_semantic = _is_high_impact_command(command, tool) or artifact_execution
    known_observe = tool in _LOCAL_OBSERVE_TOOLS
    registry_level = execution_baseline_for_tool(tool)
    known_semantics = bool(
        registry_level
        or known_observe
        or active_probe
        or high_impact_semantic
        or lifecycle.mutates_state
        or lifecycle.persistent_change
        or lifecycle.destructive
    )
    effective_mutation = bool(
        lifecycle.mutates_state
        or semantic_mutation
        or registry_level == L2_MUTATE
    )
    effective_high_impact = bool(
        high_impact_semantic or registry_level == L3_HIGH_IMPACT
    )
    normalized_scope_target = _normalize_scope_target(scope_target)
    target_required = bool(active_probe or semantic_mutation or target)
    if target_required:
        target_bound = bool(target) and (
            normalized_scope_target is None
            or target.casefold() == normalized_scope_target.casefold()
        )
    else:
        # Purely local actions bind to the confirmed execution environment/host,
        # not to a remote network target.
        target_bound = True

    if not known_semantics:
        level = L3_HIGH_IMPACT
    elif lifecycle.destructive or host.host_impact in {"blocked", "critical"} or high_impact_semantic:
        level = L3_HIGH_IMPACT
    elif lifecycle.mutates_state or lifecycle.persistent_change or semantic_mutation:
        level = L2_MUTATE
    elif active_probe:
        level = L1_PROBE
    else:
        level = L0_OBSERVE

    if registry_level and _LEVEL_RANK[registry_level] > _LEVEL_RANK[level]:
        level = registry_level

    effective_rollback_required = bool(
        host.rollback_required
        or level == L2_MUTATE
        or lifecycle.persistent_change
    )

    if not known_semantics:
        authority = BLOCKED
    elif host.host_impact == "blocked":
        authority = BLOCKED
    elif (
        operator_requested_execution
        and level != L0_OBSERVE
        and (not scope_confirmed or not target_bound)
    ):
        authority = BLOCKED
    elif level == L3_HIGH_IMPACT:
        authority = APPROVAL_REQUIRED
    elif level == L2_MUTATE or lifecycle.privilege_required:
        authority = APPROVAL_REQUIRED
    elif level == L1_PROBE:
        authority = ON_DEMAND
    else:
        authority = AUTO

    if level == L0_OBSERVE:
        capability = "local_observation"
        expected_effect = "read local state without intended mutation"
        evidence = ("stdout/stderr", "exit status")
    elif level == L1_PROBE:
        capability = "active_probe"
        expected_effect = "query or probe a bound target and collect observable response"
        evidence = ("exact command", "stdout/stderr", "target response", "timestamp")
    elif level == L2_MUTATE:
        capability = "state_change"
        expected_effect = "change a bounded local/network state and verify the post-condition"
        evidence = ("pre-state", "exact command", "post-state", "rollback result", "timestamp")
    else:
        capability = "high_impact_validation"
        expected_effect = "perform an explicitly authorized high-impact validation with bounded proof objective"
        evidence = (
            "preconditions", "exact command/artifact hash", "success predicate",
            "raw result", "post-state", "rollback/cleanup", "timestamp",
        )

    risk = _risk_index(
        lifecycle=lifecycle,
        host=host,
        active_probe=active_probe,
        semantic_mutation=effective_mutation,
        high_impact_semantic=effective_high_impact,
    )
    readiness = _readiness_index(
        scope_confirmed=scope_confirmed or level == L0_OBSERVE,
        operator_requested=operator_requested_execution or level == L0_OBSERVE,
        rollback_ready=rollback_ready or not effective_rollback_required,
        target_bound=target_bound or level == L0_OBSERVE,
        verification_ready=verification_ready,
        authority_level=level,
    )

    reasons = list(lifecycle.reasons) + list(host.reasons)
    reasons.extend(
        (
            f"authority_level={level}",
            f"authority={authority}",
        )
    )
    if not known_semantics:
        reasons.append("unknown_tool_semantics_fail_closed")
    if registry_level:
        reasons.append(f"kali_registry_baseline={registry_level}")
    if active_probe:
        reasons.append("active_probe")
    if semantic_mutation:
        reasons.append("semantic_remote_mutation")
    if high_impact_semantic:
        reasons.append("high_impact_semantic")
    if artifact_execution:
        reasons.append("explicit_poc_artifact_execution")
    if level != L0_OBSERVE and not scope_confirmed:
        reasons.append("scope_not_confirmed")
    if level != L0_OBSERVE and target_required and not target:
        reasons.append("target_not_bound")
    elif (
        level != L0_OBSERVE
        and target_required
        and normalized_scope_target is not None
        and target
        and target.casefold() != normalized_scope_target.casefold()
    ):
        reasons.append("target_scope_mismatch")
    if authority in {APPROVAL_REQUIRED, BLOCKED} and not operator_requested_execution:
        reasons.append("operator_request_required")

    return ExecutionIntent(
        command=command,
        tool=tool,
        target=target,
        capability=capability,
        authority_level=level,
        authority=authority,
        expected_effect=expected_effect,
        evidence_expected=evidence,
        privilege_required=lifecycle.privilege_required,
        mutates_state=effective_mutation,
        persistent_change=lifecycle.persistent_change,
        destructive=lifecycle.destructive,
        rollback_required=effective_rollback_required,
        verification_required=lifecycle.verification_required or level != L0_OBSERVE,
        risk_index=risk,
        readiness_index=readiness,
        reasons=tuple(dict.fromkeys(reasons)),
    )
