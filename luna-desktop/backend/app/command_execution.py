"""Deterministic command lifecycle policy for Luna.

The model may propose commands, but this module decides whether a command is
operator-ready, requires explicit confirmation, or must remain advisory. It
never executes a shell command by itself.

Lifecycle:
DISCOVER -> PREFLIGHT -> PLAN -> EXECUTE -> VERIFY -> ROLLBACK/CONTINUE
"""

from __future__ import annotations

import math
import re
import shlex
from dataclasses import asdict, dataclass


_READ_ONLY_TOOLS = {
    "cat", "less", "head", "tail", "grep", "rg", "find", "ls", "pwd",
    "which", "whereis", "command", "type", "id", "whoami", "uname", "hostname",
    "ip", "ss", "netstat", "route", "resolvectl", "systemctl", "journalctl",
    "ps", "pgrep", "nmap", "dig", "nslookup", "host", "curl", "wget", "httpx",
    "whatweb", "sslscan", "testssl", "tshark", "tcpdump", "wg",
    "file", "sha256sum", "strings", "xxd", "readelf", "objdump", "yara", "capa",
    "floss", "rizin", "radare2", "binwalk", "volatility3", "vol", "olevba",
    "apktool", "jadx",
}

_TRANSIENT_MUTATORS = {
    "openvpn", "wg-quick", "tor", "torsocks", "proxychains", "proxychains4",
    "systemctl", "ip", "route", "resolvectl",
}

_PACKAGE_MANAGERS = {"apt", "apt-get"}

_PERSISTENT_MUTATORS = {
    "apt", "apt-get", "dnf", "yum", "pacman", "systemctl", "nft", "iptables",
    "ufw", "firewall-cmd", "tee", "sed", "cp", "mv", "chmod", "chown",
}

_DESTRUCTIVE_TOOLS = {
    "rm", "rmdir", "shred", "mkfs", "fdisk", "parted", "dd", "reboot",
    "shutdown", "poweroff", "halt", "kill", "pkill",
}

_INTERACTIVE_TOOLS = {
    "nano", "vim", "vi", "less", "more", "top", "htop", "msfconsole",
}

_HIGH_RISK_PATTERNS = (
    re.compile(r"\brm\s+-[^\n]*r[^\n]*f", re.IGNORECASE),
    re.compile(r"\b(?:mkfs|fdisk|parted)\b", re.IGNORECASE),
    re.compile(r"\bdd\s+if=", re.IGNORECASE),
    re.compile(r"\biptables\s+-F\b", re.IGNORECASE),
    re.compile(r"\bnft\s+flush\s+ruleset\b", re.IGNORECASE),
    re.compile(r"\bsystemctl\s+(?:disable|mask)\b", re.IGNORECASE),
)

_PERSISTENCE_PATTERNS = (
    re.compile(r"\bsystemctl\s+enable\b", re.IGNORECASE),
    re.compile(r"(?:^|\s)/(?:etc|usr/local/etc)/", re.IGNORECASE),
    re.compile(r"\b(?:tee|sed\s+-i|cp|mv|chmod|chown)\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class CommandExecutionAssessment:
    command: str
    tool: str
    privilege_required: bool
    interactive: bool
    mutates_state: bool
    persistent_change: bool
    destructive: bool
    reversible: bool
    verification_required: bool
    explicit_confirmation_required: bool
    execution_ready: bool
    utility: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _split_command(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def _effective_tokens(tokens: list[str]) -> tuple[bool, list[str]]:
    if not tokens:
        return False, []
    if tokens[0].casefold() != "sudo":
        return False, tokens

    index = 1
    value_opts = {"-u", "--user", "-g", "--group", "-h", "--host"}
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            break
        if token in value_opts and index + 1 < len(tokens):
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        break
    return True, tokens[index:]


def _systemctl_is_read_only(tokens: list[str]) -> bool:
    if not tokens or tokens[0].casefold() != "systemctl":
        return False
    verbs = {token.casefold() for token in tokens[1:] if not token.startswith("-")}
    return bool(verbs & {"status", "is-active", "is-enabled", "show", "list-units"})


def _ip_is_read_only(tokens: list[str]) -> bool:
    if not tokens or tokens[0].casefold() != "ip":
        return False
    if len(tokens) == 1:
        return True
    verbs = {token.casefold() for token in tokens[1:]}
    return not bool(verbs & {"add", "del", "delete", "replace", "set", "flush"})


def assess_command_execution(
    command: str,
    *,
    operator_requested_execution: bool = False,
    tool_execution_enabled: bool = False,
) -> CommandExecutionAssessment:
    tokens = _split_command(command)
    has_sudo, effective = _effective_tokens(tokens)
    tool = effective[0].casefold() if effective else ""
    lowered = command.casefold()
    package_tokens = {token.casefold() for token in effective[1:]}
    package_action = bool(
        tool in _PACKAGE_MANAGERS
        and any(
            token in {
                "install", "remove", "purge", "upgrade", "full-upgrade",
                "dist-upgrade", "autoremove",
            }
            for token in package_tokens
        )
    )
    package_simulation = bool(
        package_action
        and package_tokens.intersection({"-s", "--simulate", "--dry-run"})
    )

    read_only = (
        (
            tool in _READ_ONLY_TOOLS
            and not any(pattern.search(command) for pattern in _PERSISTENCE_PATTERNS)
        )
        or package_simulation
    )
    if tool == "systemctl":
        read_only = _systemctl_is_read_only(effective)
    elif tool == "ip":
        read_only = _ip_is_read_only(effective)

    destructive = tool in _DESTRUCTIVE_TOOLS or any(
        pattern.search(command) for pattern in _HIGH_RISK_PATTERNS
    )
    package_mutation = bool(package_action and not package_simulation)
    persistent = bool(
        (tool in _PERSISTENT_MUTATORS and any(
            pattern.search(command) for pattern in _PERSISTENCE_PATTERNS
        ))
        or package_mutation
    )
    mutates_state = not read_only and (
        tool in _TRANSIENT_MUTATORS
        or tool in _PERSISTENT_MUTATORS
        or destructive
        or has_sudo
    )
    interactive = tool in _INTERACTIVE_TOOLS
    privilege_required = has_sudo or tool in {
        "nft", "iptables", "ufw", "firewall-cmd", "wg-quick", "openvpn",
    } or package_mutation

    reversible = not destructive
    if persistent and tool in {"tee", "sed", "rm", "shred"}:
        reversible = False

    verification_required = mutates_state or tool in {
        "nmap", "curl", "proxychains", "proxychains4", "tor", "torsocks",
        "openvpn", "wg-quick", "wg",
    }

    reasons: list[str] = []
    if destructive:
        reasons.append("destructive_command")
    if persistent:
        reasons.append("persistent_system_change")
    if interactive:
        reasons.append("interactive_command")
    if mutates_state:
        reasons.append("state_mutation")
    if privilege_required:
        reasons.append("privilege_elevation")
    if not operator_requested_execution:
        reasons.append("operator_execution_not_requested")
    if not tool_execution_enabled:
        reasons.append("model_tool_loop_disabled")
    if mutates_state and not reversible:
        reasons.append("rollback_not_guaranteed")

    explicit_confirmation_required = bool(
        destructive or persistent or privilege_required or (mutates_state and not reversible)
    )

    # Multiplicative readiness score. One serious risk dimension should dominate.
    factual = 1.0 if tool else 0.15
    reversibility = 1.0 if reversible else 0.25
    non_destructive = 0.08 if destructive else 1.0
    non_interactive = 0.55 if interactive else 1.0
    privilege_factor = 0.72 if privilege_required else 1.0
    mutation_factor = 0.82 if mutates_state else 1.0
    utility = (
        factual
        * (reversibility ** 1.35)
        * (non_destructive ** 1.8)
        * (non_interactive ** 0.7)
        * (privilege_factor ** 0.8)
        * mutation_factor
    )

    execution_ready = bool(
        operator_requested_execution
        and tool_execution_enabled
        and tool
        and not destructive
        and not interactive
        and (reversible or not mutates_state)
    )

    return CommandExecutionAssessment(
        command=command,
        tool=tool,
        privilege_required=privilege_required,
        interactive=interactive,
        mutates_state=mutates_state,
        persistent_change=persistent,
        destructive=destructive,
        reversible=reversible,
        verification_required=verification_required,
        explicit_confirmation_required=explicit_confirmation_required,
        execution_ready=execution_ready,
        utility=round(utility, 4),
        reasons=tuple(dict.fromkeys(reasons)),
    )


def command_lifecycle_guidance(command: str) -> str:
    assessment = assess_command_execution(command)
    if not assessment.tool:
        return ""
    return (
        "COMMAND LIFECYCLE: DISCOVER/PREFLIGHT before mutation; execute one state-changing "
        "step at a time; verify the expected post-condition before continuing; for persistent "
        "or privileged changes require explicit confirmation and a rollback path; never chain "
        "an unverified mutation with later actions. "
        f"tool={assessment.tool}; utility={assessment.utility:.3f}; "
        f"reasons={','.join(assessment.reasons) or 'none'}."
    )
