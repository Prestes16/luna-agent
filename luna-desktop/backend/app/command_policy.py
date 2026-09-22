"""Deterministic operational policy for approved technical commands.

The language model proposes a command; this module evaluates the exact command
structure before it can be considered operator-ready. Non-compensable
requirements stay outside the LLM: privilege needs, explicit artifact intent,
target fidelity and command integrity.
"""

from __future__ import annotations

import hashlib
import re
import shlex
from dataclasses import asdict, dataclass

from .command_ast import CommandAST, parse_command as _parse_base_command
from .reasoning_quality import build_operator_contract


_NMAP_PRIVILEGED_FLAGS = {
    "-a",       # includes OS detection/traceroute/default scripts
    "-o",       # OS detection
    "-ss",      # SYN scan/raw sockets
    "-su",      # UDP raw sockets for full fidelity
    "-sy",      # SCTP INIT scan
    "-sz",      # SCTP COOKIE-ECHO scan
    "--send-eth",
    "--privileged",
}
_NMAP_OUTPUT_FLAGS = ("-oN", "-oA", "-oX", "-oS", "-oG")
_ARTIFACT_MARKERS = (
    "salve", "salvar", "grave", "gravar", "output", "saída", "saida",
    "relatório", "relatorio", "log", "persistir", "persistente",
    "evidência", "evidencia",
)
_ARTIFACT_PATH_RE = re.compile(
    r"""(?i)(?P<path>(?:[A-Za-z]:[\\/]|/|~/)?[^\s`"']+\.(?:txt|log|xml|gnmap|nmap))"""
)


@dataclass(frozen=True)
class CommandPolicyAssessment:
    command: str
    sha256: str
    effective_tool: str
    has_sudo: bool
    requires_elevation: bool
    artifact_required: bool
    artifact_present: bool
    artifact_path: str | None
    recommended_artifact: str | None
    target_verified: bool
    expected_targets: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _split_sudo(command: str) -> tuple[bool, list[str]]:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return False, []
    if not tokens:
        return False, []
    if tokens[0].casefold() != "sudo":
        return False, tokens

    index = 1
    value_options = {"-u", "--user", "-g", "--group", "-h", "--host", "-C", "--close-from"}
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            break
        if token in value_options and index + 1 < len(tokens):
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        break
    return True, tokens[index:]


def parse_effective_command(command: str) -> CommandAST | None:
    """Parse the effective executable while preserving sudo as policy metadata."""
    _, effective_tokens = _split_sudo(command)
    if not effective_tokens:
        return None
    return _parse_base_command(shlex.join(effective_tokens))


def effective_tool(command: str) -> str:
    ast = parse_effective_command(command)
    return ast.tool if ast else ""


def _artifact_path(ast: CommandAST) -> str | None:
    for flag in _NMAP_OUTPUT_FLAGS:
        value = ast.value_for(flag)
        if value:
            return value
    return None


def _requires_nmap_elevation(ast: CommandAST) -> bool:
    folded = {option.casefold() for option in ast.options}
    return bool(folded & _NMAP_PRIVILEGED_FLAGS)


def _artifact_requested(message: str) -> bool:
    normalized = message.casefold()
    if any(flag.casefold() in normalized for flag in _NMAP_OUTPUT_FLAGS):
        return True
    # A filename alone can be an input (-iL targets.txt, wordlist etc.).
    # Persistence is opt-in only through explicit output language/flags.
    return any(
        re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", normalized)
        for marker in _ARTIFACT_MARKERS
    )


def _observed_artifact_path(message: str) -> str | None:
    # Explicit Nmap output flag takes precedence and preserves the operator path.
    try:
        tokens = shlex.split(message, posix=True)
    except ValueError:
        tokens = message.split()
    for index, token in enumerate(tokens):
        if token in _NMAP_OUTPUT_FLAGS and index + 1 < len(tokens):
            return tokens[index + 1].strip("`'\".,;")
        for flag in _NMAP_OUTPUT_FLAGS:
            if token.startswith(flag) and len(token) > len(flag):
                return token[len(flag):].strip("`'\".,;")

    # A free-standing filename may be an INPUT (-iL targets.txt, wordlist etc.).
    # Only bind a path as an output artifact when it appears AFTER explicit
    # persistence language, preventing accidental overwrite of an input file.
    marker_group = "|".join(re.escape(marker) for marker in _ARTIFACT_MARKERS)
    artifact_pattern = _ARTIFACT_PATH_RE.pattern.removeprefix("(?i)")
    contextual = re.search(
        rf"(?is)(?<!\w)(?:{marker_group})(?!\w).{{0,120}}?"
        + artifact_pattern,
        message,
    )
    if contextual:
        return contextual.group("path").rstrip(".,;:")
    return None

def assess_command_policy(message: str, command: str) -> CommandPolicyAssessment:
    """Evaluate deterministic operational requirements for an exact command."""
    contract = build_operator_contract(message)
    has_sudo, _ = _split_sudo(command)
    ast = parse_effective_command(command)
    tool = ast.tool if ast else ""

    requires_elevation = False
    artifact_required = False
    artifact_present = False
    artifact_path = None
    recommended_artifact = None

    if ast and tool == "nmap":
        requires_elevation = _requires_nmap_elevation(ast)
        # Output files are opt-in. A scan command must not silently create files.
        artifact_required = _artifact_requested(message)
        artifact_path = _artifact_path(ast)
        artifact_present = artifact_path is not None
        recommended_artifact = _observed_artifact_path(message) if artifact_required else None

    normalized_positionals = {
        value.casefold().rstrip(".") for value in (ast.positionals if ast else ())
    }
    target_verified = (
        True
        if not contract.target_hosts
        else any(target.casefold().rstrip(".") in normalized_positionals for target in contract.target_hosts)
    )

    return CommandPolicyAssessment(
        command=command,
        sha256=hashlib.sha256(command.encode("utf-8")).hexdigest(),
        effective_tool=tool,
        has_sudo=has_sudo,
        requires_elevation=requires_elevation,
        artifact_required=artifact_required,
        artifact_present=artifact_present,
        artifact_path=artifact_path,
        recommended_artifact=recommended_artifact,
        target_verified=target_verified,
        expected_targets=contract.target_hosts,
    )
