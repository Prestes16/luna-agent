"""Deterministic prompt compiler for the optional Luna Cyber Kernel v1.

The compiler is intentionally read-only and side-effect free. It selects a compact
subset of repository-owned instruction modules for the current turn. Execution,
authorization, validation, and evidence remain harness responsibilities.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts" / "cyber"

_SKILL_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("WEB_API", ("http", "api", "rest", "graphql", "jwt", "idor", "bola", "ssrf", "cors", "xss", "sqli", "cookie", "session")),
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
    ("WEB / API", ("http", "api", "jwt", "idor", "bola", "graphql", "cors", "ssrf")),
    ("WEB3", ("solana", "anchor", "ethereum", "solidity", "pda", "smart contract")),
    ("REPORT-GRADE FINDING", ("report", "relatório", "finding", "hackerone", "immunefi")),
)

_TOOL_MARKERS = (
    "comando", "command", "curl", "nmap", "ffuf", "burp", "gdb", "ghidra",
    "solana", "anchor", "foundry", "cast", "tool", "ferramenta",
)


@dataclass(frozen=True)
class CyberPromptCompilation:
    text: str
    selected_skill: str | None
    selected_output_contract: str
    tool_epistemology_included: bool

    @property
    def char_count(self) -> int:
        return len(self.text)


def _read_prompt(name: str, max_chars: int) -> str:
    root = PROMPT_ROOT.resolve()
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return ""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""
    return text[:max_chars].rstrip()


def _section(text: str, heading: str, max_chars: int) -> str:
    match = re.search(
        rf"(?ms)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s|\Z)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return ""
    body = match.group(1).strip()
    return f"## {heading}\n{body}"[:max_chars].rstrip()


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
    """Compile a bounded prompt for one turn without executing anything."""
    core = _read_prompt("core.md", 3_250)
    epistemic = _read_prompt("epistemic.md", 1_450)
    skills = _read_prompt("skills.md", 10_000)
    outputs = _read_prompt("output-contracts.md", 8_000)
    tools = _read_prompt("tool-contracts.md", 950)

    selected_skill = select_skill(message)
    selected_output = select_output_contract(message)
    include_tools = _matches(message, _TOOL_MARKERS)

    parts = [
        "LUNA CYBER KERNEL V1 — COMPILED",
        (
            "EXECUTION PLANE: supervised executor only; model tool loop locked."
            if supervised_mode
            else "EXECUTION PLANE: restricted runtime tools enabled by harness."
        ),
        core,
        epistemic,
    ]

    if selected_skill:
        skill_section = _section(skills, selected_skill, 800)
        if skill_section:
            parts.extend(("", f"ACTIVE CYBER SKILL: {selected_skill}", skill_section))

    output_section = _section(outputs, selected_output, 550)
    if output_section:
        parts.extend(("", f"ACTIVE OUTPUT CONTRACT: {selected_output}", output_section))

    if include_tools:
        parts.extend(("", "TOOL EPISTEMOLOGY", tools))

    compiled = "\n".join(part for part in parts if part is not None).strip()
    if len(compiled) > max_chars:
        compiled = compiled[:max_chars].rstrip()

    return CyberPromptCompilation(
        text=compiled,
        selected_skill=selected_skill,
        selected_output_contract=selected_output,
        tool_epistemology_included=include_tools,
    )
