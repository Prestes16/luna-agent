"""Fail-closed host-safety policy for operator-run commands.

The current Luna build is instruction-only: it never executes these commands.
This module protects the operator by classifying host-impact and requiring a
staged preflight for commands that could damage availability, configuration,
bootability, networking, or data.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import asdict, dataclass

from .command_execution import assess_command_execution


_REMOTE_PIPE_EXEC_PATTERNS = (
    re.compile(r"(?is)\bcurl\b[^\n|;]*\|\s*(?:sudo\s+)?(?:sh|bash|zsh)\b"),
    re.compile(r"(?is)\bwget\b[^\n|;]*\|\s*(?:sudo\s+)?(?:sh|bash|zsh)\b"),
    re.compile(r"(?is)\b(?:irm|iwr|invoke-restmethod|invoke-webrequest)\b[^\n|;]*\|\s*(?:iex|invoke-expression)\b"),
)

_CRITICAL_STORAGE_PATTERNS = (
    re.compile(r"(?i)\b(?:mkfs(?:\.[a-z0-9]+)?|wipefs|fdisk|cfdisk|sfdisk|parted)\b"),
    re.compile(r"(?i)\bdd\b[^\n]*\bof=/dev/(?:sd|nvme|vd|xvd|mmcblk)[^\s]*"),
    re.compile(r"(?i)\b(?:diskpart|format(?:\.com)?)\b"),
)

_BOOT_PATTERNS = (
    re.compile(r"(?i)\b(?:grub-install|grub-mkconfig|update-grub|efibootmgr)\b"),
    re.compile(r"(?i)\b(?:bcdedit|bootrec|bootsect)\b"),
)

_SYSTEM_TREE_PATTERNS = (
    re.compile(r"(?i)\brm\b[^\n]*(?:-r|-rf|-fr)[^\n]*(?:\s/\s*$|\s/(?:boot|etc|usr|var|home)(?:/|\s|$))"),
    re.compile(r"(?i)\b(?:chmod|chown)\b[^\n]*-R[^\n]*(?:\s/\s*$|\s/(?:boot|etc|usr|var|home)(?:/|\s|$))"),
    re.compile(r"(?i)\bfind\s+/(?:\s|[^\n]*)-delete\b"),
    re.compile(r"(?i)\bremove-item\b[^\n]*-(?:recurse|r)\b[^\n]*(?:[a-z]:\\+(?:windows|program files|users)(?:\\+|\s|$))"),
    re.compile(r"(?i)\b(?:icacls|takeown)\b[^\n]*(?:[a-z]:\\+(?:windows|program files|users))[^\n]*(?:/t|/r)\b"),
)

_FIREWALL_ROUTE_PATTERNS = (
    re.compile(r"(?i)\biptables\b.*\s-F\b"),
    re.compile(r"(?i)\bnft\b.*\bflush\s+ruleset\b"),
    re.compile(r"(?i)\bufw\s+(?:reset|disable)\b"),
    re.compile(r"(?i)\bip\s+(?:route|addr)\s+flush\b"),
    re.compile(r"(?i)\broute\s+(?:del|delete)\b"),
    re.compile(r"(?i)\b(?:new-netroute|remove-netroute|set-dnsclientserveraddress)\b"),
)

_CONNECTIVITY_PATTERNS = (
    re.compile(r"(?i)\bip\s+link\s+set\b[^\n]*\b(?:up|down)\b"),
    re.compile(r"(?i)\bip\s+(?:route|addr)\s+(?:add|replace|del|delete|flush)\b"),
    re.compile(r"(?i)\bresolvectl\s+(?:dns|domain|default-route)\b"),
    re.compile(r"(?i)\bwg-quick\s+(?:up|down)\b"),
    re.compile(r"(?i)\bopenvpn\b"),
    re.compile(r"(?i)\bnmcli\s+networking\s+off\b"),
    re.compile(r"(?i)\bsystemctl\s+(?:stop|restart)\s+(?:networkmanager|networking|systemd-resolved|ssh|sshd)\b"),
    re.compile(r"(?i)\bdisable-netadapter\b"),
    re.compile(r"(?i)\bnetsh\s+interface\b[^\n]*\bdisabled\b"),
)

_SECURITY_CONTROL_PATTERNS = (
    re.compile(r"(?i)\bset-mppreference\b[^\n]*-disablerealtimemonitoring\s+\$?true\b"),
    re.compile(r"(?i)\b(?:sc(?:\.exe)?\s+stop|stop-service)\s+(?:windefend|mpssvc)\b"),
    re.compile(r"(?i)\bset-netfirewallprofile\b[^\n]*-enabled\s+(?:false|0)\b"),
)

_SYSTEM_CONFIG_PATH_PATTERNS = (
    re.compile(r"(?i)(?:^|\s)/(?:etc|boot|usr/lib/systemd|lib/systemd)/"),
    re.compile(r"(?i)\bHKLM[:\\]"),
)

_CONFIG_WRITE_PATTERNS = (
    re.compile(r"(?i)(?:>|>>)\s*/(?:etc|boot|usr/lib/systemd|lib/systemd)/"),
    re.compile(r"(?i)\btee\b[^\n]*/(?:etc|boot|usr/lib/systemd|lib/systemd)/"),
    re.compile(r"(?i)\bsed\b[^\n]*\s-i(?:\s|$)[^\n]*/(?:etc|boot|usr/lib/systemd|lib/systemd)/"),
    re.compile(r"(?i)\b(?:cp|mv|install)\b[^\n]*/(?:etc|boot|usr/lib/systemd|lib/systemd)/"),
    re.compile(r"(?i)\b(?:nano|vim|vi)\b[^\n]*/(?:etc|boot|usr/lib/systemd|lib/systemd)/"),
    re.compile(r"(?i)\b(?:reg(?:\.exe)?\s+(?:add|delete)|set-itemproperty|new-itemproperty)\b.*\bHKLM[:\\]"),
)

_PERSISTENCE_PATTERNS = (
    re.compile(r"(?i)\bsystemctl\s+(?:enable|disable|mask|unmask)\b"),
    re.compile(r"(?i)\b(?:schtasks|sc(?:\.exe)?)\b.*\b(?:/create|create|config)\b"),
    re.compile(r"(?i)\bcrontab\b(?!\s+-l\b)"),
)

_LAB_MARKERS = (
    "vm descartável", "vm descartavel", "disposable vm", "snapshot criado",
    "snapshot confirmado", "snapshot ready", "backup confirmado", "backup feito",
    "laboratório descartável", "laboratorio descartavel",
)

_EXPLICIT_HIGH_IMPACT_MARKERS = (
    "formatar", "format", "particionar", "partition", "bootloader", "grub",
    "bcd", "wipe", "apagar disco", "limpar firewall", "flush firewall",
    "alterar rota", "mudar rota", "editar /etc", "alterar /etc",
    "desativar defender", "disable defender", "desativar firewall", "disable firewall",
    "desativar adaptador", "disable adapter", "instalar", "install", "remover pacote", "remove package", "upgrade",
    "atualizar pacotes",
)

_ENVIRONMENT_MARKERS = (
    "kali", "linux", "windows", "powershell", "wsl", "vm", "virtual machine",
)


@dataclass(frozen=True)
class HostSafetyAssessment:
    command: str
    host_impact: str
    critical_storage: bool
    boot_change: bool
    system_tree_change: bool
    network_control_change: bool
    connectivity_change: bool
    security_control_reduction: bool
    remote_pipe_execution: bool
    persistent_change: bool
    environment_confirmed: bool
    protected_lab_confirmed: bool
    device_target_confirmed: bool
    destructive_target_confirmed: bool
    backup_or_snapshot_required: bool
    rollback_required: bool
    safe_to_recommend_now: bool
    risk: float
    utility: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _matches_any(command: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(command) for pattern in patterns)


def _context_flag(context: str, markers: tuple[str, ...]) -> bool:
    normalized = context.casefold()
    return any(marker in normalized for marker in markers)


def _device_targets(command: str) -> tuple[str, ...]:
    values = re.findall(
        r"(?i)(/dev/(?:sd[a-z]\d*|nvme\d+n\d+(?:p\d+)?|vd[a-z]\d*|xvd[a-z]\d*|mmcblk\d+(?:p\d+)?))",
        command,
    )
    return tuple(dict.fromkeys(value.casefold() for value in values))


def _effective_tokens(command: str) -> list[str]:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    if not tokens:
        return []
    if tokens[0].casefold() == "sudo":
        index = 1
        while index < len(tokens) and tokens[index].startswith("-"):
            index += 1
        return tokens[index:]
    return tokens


def _destructive_targets(command: str) -> tuple[str, ...]:
    tokens = _effective_tokens(command)
    if not tokens:
        return ()
    tool = tokens[0].casefold()
    if tool in {"rm", "rmdir", "shred", "kill", "pkill"}:
        targets = [
            token for token in tokens[1:]
            if token and not token.startswith("-")
        ]
        return tuple(dict.fromkeys(target.casefold() for target in targets))
    return ()


def _destructive_target_confirmed(command: str, context: str, lifecycle) -> bool:
    if not lifecycle.destructive:
        return True

    normalized = context.casefold()
    targets = _destructive_targets(command)
    if targets:
        return all(target in normalized for target in targets)

    tool_tokens = _effective_tokens(command)
    tool = tool_tokens[0].casefold() if tool_tokens else ""
    if tool.startswith("mkfs") or tool in {"wipefs", "fdisk", "cfdisk", "sfdisk", "parted"}:
        devices = _device_targets(command)
        return bool(devices and all(device in normalized for device in devices))
    if tool in {"reboot", "shutdown", "poweroff", "halt"}:
        return any(
            marker in normalized
            for marker in ("reboot", "reiniciar", "shutdown", "desligar", "poweroff", "halt")
        )
    return False


def assess_host_safety(command: str, *, context: str = "") -> HostSafetyAssessment:
    lifecycle = assess_command_execution(command)
    critical_storage = _matches_any(command, _CRITICAL_STORAGE_PATTERNS)
    boot_change = _matches_any(command, _BOOT_PATTERNS)
    system_tree_change = _matches_any(command, _SYSTEM_TREE_PATTERNS)
    network_control_change = _matches_any(command, _FIREWALL_ROUTE_PATTERNS)
    connectivity_change = _matches_any(command, _CONNECTIVITY_PATTERNS)
    security_control_reduction = _matches_any(command, _SECURITY_CONTROL_PATTERNS)
    network_control_change = bool(network_control_change or connectivity_change)
    remote_pipe_execution = _matches_any(command, _REMOTE_PIPE_EXEC_PATTERNS)
    system_config_path = _matches_any(command, _SYSTEM_CONFIG_PATH_PATTERNS)
    config_write = _matches_any(command, _CONFIG_WRITE_PATTERNS)
    system_config_change = bool(
        system_config_path and (lifecycle.mutates_state or config_write)
    )
    persistence_change = _matches_any(command, _PERSISTENCE_PATTERNS)

    environment_confirmed = _context_flag(context, _ENVIRONMENT_MARKERS)
    protected_lab_confirmed = _context_flag(context, _LAB_MARKERS)
    explicit_high_impact = _context_flag(context, _EXPLICIT_HIGH_IMPACT_MARKERS)
    device_targets = _device_targets(command)
    context_lower = context.casefold()
    device_target_confirmed = bool(
        device_targets and all(target in context_lower for target in device_targets)
    )
    if critical_storage and not device_targets:
        device_target_confirmed = False
    destructive_target_confirmed = _destructive_target_confirmed(
        command, context, lifecycle
    )

    persistent_change = bool(
        lifecycle.persistent_change or system_config_change or persistence_change
    )
    high_impact = any((
        critical_storage, boot_change, system_tree_change, network_control_change,
        connectivity_change, security_control_reduction, remote_pipe_execution,
        system_config_change, persistence_change, persistent_change,
    ))
    backup_or_snapshot_required = bool(
        critical_storage or boot_change or system_tree_change or system_config_change
    )
    rollback_required = bool(
        lifecycle.mutates_state or network_control_change or persistent_change or high_impact
    )

    reasons: list[str] = []
    if remote_pipe_execution:
        reasons.append("remote_content_piped_to_shell")
    if critical_storage:
        reasons.append("critical_storage_mutation")
    if boot_change:
        reasons.append("boot_configuration_mutation")
    if system_tree_change:
        reasons.append("system_tree_recursive_mutation")
    if network_control_change:
        reasons.append("network_control_plane_mutation")
    if connectivity_change:
        reasons.append("host_connectivity_mutation")
    if security_control_reduction:
        reasons.append("security_control_reduction")
    if system_config_change:
        reasons.append("system_configuration_mutation")
    if persistence_change:
        reasons.append("persistence_configuration_mutation")
    if high_impact and not environment_confirmed:
        reasons.append("execution_environment_not_confirmed")
    if (critical_storage or boot_change) and not protected_lab_confirmed:
        reasons.append("snapshot_or_backup_not_confirmed")
    if critical_storage and not device_target_confirmed:
        reasons.append("storage_device_target_not_confirmed")
    if lifecycle.destructive and not destructive_target_confirmed:
        reasons.append("destructive_target_not_confirmed")
    if high_impact and not explicit_high_impact and not protected_lab_confirmed:
        reasons.append("high_impact_intent_not_explicit")

    hard_block = (
        remote_pipe_execution
        or system_tree_change
        or (lifecycle.destructive and not destructive_target_confirmed)
    )
    gated_block = (critical_storage or boot_change) and not (
        environment_confirmed
        and protected_lab_confirmed
        and explicit_high_impact
        and (device_target_confirmed if critical_storage else True)
    )
    security_gate = security_control_reduction and not (
        environment_confirmed and protected_lab_confirmed and explicit_high_impact
    )
    environmental_block = high_impact and not environment_confirmed
    safe_to_recommend_now = not (
        hard_block or gated_block or security_gate or environmental_block
    )

    base_risk = 0.08
    base_risk += 0.92 if remote_pipe_execution else 0.0
    base_risk += 0.88 if critical_storage else 0.0
    base_risk += 0.82 if boot_change else 0.0
    base_risk += 0.90 if system_tree_change else 0.0
    base_risk += 0.55 if network_control_change else 0.0
    base_risk += 0.72 if security_control_reduction else 0.0
    base_risk += 0.42 if persistent_change else 0.0
    base_risk += 0.22 if lifecycle.privilege_required else 0.0
    risk = min(1.0, base_risk)

    reversibility = 1.0 if lifecycle.reversible else 0.18
    environment_factor = 1.0 if environment_confirmed else (0.35 if high_impact else 0.85)
    lab_factor = 1.0 if protected_lab_confirmed else (0.30 if critical_storage or boot_change else 0.90)
    review_factor = 0.05 if remote_pipe_execution else 1.0
    utility = (
        (1.0 - risk) ** 1.55
        * reversibility ** 1.25
        * environment_factor ** 1.10
        * lab_factor ** 1.15
        * review_factor ** 1.80
    )

    if remote_pipe_execution or system_tree_change:
        host_impact = "blocked"
    elif critical_storage or boot_change:
        host_impact = "critical"
    elif network_control_change or persistent_change:
        host_impact = "high"
    elif lifecycle.mutates_state:
        host_impact = "moderate"
    else:
        host_impact = "low"

    return HostSafetyAssessment(
        command=command,
        host_impact=host_impact,
        critical_storage=critical_storage,
        boot_change=boot_change,
        system_tree_change=system_tree_change,
        network_control_change=network_control_change,
        connectivity_change=connectivity_change,
        security_control_reduction=security_control_reduction,
        remote_pipe_execution=remote_pipe_execution,
        persistent_change=persistent_change,
        environment_confirmed=environment_confirmed,
        protected_lab_confirmed=protected_lab_confirmed,
        device_target_confirmed=device_target_confirmed,
        destructive_target_confirmed=destructive_target_confirmed,
        backup_or_snapshot_required=backup_or_snapshot_required,
        rollback_required=rollback_required,
        safe_to_recommend_now=safe_to_recommend_now,
        risk=round(risk, 4),
        utility=round(utility, 4),
        reasons=tuple(dict.fromkeys(reasons)),
    )


def host_safety_guidance(context: str) -> str:
    return (
        "HOST SAFETY: the operator executes every command. For any privileged or state-changing "
        "action use PRECHECK -> ONE CHANGE -> VERIFY -> ROLLBACK/CONTINUE. Never pipe remote "
        "downloads directly into a shell. Never use recursive deletion/permission changes on "
        "system trees. Disk/partition/boot operations require an explicitly identified environment, "
        "a confirmed snapshot/backup and explicit operator intent before the command is proposed. "
        "System config/firewall/route/persistence changes require factual current state, reversible "
        "rollback instructions and post-change verification. Prefer read-only discovery first."
    )
