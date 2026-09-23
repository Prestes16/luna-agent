"""Construction-first reasoning for cyber analysis: build the model before breaking it.

The operator still executes every action. This module gives Luna a compact
mathematical representation of how well a system is structurally understood
before an attack/audit hypothesis is promoted.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass


def _clip(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


@dataclass(frozen=True)
class ConstructionModel:
    topology: float
    interfaces: float
    data_flow: float
    state_model: float
    trust_boundaries: float
    invariants: float
    dependencies: float
    controls: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConstructionDomainProfile:
    name: str
    markers: tuple[str, ...]
    structural_questions: tuple[str, ...]
    critical_invariants: tuple[str, ...]


@dataclass(frozen=True)
class MechanismChain:
    component: float
    interface: float
    trust_boundary: float
    state_transition: float
    invariant: float
    evidence: float
    expected_observation: float


CONSTRUCTION_PROFILES: tuple[ConstructionDomainProfile, ...] = (
    ConstructionDomainProfile(
        "web_api",
        ("web", "http", "https", "api", "rest", "graphql", "jwt", "cookie", "session"),
        (
            "request path and parser",
            "authentication then authorization decision point",
            "session/token lifecycle",
            "server-side state transition",
            "frontend/backend trust split",
        ),
        (
            "identity cannot be forged by untrusted input",
            "authorization is enforced server-side",
            "state transitions require the intended principal and preconditions",
        ),
    ),
    ConstructionDomainProfile(
        "network_protocols",
        ("tcp", "udp", "dns", "smb", "ldap", "ssh", "tls", "pcap", "nmap", "rede", "network"),
        (
            "layer/protocol state machine",
            "client/server roles and reachable interfaces",
            "routing/NAT/firewall path",
            "name-resolution and trust path",
            "transport versus application semantics",
        ),
        (
            "state transitions follow protocol rules",
            "traffic reaches only intended trust zones",
            "identity/confidentiality properties match the negotiated protocol",
        ),
    ),
    ConstructionDomainProfile(
        "linux_windows_identity",
        ("linux", "windows", "sudo", "systemd", "active directory", "kerberos", "ntlm", "ldap", "winrm"),
        (
            "principal and token/credential origin",
            "permission evaluation path",
            "service/job/persistence lifecycle",
            "privilege boundary and inheritance",
            "trusted configuration source",
        ),
        (
            "least-privilege boundary is preserved",
            "privileged transitions require intended authority",
            "persistence/configuration cannot be modified by lower-trust principals",
        ),
    ),
    ConstructionDomainProfile(
        "malware_reverse",
        ("malware", "ransomware", "trojan", "rootkit", "bootkit", "reverse", "ghidra", "rizin", "radare"),
        (
            "file/container format and loader path",
            "entry point and control-flow graph",
            "configuration/key material origin",
            "persistence and privilege interaction",
            "process/memory/network behavior",
        ),
        (
            "observed behavior is separated from inferred capability",
            "decoded stages retain provenance",
            "dynamic behavior is only trusted from isolated observation",
        ),
    ),
    ConstructionDomainProfile(
        "blockchain_web3",
        ("solana", "anchor", "web3", "smart contract", "solidity", "ethereum", "pda", "spl"),
        (
            "account/state layout",
            "authority and signer derivation",
            "instruction/CPI call graph",
            "asset flow and custody",
            "state-transition and randomness dependencies",
        ),
        (
            "only intended authorities mutate protected state",
            "asset conservation and fee invariants hold",
            "state transitions are deterministic and replay-safe where required",
        ),
    ),
    ConstructionDomainProfile(
        "exploit_memory",
        ("buffer overflow", "rop", "heap", "stack", "memory corruption", "gdb", "pwndbg", "crash", "fuzz"),
        (
            "input-to-memory data path",
            "allocation/lifetime model",
            "calling convention and control-flow boundary",
            "mitigations and executable-memory policy",
            "crash primitive and reproducibility",
        ),
        (
            "memory ownership and bounds are preserved",
            "control data cannot be influenced outside intended paths",
            "a crash is not promoted to exploitability without a demonstrated primitive",
        ),
    ),
    ConstructionDomainProfile(
        "cloud_container",
        ("docker", "container", "kubernetes", "k8s", "aws", "azure", "gcp", "cloud", "iam"),
        (
            "identity/IAM trust graph",
            "container/host boundary",
            "network policy and service exposure",
            "secret/configuration source",
            "control-plane versus workload authority",
        ),
        (
            "tenant/workload isolation holds",
            "credentials grant only intended scope",
            "control-plane mutations require intended authority",
        ),
    ),
)


def select_construction_profile(context: str) -> ConstructionDomainProfile | None:
    normalized = context.casefold()
    ranked: list[tuple[int, int, ConstructionDomainProfile]] = []
    for index, profile in enumerate(CONSTRUCTION_PROFILES):
        hits = sum(marker in normalized for marker in profile.markers)
        if hits:
            ranked.append((hits, -index, profile))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], -item[1]))
    return ranked[0][2]


def mechanism_chain_score(chain: MechanismChain) -> float:
    """Geometric mechanism completeness; weak causal links dominate the score."""
    weights = {
        "component": 0.90,
        "interface": 1.10,
        "trust_boundary": 1.35,
        "state_transition": 1.20,
        "invariant": 1.45,
        "evidence": 1.50,
        "expected_observation": 1.15,
    }
    values = asdict(chain)
    eps = 1e-6
    numerator = sum(
        weights[name] * math.log(max(_clip(values[name]), eps))
        for name in weights
    )
    return round(math.exp(numerator / sum(weights.values())), 6)


def structural_discovery_priority(model: ConstructionModel) -> tuple[tuple[str, float], ...]:
    """Return weighted deficits, highest-value missing structural fact first."""
    values = model.to_dict()
    ranked = [
        (name, round(_COVERAGE_WEIGHTS[name] * (1.0 - _clip(value)), 6))
        for name, value in values.items()
    ]
    ranked.sort(key=lambda item: (-item[1], item[0]))
    return tuple(ranked)


_COVERAGE_WEIGHTS = {
    "topology": 0.90,
    "interfaces": 1.20,
    "data_flow": 1.25,
    "state_model": 1.15,
    "trust_boundaries": 1.40,
    "invariants": 1.50,
    "dependencies": 0.85,
    "controls": 1.20,
}


def construction_coverage(model: ConstructionModel) -> float:
    """Weighted geometric coverage in [0, 1].

    K = exp(sum(w_i * ln(max(x_i, eps))) / sum(w_i))

    A geometric mean is deliberate: one nearly-unknown critical dimension
    cannot be hidden by strong scores elsewhere.
    """
    eps = 1e-6
    values = model.to_dict()
    numerator = sum(
        weight * math.log(max(_clip(values[name]), eps))
        for name, weight in _COVERAGE_WEIGHTS.items()
    )
    denominator = sum(_COVERAGE_WEIGHTS.values())
    return round(math.exp(numerator / denominator), 6)


def construction_gaps(model: ConstructionModel) -> tuple[str, ...]:
    """Rank missing structural knowledge by weighted deficit."""
    values = model.to_dict()
    ranked = sorted(
        values,
        key=lambda name: (
            -_COVERAGE_WEIGHTS[name] * (1.0 - _clip(values[name])),
            name,
        ),
    )
    return tuple(ranked)


def break_readiness(
    *,
    construction: float,
    evidence: float,
    mechanism_linkage: float,
    discriminative_power: float,
    reversibility: float,
    safety: float,
    uncertainty: float,
    noise: float,
) -> float:
    """Readiness for the next audit/attack test.

    R = K^1.60 * E^1.35 * M^1.45 * D^1.20 * V^1.00 * S^1.10
        * exp(-(1.10*U + 0.75*N))

    K=construction coverage, E=evidence, M=mechanism linkage, D=ability to
    discriminate hypotheses, V=reversibility, S=safety, U=uncertainty, N=noise.
    """
    k = _clip(construction)
    e = _clip(evidence)
    m = _clip(mechanism_linkage)
    d = _clip(discriminative_power)
    v = _clip(reversibility)
    s = _clip(safety)
    u = _clip(uncertainty)
    n = _clip(noise)
    value = (
        k ** 1.60
        * e ** 1.35
        * m ** 1.45
        * d ** 1.20
        * v ** 1.00
        * s ** 1.10
        * math.exp(-(1.10 * u + 0.75 * n))
    )
    return round(value, 6)


def construction_guidance(context: str) -> str:
    """Inject a compact build-before-break discipline only for technical work."""
    normalized = context.casefold()
    markers = (
        "auditoria", "audit", "pentest", "ctf", "ataque", "attack", "exploit",
        "reverse", "revers", "malware", "ransomware", "web", "api", "rede",
        "network", "linux", "windows", "solana", "blockchain", "smart contract",
        "vulnerab", "segurança", "security",
    )
    if not any(marker in normalized for marker in markers):
        return ""

    profile = select_construction_profile(context)
    domain = ""
    if profile:
        questions = "; ".join(profile.structural_questions[:3])
        invariants = "; ".join(profile.critical_invariants[:2])
        domain = (
            f" DOMAIN={profile.name}; reconstruct: {questions}. "
            f"Critical invariants: {invariants}."
        )

    return (
        "BUILD-TO-BREAK: reconstruct the minimum viable construction model before promoting "
        "a break/audit hypothesis: COMPONENTS/TOPOLOGY -> INTERFACES -> DATA/CONTROL FLOW -> "
        "STATE -> TRUST BOUNDARIES -> INVARIANTS -> DEPENDENCIES/CONTROLS. Label each element "
        "KNOWN, UNKNOWN or INFERRED. Every proposed test must name the concrete mechanism, "
        "trust boundary/state transition, invariant under test, and expected observation that "
        "would confirm or falsify the hypothesis. If structural coverage is weak, gather the "
        "highest-weight missing structural fact instead of guessing an exploit."
        + domain
    )
