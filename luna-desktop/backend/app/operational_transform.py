"""Deterministic post-validation command normalization for operator-ready output.

The LLM proposes the command and the reasoning validators verify intent/target.
This layer performs only mechanically safe, target-preserving additions:
privilege elevation for raw-socket Nmap modes and an output artifact only when
the operator explicitly requested one and supplied an observable path/name.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import asdict, dataclass

from .command_ast import infer_nmap_intent\nfrom .command_policy import assess_command_policy, effective_tool, parse_effective_command


_FENCE_RE = re.compile(r"```(?P<label>[A-Za-z0-9_+.-]*)[ \t]*(?P<body>.*?)```", re.DOTALL)


@dataclass(frozen=True)
class OperationalMutation:
    original_sha256: str
    approved_sha256: str
    scan_mode_added: bool
    sudo_added: bool
    artifact_added: bool
    artifact_path: str | None

    def to_safe_dict(self) -> dict:
        return asdict(self)


_EXPLICIT_NMAP_SCAN_MODES = {"-ss", "-st", "-su", "-sn", "-sy", "-sz"}


def _add_initial_syn_mode(command: str) -> str:
    """Insert an explicit SYN scan mode while preserving the factual target."""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return command
    if not tokens:
        return command

    nmap_index = next(
        (
            index for index, token in enumerate(tokens)
            if token.casefold().removesuffix(".exe") == "nmap"
        ),
        None,
    )
    if nmap_index is None:
        return command
    tokens.insert(nmap_index + 1, "-sS")
    return shlex.join(tokens)


def _prepend_sudo(command: str) -> str:
    stripped = command.strip()
    if stripped.casefold().startswith("sudo "):
        return stripped
    return f"sudo {stripped}"


def _append_artifact(command: str, artifact: str) -> str:
    return f"{command.rstrip()} -oN {shlex.quote(artifact)}"


def normalize_operator_command(message: str, command: str) -> tuple[str, OperationalMutation | None]:
    """Apply deterministic, additive policy to one already-target-verified command."""
    assessment = assess_command_policy(message, command)
    if assessment.effective_tool != "nmap" or not assessment.target_verified:
        return command, None

    approved = command.strip()
    scan_mode_added = False
    sudo_added = False
    artifact_added = False
    artifact_path = assessment.artifact_path

    # Final operator-facing commands should not fail merely because a small local
    # model omitted Nmap's scan technique on a generic initial scan.  That gap is
    # mechanically repairable without changing target, ports, scripts or output.
    ast = parse_effective_command(approved)
    if ast and ast.tool == "nmap" and infer_nmap_intent(message) == "initial":
        options = {option.casefold() for option in ast.options}
        if not (options & _EXPLICIT_NMAP_SCAN_MODES):
            approved = _add_initial_syn_mode(approved)
            scan_mode_added = approved != command.strip()

    # -sS requires raw sockets, so the same deterministic pass supplies sudo.
    after_mode = assess_command_policy(message, approved)
    if after_mode.requires_elevation and not after_mode.has_sudo:
        approved = _prepend_sudo(approved)
        sudo_added = True

    # Output persistence is opt-in: never synthesize a filename or path.
    after_sudo = assess_command_policy(message, approved)
    if (
        after_sudo.artifact_required
        and not after_sudo.artifact_present
        and after_sudo.recommended_artifact
    ):
        approved = _append_artifact(approved, after_sudo.recommended_artifact)
        artifact_added = True
        artifact_path = after_sudo.recommended_artifact

    if approved == command.strip():
        return command, None

    final = assess_command_policy(message, approved)
    mutation = OperationalMutation(
        original_sha256=assessment.sha256,
        approved_sha256=final.sha256,
        scan_mode_added=scan_mode_added,
        sudo_added=sudo_added,
        artifact_added=artifact_added,
        artifact_path=artifact_path,
    )
    return approved, mutation


def transform_response_commands(message: str, response: str) -> tuple[str, list[OperationalMutation]]:
    """Normalize executable commands inside Markdown fences without touching prose."""
    mutations: list[OperationalMutation] = []

    def replace_fence(match: re.Match[str]) -> str:
        label = match.group("label")
        # The fence regex deliberately does not consume newlines after the
        # language label. Canonicalize them here so operator-visible output is
        # stable: ```bash\ncommand, never ```bash\n\ncommand.
        body = re.sub(r"^(?:\r?\n)+", "", match.group("body"))
        output_lines: list[str] = []

        for raw_line in body.splitlines():
            leading = raw_line[: len(raw_line) - len(raw_line.lstrip())]
            candidate = raw_line.strip()
            prompt = ""
            if candidate.startswith("$ "):
                prompt, candidate = "$ ", candidate[2:].lstrip()
            elif candidate.startswith("PS> "):
                prompt, candidate = "PS> ", candidate[4:].lstrip()

            if candidate and effective_tool(candidate):
                approved, mutation = normalize_operator_command(message, candidate)
                if mutation:
                    mutations.append(mutation)
                    candidate = approved
                output_lines.append(f"{leading}{prompt}{candidate}")
            else:
                output_lines.append(raw_line)

        transformed_body = "\n".join(output_lines)
        return f"```{label}\n{transformed_body}\n```"

    transformed = _FENCE_RE.sub(replace_fence, response)
    return transformed, mutations
