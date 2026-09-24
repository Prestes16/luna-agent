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
        ("format and input paths must be factual",),
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
    "masscan": KaliToolSpec(
        "masscan", "network", "IP/CIDR", "high-speed port discovery",
        ("ports and rate must be explicit", "never convert URL paths into targets"),
        ("target", "ports"),
    ),
    "rustscan": KaliToolSpec(
        "rustscan", "network", "hostname/IP", "fast port discovery with Nmap handoff",
        ("preserve target", "arguments after -- belong to Nmap"),
        ("target",),
    ),
    "httpx": KaliToolSpec(
        "httpx", "web", "host/URL list", "HTTP service probing and metadata",
        ("preserve target form", "do not invent headers or credentials"),
        ("target",),
    ),
    "whatweb": KaliToolSpec(
        "whatweb", "web", "URL/host", "web technology fingerprinting",
        ("preserve scheme and host", "treat fingerprints as observations only after output"),
        ("target",),
    ),
    "feroxbuster": KaliToolSpec(
        "feroxbuster", "web", "URL", "recursive web content discovery",
        ("preserve scheme and host", "never invent cookies, headers or wordlists"),
        ("target URL",),
    ),
    "dirsearch": KaliToolSpec(
        "dirsearch", "web", "URL", "web content discovery",
        ("preserve target URL", "do not invent local wordlists"),
        ("target URL",),
    ),
    "nikto": KaliToolSpec(
        "nikto", "web", "host/URL", "web server configuration review",
        ("preserve target", "do not claim findings before output"),
        ("target",),
    ),
    "amass": KaliToolSpec(
        "amass", "dns", "root domain", "DNS and asset enumeration",
        ("no scheme or path", "do not invent API keys or config"),
        ("root domain",),
    ),
    "dnsrecon": KaliToolSpec(
        "dnsrecon", "dns", "domain", "DNS record assessment",
        ("preserve domain", "do not invent wordlists"),
        ("domain",),
    ),
    "dnsenum": KaliToolSpec(
        "dnsenum", "dns", "domain", "DNS enumeration",
        ("preserve domain", "external files must be operator-provided"),
        ("domain",),
    ),
    "tcpdump": KaliToolSpec(
        "tcpdump", "network", "interface/filter", "packet capture",
        ("interface and capture filter must match operator context",),
        ("capture source",),
    ),
    "tshark": KaliToolSpec(
        "tshark", "network", "interface/file", "packet capture and protocol analysis",
        ("capture source and filters must be factual",),
        ("capture source",),
    ),
    "sslscan": KaliToolSpec(
        "sslscan", "tls", "host:port", "TLS configuration inspection",
        ("preserve host and port", "do not invent SNI names"),
        ("target",),
    ),
    "smbclient": KaliToolSpec(
        "smbclient", "windows", "host/share", "SMB share inspection",
        ("share and credential inputs must be factual", "do not invent domain names"),
        ("host", "share"),
    ),
    "enum4linux-ng": KaliToolSpec(
        "enum4linux-ng", "windows", "host/IP", "SMB and directory-service enumeration",
        ("do not invent credentials or domain names",),
        ("target",),
    ),
    "rpcclient": KaliToolSpec(
        "rpcclient", "windows", "host/IP", "RPC service inspection",
        ("identity and domain inputs must come from evidence or operator input",),
        ("target",),
    ),
    "ldapsearch": KaliToolSpec(
        "ldapsearch", "directory", "LDAP URI/host", "LDAP directory queries",
        ("base DN, bind identity and filters must be factual or operator-provided",),
        ("target", "base DN"),
    ),
    "medusa": KaliToolSpec(
        "medusa", "authentication", "service target", "authentication validation",
        ("module and credential sources must be explicit and factual",),
        ("target", "service/module", "identity source", "secret source"),
    ),
    "wpscan": KaliToolSpec(
        "wpscan", "web", "WordPress URL", "WordPress-focused assessment",
        ("use only when WordPress is observed or explicitly requested", "preserve target"),
        ("target URL", "WordPress evidence"),
    ),
    "testssl": KaliToolSpec(
        "testssl", "tls", "host/URL", "TLS configuration assessment",
        ("preserve target", "do not invent certificates or SNI overrides"),
        ("target",),
    ),
    "burpsuite": KaliToolSpec(
        "burpsuite", "web_proxy", "browser/app HTTP(S) traffic",
        "interactive HTTP(S) interception, inspection and request replay",
        (
            "this is an intercepting proxy, not a packet sniffer",
            "proxy/certificate setup belongs to operator environment and must not be invented",
        ),
    ),
    "mitmproxy": KaliToolSpec(
        "mitmproxy", "web_proxy", "HTTP(S) client traffic",
        "terminal-first HTTP(S) interception with scriptable flows",
        (
            "use when CLI/scriptability is valuable",
            "proxy/certificate setup must match the operator environment",
        ),
    ),
    "zaproxy": KaliToolSpec(
        "zaproxy", "web_proxy", "browser/app HTTP(S) traffic",
        "GUI intercepting proxy with web assessment workflow",
        (
            "treat it as an HTTP(S) proxy, not raw packet capture",
            "do not invent proxy/certificate configuration",
        ),
    ),
    "wireshark": KaliToolSpec(
        "wireshark", "packet_capture", "interface/capture file",
        "packet capture and protocol analysis",
        (
            "use for observing packets/protocols; it is not an HTTP request interception/rewrite proxy",
            "interface and capture source must be factual",
        ),
        ("capture source",),
    ),
    "proxychains4": KaliToolSpec(
        "proxychains4", "privacy", "TCP-capable application command",
        "application-level proxy chaining through a factual proxy configuration",
        (
            "do not assume config path, SOCKS port or proxy_dns state; detect them locally",
            "raw sockets and UDP are not transparently proxyable through proxychains",
            "never claim anonymity; validate application egress and DNS behavior",
        ),
        ("proxy configuration", "application command"),
    ),
    "proxychains": KaliToolSpec(
        "proxychains", "privacy", "TCP-capable application command",
        "application-level proxy chaining through a factual proxy configuration",
        (
            "prefer the installed binary name detected on the system",
            "raw sockets and UDP are not transparently proxyable",
            "verify DNS handling instead of assuming it",
        ),
        ("proxy configuration", "application command"),
    ),
    "tor": KaliToolSpec(
        "tor", "privacy", "local Tor service/SOCKS listener",
        "TCP-oriented privacy routing through the Tor network",
        (
            "confirm service state and SOCKS listener instead of assuming a port",
            "do not treat Tor as UDP/raw-socket transport",
            "never promise non-traceability",
        ),
        ("service state", "SOCKS listener"),
    ),
    "torsocks": KaliToolSpec(
        "torsocks", "privacy", "TCP application command",
        "Tor routing wrapper for compatible TCP applications",
        (
            "verify the local Tor listener first",
            "do not use it for raw sockets or UDP",
            "validate egress per application",
        ),
        ("Tor listener", "application command"),
    ),
    "openvpn": KaliToolSpec(
        "openvpn", "privacy", "operator-provided VPN profile",
        "system-level VPN tunnel for TCP/UDP-capable workloads",
        (
            "profile path and credentials must be operator-provided or observed",
            "verify route, DNS, IPv4 and IPv6 behavior after connection",
            "do not silently fall back to direct traffic",
        ),
        ("VPN profile",),
    ),
    "wg-quick": KaliToolSpec(
        "wg-quick", "privacy", "operator-provided WireGuard interface/profile",
        "system-level WireGuard tunnel management",
        (
            "interface/profile name must be factual",
            "verify route, DNS, IPv4 and IPv6 behavior",
            "kill-switch rules must be explicit and reversible",
        ),
        ("WireGuard interface/profile",),
    ),
    "wg": KaliToolSpec(
        "wg", "privacy", "WireGuard interface",
        "WireGuard state inspection and tunnel diagnostics",
        (
            "interface name must be factual",
            "do not expose or persist private keys in prompts or logs",
        ),
        ("WireGuard interface",),
    ),
    "file": KaliToolSpec(
        "file", "malware", "specimen/file", "file-format and magic classification",
        ("operate on a preserved specimen copy", "classification is evidence, not family attribution"),
        ("specimen",),
    ),
    "sha256sum": KaliToolSpec(
        "sha256sum", "malware", "specimen/file", "cryptographic hashing for evidence identity",
        ("hash before modifying or unpacking the specimen",),
        ("specimen",),
    ),
    "strings": KaliToolSpec(
        "strings", "malware", "specimen/file", "printable-string triage",
        ("strings are leads and require contextual validation",),
        ("specimen",),
    ),
    "xxd": KaliToolSpec(
        "xxd", "malware", "specimen/file", "hexadecimal byte inspection",
        ("preserve offsets and original bytes when documenting evidence",),
        ("specimen",),
    ),
    "yara": KaliToolSpec(
        "yara", "malware", "specimen/file/directory", "signature-based malware triage",
        (
            "rule path and specimen path must be factual",
            "a YARA hit is evidence of a rule match, not proof of family attribution by itself",
        ),
        ("specimen", "rule set"),
    ),
    "capa": KaliToolSpec(
        "capa", "malware", "binary specimen", "static capability identification",
        (
            "analyze a preserved specimen copy",
            "treat capabilities as analysis evidence, not proof of execution",
        ),
        ("specimen",),
    ),
    "floss": KaliToolSpec(
        "floss", "malware", "binary specimen", "decoded and obfuscated string recovery",
        (
            "preserve the original specimen",
            "recovered strings require contextual validation",
        ),
        ("specimen",),
    ),
    "rizin": KaliToolSpec(
        "rizin", "reverse_engineering", "binary specimen", "static/dynamic reverse engineering",
        (
            "prefer static analysis on the preserved sample before execution",
            "addresses and architecture must come from the artifact",
        ),
        ("specimen",),
    ),
    "radare2": KaliToolSpec(
        "radare2", "reverse_engineering", "binary specimen", "binary reverse engineering",
        (
            "prefer static analysis first",
            "do not invent architecture, base address or symbols",
        ),
        ("specimen",),
    ),
    "objdump": KaliToolSpec(
        "objdump", "reverse_engineering", "binary/object file", "disassembly and object metadata inspection",
        ("architecture and file format must come from the artifact",),
        ("specimen",),
    ),
    "readelf": KaliToolSpec(
        "readelf", "reverse_engineering", "ELF file", "ELF header, section, symbol and relocation inspection",
        ("use only for ELF artifacts",),
        ("ELF specimen",),
    ),
    "binwalk": KaliToolSpec(
        "binwalk", "malware", "file/firmware/blob", "embedded-content and signature inspection",
        ("extraction paths are opt-in and must not overwrite the original specimen",),
        ("specimen",),
    ),
    "volatility3": KaliToolSpec(
        "volatility3", "forensics", "memory image", "memory forensics and process/artifact reconstruction",
        (
            "memory-image path must be factual",
            "profile/symbol assumptions must be validated against the image",
        ),
        ("memory image",),
    ),
    "vol": KaliToolSpec(
        "vol", "forensics", "memory image", "Volatility 3 memory analysis",
        (
            "memory-image path must be factual",
            "plugin choice must match the investigative question",
        ),
        ("memory image",),
    ),
    "olevba": KaliToolSpec(
        "olevba", "malware", "Office document", "VBA macro extraction and static triage",
        ("use only on supported Office/OLE/OOXML artifacts", "do not execute extracted macros"),
        ("document",),
    ),
    "apktool": KaliToolSpec(
        "apktool", "reverse_engineering", "APK", "Android package resource and smali analysis",
        ("preserve the original APK", "do not sign or reinstall unless explicitly requested"),
        ("APK specimen",),
    ),
    "jadx": KaliToolSpec(
        "jadx", "reverse_engineering", "APK/DEX", "Android Java/Kotlin decompilation",
        ("decompiled source is an approximation and must be checked against bytecode/smali when critical",),
        ("APK/DEX specimen",),
    ),
}


_EXECUTION_BASELINE_BY_FAMILY: dict[str, str] = {
    "network": "L1_PROBE",
    "web": "L1_PROBE",
    "dns": "L1_PROBE",
    "tls": "L1_PROBE",
    "windows": "L1_PROBE",
    "directory": "L1_PROBE",
    "packet_capture": "L1_PROBE",
    "authentication": "L3_HIGH_IMPACT",
    "web_proxy": "L2_MUTATE",
    "privacy": "L2_MUTATE",
    "offline": "L0_OBSERVE",
    "malware": "L0_OBSERVE",
    "reverse_engineering": "L0_OBSERVE",
    "forensics": "L0_OBSERVE",
}

_EXECUTION_BASELINE_OVERRIDES: dict[str, str] = {
    # Read-only WireGuard inspection is distinct from wg-quick tunnel mutation.
    "wg": "L0_OBSERVE",
    # Wrappers can execute arbitrary nested applications; keep them approval-bound.
    "proxychains": "L2_MUTATE",
    "proxychains4": "L2_MUTATE",
    "torsocks": "L2_MUTATE",
}


def get_tool_spec(name: str | None) -> KaliToolSpec | None:
    return KALI_TOOL_DICTIONARY.get((name or "").casefold())


def execution_baseline_for_tool(name: str | None) -> str | None:
    """Return the conservative L0-L3 baseline for a registered Kali tool.

    This is a baseline only. Command-specific flags, privilege, mutation and
    host-safety analysis may always escalate the final intent.
    """
    normalized = (name or "").casefold()
    if not normalized:
        return None
    if normalized in _EXECUTION_BASELINE_OVERRIDES:
        return _EXECUTION_BASELINE_OVERRIDES[normalized]
    spec = get_tool_spec(normalized)
    if spec is None:
        return None
    return _EXECUTION_BASELINE_BY_FAMILY.get(spec.family)
