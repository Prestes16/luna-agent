"""Lazy technical capability map for Luna instruction-only operation.

Breadth is loaded on demand so the small local model receives only the
technical domains relevant to the current task. No capability grants host
execution; the operator remains responsible for every command.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TechnicalCapability:
    name: str
    markers: tuple[str, ...]
    knowledge: tuple[str, ...]
    deliverables: tuple[str, ...]

    def prompt(self) -> str:
        return (
            f"{self.name}: knowledge={'; '.join(self.knowledge)}; "
            f"deliverables={'; '.join(self.deliverables)}"
        )


CAPABILITIES: tuple[TechnicalCapability, ...] = (
    TechnicalCapability(
        "web_api",
        ("web", "http", "https", "api", "rest", "graphql", "jwt", "cookie", "session", "cors"),
        ("HTTP semantics and proxies", "auth/session boundaries", "input validation", "API abuse cases"),
        ("curl/httpx tests", "request-replay recipes", "small validation scripts", "fuzzing harnesses"),
    ),
    TechnicalCapability(
        "network_protocols",
        ("nmap", "tcp", "udp", "dns", "smb", "ldap", "ssh", "tls", "packet", "pcap", "rede"),
        ("TCP/IP and routing", "service enumeration", "protocol state", "packet/TLS analysis"),
        ("scan plans", "packet filters", "protocol probes", "parsers"),
    ),
    TechnicalCapability(
        "identity_auth",
        ("login", "auth", "credential", "senha", "password", "oauth", "oidc", "kerberos", "ntlm"),
        ("authentication flows", "authorization models", "credential handling", "identity protocols"),
        ("test matrices", "request templates", "credential-safe scripts", "evidence checklists"),
    ),
    TechnicalCapability(
        "linux_privilege",
        ("linux", "sudo", "suid", "capabilities", "cron", "systemd", "privesc", "privilege escalation"),
        ("Linux permissions", "services and jobs", "capabilities/SUID", "local privilege boundaries"),
        ("enumeration commands", "small audit scripts", "proof-of-condition checks", "rollback steps"),
    ),
    TechnicalCapability(
        "windows_ad",
        ("windows", "active directory", "ad", "smb", "ldap", "kerberos", "winrm", "powershell"),
        ("Windows security model", "AD/Kerberos/LDAP", "SMB/RPC", "PowerShell administration"),
        ("enumeration plans", "PowerShell helpers", "LDAP queries", "evidence parsers"),
    ),
    TechnicalCapability(
        "exploit_dev",
        (
            "exploit", "exploração", "exploracao", "poc", "proof of concept",
            "prova de conceito", "comprovar achado", "validar achado", "reproducer",
            "rce", "auth bypass", "idor", "ssrf", "sql injection", "xss", "privesc",
            "buffer overflow", "rop", "heap", "stack", "gdb", "pwndbg", "fuzz", "crash",
        ),
        (
            "exploitability proof across Web/API, privilege boundaries, protocols, binaries and Web3",
            "memory safety, calling conventions, debugging and crash triage",
            "precondition and explicit success predicate design",
            "minimal reproducible proof construction",
            "evidence capture, cleanup and report-grade reproduction",
        ),
        (
            "minimal PoCs/exploit reproducers for authorized targets",
            "fuzz harnesses and crash reproducers",
            "request/response or transaction proof scripts",
            "evidence capture manifests",
            "debug scripts and cleanup/rollback steps",
        ),
    ),
    TechnicalCapability(
        "reverse_engineering",
        ("reverse", "reversing", "ghidra", "radare", "rizin", "assembly", "disassembly", "binary", "decompiler"),
        ("x86/x64/ARM assembly and ABI", "static/dynamic analysis", "PE/ELF/Mach-O", "decompilation limits"),
        ("analysis checklists", "GDB/Ghidra scripts", "binary parsers", "function-mapping notes"),
    ),
    TechnicalCapability(
        "cloud_container",
        ("docker", "container", "kubernetes", "k8s", "aws", "azure", "gcp", "cloud", "iam"),
        ("container isolation", "Kubernetes/RBAC", "cloud IAM", "metadata and secret boundaries"),
        ("audit commands", "manifest checks", "policy tests", "configuration validators"),
    ),
    TechnicalCapability(
        "wireless",
        ("wifi", "wi-fi", "802.11", "wireless", "wpa", "aircrack", "hcxdumptool"),
        ("802.11 frames", "WPA security", "radio/interface modes", "capture validation"),
        ("capture workflows", "interface checks", "pcap analysis", "lab scripts"),
    ),
    TechnicalCapability(
        "blockchain_web3",
        ("solana", "anchor", "web3", "smart contract", "solidity", "ethereum", "pda", "spl", "program"),
        ("transaction/account models", "program authority", "state invariants", "on-chain attack surfaces"),
        ("tests", "PoCs in local/devnet labs", "invariant checks", "transaction parsers"),
    ),
    TechnicalCapability(
        "malware_forensics",
        (
            "malware", "ransomware", "trojan", "rat", "rootkit", "bootkit",
            "loader", "dropper", "stealer", "webshell", "yara", "volatility",
            "packer", "obfuscat", "desofusc", "deobfuscat", "memory dump", "sandbox",
        ),
        (
            "static and dynamic malware triage", "ransomware cryptographic workflow",
            "x86/x64/ARM machine code", "C/C++/Rust/Go native artifacts",
            ".NET C#/IL and JVM/DEX", "PowerShell/VBScript/VBA/JScript/JavaScript",
            "Python bytecode and shell scripts", "memory/process/network forensics",
            "YARA/Sigma/IOC engineering and incident response",
        ),
        (
            "safe triage plans", "YARA/Sigma rules", "artifact and config parsers",
            "deobfuscation helpers", "Ghidra/rizin/GDB scripts", "Volatility workflows",
            "ransomware-family evidence matrices", "containment/eradication/recovery checklists",
        ),
    ),
    TechnicalCapability(
        "programming_automation",
        (
            "python", "bash", "powershell", "rust", "golang", " go ", " c ", "c++",
            "c#", "dotnet", "java", "kotlin", "assembly", "mips", "riscv",
            "delphi", "pascal", "nim", "zig", "typescript", "javascript",
            "vbscript", "vba", "script", "programar", "codigo", "código",
        ),
        (
            "Python/Bash/PowerShell", "Rust/C/C++/Go", "C#/.NET IL",
            "Java/Kotlin/JVM/DEX", "x86/x64/ARM assembly", "JavaScript/TypeScript",
            "VBScript/VBA/HTA/AutoIt and binary-data processing",
            "Delphi/Pascal/Nim/Zig and embedded architectures", "testing and CLI design",
        ),
        ("scripts", "CLI tools", "parsers", "test harnesses", "automation", "reports and reusable modules"),
    ),
    TechnicalCapability(
        "math_physics",
        (
            "matemática", "matematica", "math", "física", "fisica", "physics",
            "overflow", "underflow", "rounding", "precision", "probability",
            "probabilidade", "entropy", "entropia", "modular", "fixed point",
            "fixed-point", "rf", "rssi", "snr", "timing", "side-channel",
        ),
        (
            "integer/modular arithmetic and finite fields",
            "fixed-point/decimal arithmetic, bounds, rounding and conservation",
            "probability, combinatorics, entropy and statistical inference",
            "dimensional analysis, timing, signals, RF and measurement uncertainty",
            "bit-level arithmetic, signedness, endianness and numerical error propagation",
        ),
        (
            "exact derivations with units and bounds",
            "numeric invariant checks",
            "overflow/rounding/conservation test cases",
            "probability/randomness analysis",
            "signal/timing measurement models",
        ),
    ),
    TechnicalCapability(
        "secure_engineering",
        ("arquitetura", "secure coding", "code review", "auditoria", "security review", "threat model"),
        ("threat modeling", "secure design", "code review", "test strategy"),
        ("patches", "regression tests", "security checklists", "design notes"),
    ),
)


def select_capabilities(message: str, limit: int = 3) -> tuple[TechnicalCapability, ...]:
    normalized = f" {message.casefold()} "
    ranked: list[tuple[int, int, TechnicalCapability]] = []
    for index, capability in enumerate(CAPABILITIES):
        hits = sum(marker in normalized for marker in capability.markers)
        if hits:
            ranked.append((hits, -index, capability))
    ranked.sort(key=lambda item: (-item[0], -item[1]))
    return tuple(item[2] for item in ranked[: max(1, limit)])


def technical_guidance(message: str, max_chars: int = 1_200) -> str:
    selected = select_capabilities(message)
    if not selected:
        return ""
    body = " | ".join(capability.prompt() for capability in selected)
    guidance = (
        "TECHNICAL CAPABILITY CONTEXT (supervised-copilot baseline; model tool loop locked, separate operator-gated executor): "
        + body
        + ". Explain exact prerequisites and syntax; when asked to build something, provide complete "
        "operator-reviewable code/config/tests rather than vague pseudocode. For exploit validation, "
        "prefer the smallest evidence-bound reproducer with an explicit success predicate. Never claim "
        "execution or verification unless an execution result exists. Prefer reusable small components and "
        "explicit validation/rollback steps for system changes."
    )
    return guidance[:max_chars]
