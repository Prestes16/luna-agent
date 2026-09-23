"""Structured Kali/Linux tool knowledge used for runtime guidance.

This registry stores CLI target types, factual prerequisites and anti-hallucination
rules. It never executes tools and never treats examples as evidence.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KaliToolSpec:
    name: str
    family: str
    target_kind: str
    purpose: str
    invariants: tuple[str, ...]
    required_facts: tuple[str, ...] = ()

    def prompt(self) -> str:
        rules = "; ".join(self.invariants)
        requirements = (
            " Required factual inputs: " + ", ".join(self.required_facts) + "."
            if self.required_facts else ""
        )
        return f"{self.name}: {self.purpose}. target={self.target_kind}. {rules}.{requirements}"


KALI_TOOL_DICTIONARY: dict[str, KaliToolSpec] = {
    "nmap": KaliToolSpec(
        "nmap", "network", "hostname/IP/CIDR", "port and service assessment",
        (
            "never pass an http(s) URL as the target",
            "prefer an explicit scan technique when relevant",
            "output files are opt-in and must use an observed operator path",
        ),
        ("target",),
    ),
    "ffuf": KaliToolSpec(
        "ffuf", "web", "URL", "web content testing",
        ("FUZZ marks the mutation point", "never invent a local wordlist path"),
        ("target URL", "wordlist"),
    ),
    "gobuster": KaliToolSpec(
        "gobuster", "web", "URL/domain", "web/DNS enumeration",
        ("mode must be explicit", "never invent a wordlist path"),
        ("mode", "target", "wordlist"),
    ),
    "hydra": KaliToolSpec(
        "hydra", "authentication", "service target", "authentication testing",
        (
            "service/module must be explicit",
            "identity and secret sources must be factual",
            "for web forms never invent endpoint, field names or failure markers",
        ),
        ("target", "service/module", "identity source", "secret source"),
    ),
    "sqlmap": KaliToolSpec(
        "sqlmap", "web", "URL/request", "request-parameter validation",
        ("preserve observed parameters and request data", "never invent cookies or fields"),
        ("request/URL", "parameter or captured request evidence"),
    ),
    "nuclei": KaliToolSpec(
        "nuclei", "web", "URL/list", "template-based checks",
        ("never invent template IDs or auth headers", "preserve target"),
        ("target",),
    ),
    "netexec": KaliToolSpec(
        "netexec", "windows", "host/CIDR", "Windows service assessment",
        ("protocol must be explicit", "never invent domain or credentials"),
        ("protocol", "target"),
    ),
    "hashcat": KaliToolSpec(
        "hashcat", "offline", "hash/file", "offline hash analysis",
        ("hash mode must match observed format", "never invent local paths"),
        ("hash or hash file", "hash type/mode evidence"),
    ),
    "john": KaliToolSpec(
        "john", "offline", "hash/file", "offline hash analysis",
        ("format and input paths must be factual"),
        ("hash or hash file",),
    ),
    "dig": KaliToolSpec(
        "dig", "dns", "DNS name", "DNS record inspection",
        ("do not pass full URL", "resolver must not be invented"),
        ("DNS name",),
    ),
    "subfinder": KaliToolSpec(
        "subfinder", "dns", "root domain", "subdomain discovery",
        ("no scheme/path", "do not invent provider keys"),
        ("root domain",),
    ),
}


def get_tool_spec(name: str | None) -> KaliToolSpec | None:
    return KALI_TOOL_DICTIONARY.get((name or "").casefold())
