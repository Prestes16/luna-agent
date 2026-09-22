"""Deterministic operational policy for approved technical commands.

The language model proposes a command; this module evaluates the exact command
structure before it can be considered operator-ready.  The policy intentionally
keeps non-compensable operational requirements outside the LLM: privilege needs,
artifact persistence, target fidelity and command integrity.
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
_NMAP_OUTPUT_FLAGS = ("-oN", "-oA", "-oX", "-oG")


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

    # Support common non-interactive sudo switches without pretending to model
    # the whole sudo grammar.  Value-taking options are skipped deterministically.
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
    # shlex.join provides a deterministic shell-safe reconstruction.
    return _parse_base_command(shlex.join(effective_tokens))


def effective_tool(command: str) -> str:
    ast = parse_effective_command(command)
    return ast.tool if ast else ""


def _safe_target_slug(target: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", target.strip().rstrip(".")).strip("_")
    return slug[:96] or "target"


def _artifact_path(ast: CommandAST) -> str | None:
    for flag in _NMAP_OUTPUT_FLAGS:
        value = ast.value_for(flag)
        if value:
            return value
    return None


def _requires_nmap_elevation(ast: CommandAST) -> bool:
    folded = {option.casefold() for option in ast.options}
    return bool(folded & _NMAP_PRIVILEGED_FLAGS)


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
        artifact_required = bool(contract.wants_command)
        artifact_path = _artifact_path(ast)
        artifact_present = artifact_path is not None
        target_for_name = contract.target_hosts[0] if contract.target_hosts else (
            ast.positionals[-1] if ast.positionals else "target"
        )
        recommended_artifact = f"scan_{_safe_target_slug(target_for_name)}.txt"

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
