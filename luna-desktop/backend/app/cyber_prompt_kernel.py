"""Deterministic prompt compiler for the optional Luna Cyber Kernel v1.

The compiler is read-only and side-effect free. It selects a compact semantic
subset of repository-owned instruction modules for the current turn. Execution,
authorization, validation, and evidence remain harness responsibilities.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts" / "cyber"

_SKILL_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("WEB_API", ("http", "api", "rest", "graphql", "jwt", "idor", "bola", "ssrf", "cors", "xss", "sqli", "cookie", "session", "curl")),
    ("NETWORK_PROTOCOL", ("nmap", "tcp", "udp", "dns", "tls", "smb", "ldap", "ssh", "porta", "service", "serviço")),
    ("LINUX_PRIVESC", ("sudo", "suid", "systemd", "cron", "capabilities", "privesc", "privilege escalation")),
    ("WINDOWS_AD", ("active directory", "kerberos", "ntlm", "winrm", "powershell", "windows ad")),
    ("EXPLOIT_DEV", ("buffer overflow", "use-after-free", "uaf", "rop", "heap", "stack", "crash", "fuzz", "pwndbg", "gdb", "exploit")),
    ("REVERSE_ENGINEERING", ("reverse engineering", "ghidra", "rizin", "radare", "decompiler", "disassembly", "assembly", "binary")),
    ("WEB3", ("solana", "anchor", "ethereum", "solidity", "pda", "spl token", "smart contract", "web3")),
    ("MALWARE_ANALYSIS", ("malware", "ransomware", "trojan", "rootkit", "loader", "dropper", "yara", "volatility")),
    ("QUANT_MATH", ("overflow", "underflow", "rounding", "fixed-point", "fixed point", "entropy", "probability", "timing", "rf", "snr")),
)

_OUTPUT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("EXPLOIT PROOF", ("poc", "proof of concept", "exploit", "reproducer", "comprovar", "validar achado")),
    ("BINARY / MEMORY", ("binary", "crash", "gdb", "pwndbg", "heap", "stack", "rop", "reverse engineering")),
    ("WEB / API", ("http", "api", "jwt", "idor", "bola", "graphql", "cors", "ssrf", "curl")),
    ("WEB3", ("solana", "anchor", "ethereum", "solidity", "pda", "smart contract")),
    ("REPORT-GRADE FINDING", ("report", "relatório", "finding", "hackerone", "immunefi")),
)

_TOOL_MARKERS = (
    "comando", "command", "curl", "nmap", "ffuf", "burp", "gdb", "ghidra",
    "solana", "anchor", "foundry", "cast", "tool", "ferramenta",
)

_CORE_RUNTIME_SECTIONS = (
    "MISSION",
    "AUTHORITY MODEL",
    "BUILD-TO-BREAK",
    "QUANTITATIVE INTEGRITY",
    "RESPONSE DISCIPLINE",
)

_EPISTEMIC_RUNTIME_SECTIONS = (
    "Transições válidas",
    "Fonte e precedência",
    "Capability truthfulness",
)

_OMISSION_MARKER = "[OMITTED BY PROMPT BUDGET]"


@dataclass(frozen=True)
class CyberPromptCompilation:
    text: str
    selected_skill: str | None
    selected_output_contract: str
    tool_epistemology_included: bool

    @property
    def char_count(self) -> int:
        return len(self.text)


def _clip_at_boundary(text: str, max_chars: int) -> str:
    """Bound text without cutting through a word or semantic line."""
    value = text.strip()
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value

    marker = f"\n{_OMISSION_MARKER}"
    payload_budget = max_chars - len(marker)
    if payload_budget <= 0:
        return _OMISSION_MARKER[:max_chars]

    candidate = value[:payload_budget]
    boundaries = (
        candidate.rfind("\n\n"),
        candidate.rfind("\n"),
        candidate.rfind(". "),
        candidate.rfind("; "),
        candidate.rfind(": "),
    )
    cut = max(boundaries)
    if cut < max(80, payload_budget // 2):
        cut = candidate.rfind(" ")
    if cut <= 0:
        return _OMISSION_MARKER[:max_chars]

    clipped = candidate[:cut].rstrip(" \t,;:")
    return f"{clipped}{marker}"


def _read_prompt(name: str) -> str:
    root = PROMPT_ROOT.resolve()
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"(?ms)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s|\Z)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return ""
    return f"## {heading}\n{match.group(1).strip()}"


def _compose_sections(text: str, headings: Sequence[str]) -> str:
    return "\n\n".join(
        section
        for heading in headings
        if (section := _section(text, heading))
    )


def _tool_epistemology_core(text: str) -> str:
    """Keep the universal tool contract; domain specifics live in the active skill."""
    prefix, _, _ = text.partition("## Exemplos de classes")
    return prefix.strip()


def _matches(message: str, markers: Iterable[str]) -> bool:
    normalized = message.casefold()
    return any(marker.casefold() in normalized for marker in markers)


def select_skill(message: str) -> str | None:
    for skill, markers in _SKILL_RULES:
        if _matches(message, markers):
            return skill
    return None


def select_output_contract(message: str) -> str:
    for contract, markers in _OUTPUT_RULES:
        if _matches(message, markers):
            return contract
    return "INVESTIGATION"


def compile_cyber_kernel(
    message: str,
    *,
    supervised_mode: bool = True,
    max_chars: int = 5_200,
) -> CyberPromptCompilation:
    """Compile a bounded semantic prompt for one turn without executing anything."""
    core = _read_prompt("core.md")
    epistemic = _read_prompt("epistemic.md")
    skills = _read_prompt("skills.md")
    outputs = _read_prompt("output-contracts.md")
    tools = _read_prompt("tool-contracts.md")

    selected_skill = select_skill(message)
    selected_output = select_output_contract(message)
    include_tools = _matches(message, _TOOL_MARKERS)

    core_runtime = _compose_sections(core, _CORE_RUNTIME_SECTIONS)
    epistemic_runtime = _compose_sections(epistemic, _EPISTEMIC_RUNTIME_SECTIONS)

    parts = [
        "LUNA CYBER KERNEL V1 — COMPILED",
        (
            "EXECUTION PLANE: supervised executor only; model tool loop locked."
            if supervised_mode
            else "EXECUTION PLANE: restricted runtime tools enabled by harness."
        ),
        (
            "IDENTITY: Luna Cyber; copilota técnica privada de segurança ofensiva e "
            "engenharia. Evidência atual prevalece sobre memória e prior do modelo."
        ),
        core_runtime,
        epistemic_runtime,
    ]

    if selected_skill:
        skill_section = _section(skills, selected_skill)
        if skill_section:
            parts.extend(("", f"ACTIVE CYBER SKILL: {selected_skill}", skill_section))

    output_section = _section(outputs, selected_output)
    if output_section:
        parts.extend(("", f"ACTIVE OUTPUT CONTRACT: {selected_output}", output_section))

    if include_tools:
        tool_core = _tool_epistemology_core(tools)
        if tool_core:
            parts.extend(("", "TOOL EPISTEMOLOGY", tool_core))

    compiled = "\n".join(part for part in parts if part is not None).strip()
    compiled = _clip_at_boundary(compiled, max_chars)

    return CyberPromptCompilation(
        text=compiled,
        selected_skill=selected_skill,
        selected_output_contract=selected_output,
        tool_epistemology_included=include_tools,
    )
