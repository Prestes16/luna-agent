"""Execution backends for Luna's supervised executor.

The backend answers one question only: *where* a previously-authorized argv is run.
It never decides whether execution is allowed; that remains the deterministic
ExecutionIntent / SupervisedExecutor policy.

Two backends are supported:
- local subprocess on the backend host;
- Kali over OpenSSH using the system ssh client.

The SSH backend preserves argv semantics by quoting each remote argument with
shlex.join() after the supervised executor has already rejected shell control
operators. Host-key verification is never disabled.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import shlex
import shutil
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath

from .supervised_executor import RunnerResult


_HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
_USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
_HOST_KEY_POLICIES = frozenset({"strict", "accept-new"})


@dataclass(frozen=True)
class SSHExecutionConfig:
    host: str
    user: str
    port: int = 22
    identity_file: str = ""
    known_hosts_file: str = ""
    host_key_policy: str = "strict"
    connect_timeout_seconds: int = 10
    ssh_binary: str = "ssh"

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "SSHExecutionConfig":
        """Parse the Kali SSH contract strictly.

        Invalid configured numeric values are rejected instead of silently clamped
        or replaced with defaults. That keeps execution backend selection fail-closed.
        """
        env = os.environ if environ is None else environ

        def parse_int(name: str, default: int, minimum: int, maximum: int) -> int:
            raw = str(env.get(name, "") or "").strip()
            if not raw:
                return default
            try:
                value = int(raw, 10)
            except ValueError as exc:
                raise ValueError(f"invalid {name}") from exc
            if not minimum <= value <= maximum:
                raise ValueError(
                    f"{name} must be between {minimum} and {maximum}"
                )
            return value

        return cls(
            host=str(env.get("LUNA_KALI_SSH_HOST", "") or ""),
            user=str(env.get("LUNA_KALI_SSH_USER", "") or ""),
            port=parse_int("LUNA_KALI_SSH_PORT", 22, 1, 65535),
            identity_file=str(env.get("LUNA_KALI_SSH_IDENTITY", "") or ""),
            known_hosts_file=str(env.get("LUNA_KALI_SSH_KNOWN_HOSTS", "") or ""),
            host_key_policy=str(
                env.get("LUNA_KALI_SSH_HOST_KEY_POLICY", "strict") or "strict"
            ),
            connect_timeout_seconds=parse_int(
                "LUNA_KALI_SSH_CONNECT_TIMEOUT", 10, 1, 120
            ),
            ssh_binary=str(env.get("LUNA_KALI_SSH_BINARY", "ssh") or "ssh"),
        ).validated()

    def validated(self) -> "SSHExecutionConfig":
        host = str(self.host or "").strip()
        user = str(self.user or "").strip()
        if not host or len(host) > 253:
            raise ValueError("Kali SSH host is required")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if not _HOST_RE.fullmatch(host):
                raise ValueError("invalid Kali SSH host")
        if not _USER_RE.fullmatch(user):
            raise ValueError("invalid Kali SSH user")

        if isinstance(self.port, bool):
            raise ValueError("invalid Kali SSH port")
        port = int(self.port)
        if not 1 <= port <= 65535:
            raise ValueError("invalid Kali SSH port")

        policy = str(self.host_key_policy or "strict").casefold().strip()
        if policy not in _HOST_KEY_POLICIES:
            raise ValueError("invalid SSH host-key policy")

        connect_timeout = int(self.connect_timeout_seconds)
        if not 1 <= connect_timeout <= 120:
            raise ValueError("invalid SSH connect timeout")

        identity = str(self.identity_file or "").strip()
        known_hosts = str(self.known_hosts_file or "").strip()
        ssh_binary = str(self.ssh_binary or "ssh").strip()
        for name, value in (
            ("identity_file", identity),
            ("known_hosts_file", known_hosts),
            ("ssh_binary", ssh_binary),
        ):
            if "\x00" in value or "\r" in value or "\n" in value:
                raise ValueError(f"invalid {name}")
        if not ssh_binary:
            raise ValueError("invalid ssh_binary")

        return SSHExecutionConfig(
            host=host,
            user=user,
            port=port,
            identity_file=identity,
            known_hosts_file=known_hosts,
            host_key_policy=policy,
            connect_timeout_seconds=connect_timeout,
            ssh_binary=ssh_binary,
        )

    def public_dict(self) -> dict:
        data = asdict(self.validated())
        data["identity_file"] = bool(data["identity_file"])
        data["known_hosts_file"] = bool(data["known_hosts_file"])
        binary_text = str(data["ssh_binary"] or "ssh")
        data["ssh_binary"] = (
            PureWindowsPath(binary_text).name
            if "\\" in binary_text
            else Path(binary_text).name
        ) or "ssh"
        return data


def resolve_ssh_binary(config: SSHExecutionConfig) -> str | None:
    """Resolve the configured OpenSSH client without executing it."""
    cfg = config.validated()
    resolved = shutil.which(cfg.ssh_binary)
    if resolved:
        return resolved
    candidate = Path(cfg.ssh_binary).expanduser()
    if candidate.is_file():
        return str(candidate.resolve())
    return None


def ssh_local_file_issues(config: SSHExecutionConfig) -> tuple[str, ...]:
    """Validate only explicitly configured local SSH files.

    Identity is optional because BatchMode may use ssh-agent/default keys.
    A configured identity must exist. A configured strict known_hosts file must
    already exist because strict host-key verification cannot learn the key.
    """
    cfg = config.validated()
    issues: list[str] = []
    if cfg.identity_file and not Path(cfg.identity_file).expanduser().is_file():
        issues.append("identity_file_not_found")
    if cfg.known_hosts_file:
        known_hosts = Path(cfg.known_hosts_file).expanduser()
        if cfg.host_key_policy == "strict" and not known_hosts.is_file():
            issues.append("known_hosts_file_not_found")
        elif cfg.host_key_policy == "accept-new" and not known_hosts.parent.exists():
            issues.append("known_hosts_parent_not_found")
    return tuple(issues)


def build_ssh_process_argv(
    config: SSHExecutionConfig,
    remote_argv: tuple[str, ...],
) -> tuple[str, ...]:
    cfg = config.validated()
    if not remote_argv:
        raise ValueError("remote argv must not be empty")

    remote_command = shlex.join(remote_argv)
    ssh_argv: list[str] = [
        cfg.ssh_binary,
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={cfg.connect_timeout_seconds}",
        "-o",
        (
            "StrictHostKeyChecking=yes"
            if cfg.host_key_policy == "strict"
            else "StrictHostKeyChecking=accept-new"
        ),
        "-p",
        str(cfg.port),
    ]
    if cfg.identity_file:
        ssh_argv.extend(("-i", cfg.identity_file))
    if cfg.known_hosts_file:
        ssh_argv.extend(
            ("-o", f"UserKnownHostsFile={cfg.known_hosts_file}")
        )
    ssh_argv.extend(("--", f"{cfg.user}@{cfg.host}", remote_command))
    return tuple(ssh_argv)


def build_ssh_runner(config: SSHExecutionConfig):
    cfg = config.validated()

    async def runner(
        remote_argv: tuple[str, ...],
        timeout_seconds: int,
        max_output_bytes: int,
    ) -> RunnerResult:
        process_argv = build_ssh_process_argv(cfg, remote_argv)
        process = await asyncio.create_subprocess_exec(
            *process_argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=max(1, int(timeout_seconds)),
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            raise

        return RunnerResult(
            exit_code=int(process.returncode or 0),
            stdout=stdout[: max_output_bytes + 1],
            stderr=stderr[: max_output_bytes + 1],
        )

    return runner
