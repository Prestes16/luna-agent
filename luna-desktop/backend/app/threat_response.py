"""Threat containment, eradication and recovery guidance for malware incidents.

Instruction-only: this module prepares an operator plan and never performs
containment or remediation on the host.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThreatResponseProfile:
    name: str
    markers: tuple[str, ...]
    containment: tuple[str, ...]
    eradication: tuple[str, ...]
    recovery: tuple[str, ...]


PROFILES: tuple[ThreatResponseProfile, ...] = (
    ThreatResponseProfile(
        "ransomware",
        ("ransomware", "ransom note", "arquivos criptograf", "files encrypted"),
        (
            "isolate affected hosts and stop access to writable network shares",
            "preserve ransom note, sample, logs and representative encrypted files before destructive cleanup",
            "identify propagation and identity scope before reconnecting systems",
        ),
        (
            "remove persistence and initial-access mechanism after evidence capture",
            "revoke compromised sessions/credentials and patch the exploited entry point",
            "prefer rebuild from trusted media when system integrity cannot be established",
        ),
        (
            "restore only from known-good offline/immutable backups",
            "validate restored data and monitor for recurrence before restoring trust",
        ),
    ),
    ThreatResponseProfile(
        "stealer_rat",
        ("stealer", "credential stealer", "rat", "remote access trojan", "keylogger"),
        (
            "isolate the endpoint while preserving volatile evidence when practical",
            "revoke sessions/tokens and rotate credentials from a clean device",
        ),
        (
            "remove persistence and unauthorized remote-control components",
            "rebuild the endpoint if persistence scope or credential theft cannot be bounded",
        ),
        (
            "re-enroll trusted credentials and verify identity-provider/session state",
            "monitor for reused tokens, new logins and recurring persistence indicators",
        ),
    ),
    ThreatResponseProfile(
        "rootkit_bootkit",
        ("rootkit", "bootkit", "uefi", "kernel implant", "driver malware"),
        (
            "isolate the system and preserve disk/memory/firmware evidence before remediation",
            "treat local telemetry as potentially untrustworthy",
        ),
        (
            "prefer trusted-media rebuild/reimage over in-place cleanup",
            "verify boot chain, firmware and signed-driver state when applicable",
        ),
        (
            "restore from trusted sources and re-attest boot/system integrity",
            "rotate credentials used on the compromised system",
        ),
    ),
    ThreatResponseProfile(
        "webshell",
        ("webshell", "web shell", "malicious php", "malicious aspx", "malicious jsp"),
        (
            "isolate or restrict the exposed service while preserving web, access and process logs",
            "capture the webshell and surrounding modified files before removal",
        ),
        (
            "remove malicious artifacts and persistence",
            "fix the vulnerability or credential path that enabled deployment",
            "rotate application/server secrets and rebuild if host trust is uncertain",
        ),
        (
            "verify webroot integrity and redeploy from known-good artifacts",
            "monitor access logs and filesystem changes for recurrence",
        ),
    ),
    ThreatResponseProfile(
        "generic_malware",
        ("malware", "trojan", "loader", "dropper", "backdoor"),
        (
            "isolate affected scope without destroying evidence",
            "preserve specimen, hashes, logs and volatile evidence relevant to the incident",
        ),
        (
            "remove persistence and the proven initial-access mechanism",
            "prefer trusted rebuild when the compromise boundary is unknown",
        ),
        (
            "restore from known-good sources and verify post-recovery telemetry",
            "monitor IOCs and behavior for recurrence",
        ),
    ),
)


def select_response_profiles(context: str) -> tuple[ThreatResponseProfile, ...]:
    normalized = context.casefold()
    matches = [
        profile
        for profile in PROFILES
        if any(marker in normalized for marker in profile.markers)
    ]
    if matches:
        return tuple(matches)
    return ()


def threat_response_guidance(context: str, max_chars: int = 1_400) -> str:
    profiles = select_response_profiles(context)
    if not profiles:
        return ""

    parts: list[str] = []
    for profile in profiles[:2]:
        parts.append(
            f"{profile.name}: CONTAIN={'; '.join(profile.containment)}; "
            f"ERADICATE={'; '.join(profile.eradication)}; "
            f"RECOVER={'; '.join(profile.recovery)}"
        )

    guidance = (
        "THREAT RESPONSE (instruction-only): evidence preservation precedes destructive cleanup. "
        + " | ".join(parts)
        + ". Do not call a system clean merely because the visible sample was deleted; close the "
        "initial-access path, remove persistence, rotate exposed secrets where relevant, restore "
        "from trusted sources, and verify the post-recovery state."
    )
    return guidance[:max_chars]
