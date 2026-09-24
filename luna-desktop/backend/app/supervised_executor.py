"""Operator-controlled command executor for Luna Cyber.

This executor is deliberately separate from the model tool loop. The LLM may propose
an action, but this module recomputes deterministic execution intent and enforces the
operator grant before a process can start.

Default policy is disabled. Enabling the executor does not enable model tool-calling.
L0/L1 can be allowed independently; L2/L3 additionally require an exact, expiring
operator approval bound to the command SHA-256 and target.

No shell=True path exists. Shell control operators are rejected so an approved command
cannot silently expand into a different command chain.
"""

from __future__ import annotations

import asyncio
import hashlib
import shlex
import time
import secrets
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

from .command_execution import assess_command_execution
from .evidence_bundle import EvidenceArtifact, build_evidence_artifact
from .execution_intent import (
    APPROVAL_REQUIRED,
    AUTO,
    BLOCKED,
    L0_OBSERVE,
    L1_PROBE,
    L2_MUTATE,
    L3_HIGH_IMPACT,
    ON_DEMAND,
    ExecutionIntent,
    build_execution_intent,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def command_sha256(command: str) -> str:
    return hashlib.sha256(command.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExecutionApproval:
    command_sha256: str
    target: str | None
    authority_level: str
    issued_at: float
    expires_at: float
    scope_key: str | None = None
    allow_destructive: bool = False
    allow_persistent_change: bool = False

    @classmethod
    def issue(
        cls,
        *,
        command: str,
        target: str | None,
        authority_level: str,
        ttl_seconds: int = 120,
        scope_key: str | None = None,
        allow_destructive: bool = False,
        allow_persistent_change: bool = False,
        now: float | None = None,
    ) -> "ExecutionApproval":
        current = float(time.time() if now is None else now)
        ttl = max(1, min(int(ttl_seconds), 900))
        return cls(
            command_sha256=command_sha256(command),
            target=target,
            authority_level=authority_level,
            issued_at=current,
            expires_at=current + ttl,
            scope_key=str(scope_key) if scope_key is not None else None,
            allow_destructive=bool(allow_destructive),
            allow_persistent_change=bool(allow_persistent_change),
        )

    def matches(
        self,
        intent: ExecutionIntent,
        command: str,
        *,
        now: float | None = None,
        scope_key: str | None = None,
    ) -> bool:
        current = float(time.time() if now is None else now)
        if current > self.expires_at:
            return False
        if self.command_sha256 != command_sha256(command):
            return False
        if self.authority_level != intent.authority_level:
            return False
        if self.scope_key is not None and self.scope_key != scope_key:
            return False
        if (self.target or None) != (intent.target or None):
            return False
        if intent.destructive and not self.allow_destructive:
            return False
        if intent.persistent_change and not self.allow_persistent_change:
            return False
        return True

    def to_dict(self) -> dict:
        return asdict(self)


class ExecutionApprovalStore:
    """Ephemeral one-shot approval tokens; approvals are never model-generated."""

    def __init__(self) -> None:
        self._items: dict[str, ExecutionApproval] = {}
        self._lock = threading.RLock()

    def issue(self, approval: ExecutionApproval) -> str:
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._items[token] = approval
        return token

    def consume(self, token: str, *, now: float | None = None) -> ExecutionApproval | None:
        if not isinstance(token, str) or not token:
            return None
        current = float(time.time() if now is None else now)
        with self._lock:
            approval = self._items.pop(token, None)
            if approval is None:
                return None
            if current > approval.expires_at:
                return None
            return approval

    def prune_expired(self, *, now: float | None = None) -> int:
        current = float(time.time() if now is None else now)
        with self._lock:
            expired = [
                token
                for token, approval in self._items.items()
                if current > approval.expires_at
            ]
            for token in expired:
                self._items.pop(token, None)
            return len(expired)

    def count(self) -> int:
        with self._lock:
            return len(self._items)


@dataclass(frozen=True)
class SupervisedExecutionPolicy:
    enabled: bool = False
    allow_l0: bool = True
    allow_l1: bool = True
    allow_l2: bool = False
    allow_l3: bool = False
    timeout_seconds: int = 120
    max_output_bytes: int = 2 * 1024 * 1024

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RunnerResult:
    exit_code: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True)
class SupervisedExecutionResult:
    status: str
    backend: str
    command_sha256: str
    intent: dict
    exit_code: int | None
    stdout: str
    stderr: str
    started_at: str | None
    completed_at: str | None
    duration_ms: float | None
    truncated: bool
    denial_reasons: tuple[str, ...]
    evidence: tuple[EvidenceArtifact, ...]
    raw_evidence: tuple[tuple[str, bytes], ...] = ()

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "backend": self.backend,
            "command_sha256": self.command_sha256,
            "intent": dict(self.intent),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "truncated": self.truncated,
            "denial_reasons": list(self.denial_reasons),
            "evidence": [item.to_dict() for item in self.evidence],
        }


Runner = Callable[[tuple[str, ...], int, int], Awaitable[RunnerResult]]


def _argv_from_command(command: str) -> tuple[str, ...]:
    if not isinstance(command, str) or not command.strip():
        raise ValueError("command must be a non-empty string")

    lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;<>")
    lexer.whitespace_split = True
    tokens = tuple(lexer)
    if not tokens:
        raise ValueError("command produced no argv")

    shell_operators = {"|", "||", "&", "&&", ";", ">", ">>", "<", "<<"}
    if any(token in shell_operators for token in tokens):
        raise ValueError("shell control operators are not allowed in supervised execution")
    if any(token.startswith("$(") for token in tokens):
        raise ValueError("command substitution is not allowed in supervised execution")
    return tokens


async def _subprocess_runner(
    argv: tuple[str, ...],
    timeout_seconds: int,
    max_output_bytes: int,
) -> RunnerResult:
    process = await asyncio.create_subprocess_exec(
        *argv,
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


class SupervisedExecutor:
    def __init__(
        self,
        policy: SupervisedExecutionPolicy | None = None,
        *,
        runner: Runner | None = None,
        backend_name: str = "local-subprocess",
    ) -> None:
        self.policy = policy or SupervisedExecutionPolicy()
        self._runner = runner or _subprocess_runner
        self.backend_name = backend_name

    def public_policy(self) -> dict:
        return self.policy.to_dict()

    @staticmethod
    def preview(
        command: str,
        *,
        context: str = "",
        operator_requested_execution: bool = False,
        scope_confirmed: bool = False,
        rollback_ready: bool = False,
        verification_ready: bool = True,
        scope_target: str | None = None,
    ) -> ExecutionIntent:
        return build_execution_intent(
            command,
            context=context,
            operator_requested_execution=operator_requested_execution,
            scope_confirmed=scope_confirmed,
            rollback_ready=rollback_ready,
            verification_ready=verification_ready,
            scope_target=scope_target,
        )

    def _level_enabled(self, level: str) -> bool:
        return {
            L0_OBSERVE: self.policy.allow_l0,
            L1_PROBE: self.policy.allow_l1,
            L2_MUTATE: self.policy.allow_l2,
            L3_HIGH_IMPACT: self.policy.allow_l3,
        }.get(level, False)

    def _denial_reasons(
        self,
        *,
        intent: ExecutionIntent,
        command: str,
        approval: ExecutionApproval | None,
        now: float | None,
        approval_scope_key: str | None,
        rollback_ready: bool,
        verification_ready: bool,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if not self.policy.enabled:
            reasons.append("supervised_executor_disabled")
        if intent.authority == BLOCKED:
            reasons.append("execution_intent_blocked")
        if not self._level_enabled(intent.authority_level):
            reasons.append(f"{intent.authority_level.casefold()}_disabled")

        lifecycle = assess_command_execution(command)
        if lifecycle.interactive:
            reasons.append("interactive_command_not_supported")

        if intent.rollback_required and not rollback_ready:
            reasons.append("rollback_not_ready")
        if intent.verification_required and not verification_ready:
            reasons.append("verification_not_ready")

        if intent.authority == APPROVAL_REQUIRED:
            if approval is None:
                reasons.append("operator_approval_missing")
            elif not approval.matches(
                intent,
                command,
                now=now,
                scope_key=approval_scope_key,
            ):
                reasons.append("operator_approval_mismatch_or_expired")

        if intent.authority == ON_DEMAND and "operator_execution_not_requested" in intent.reasons:
            reasons.append("operator_execution_not_requested")
        if intent.authority not in {AUTO, ON_DEMAND, APPROVAL_REQUIRED, BLOCKED}:
            reasons.append("unknown_execution_authority")

        return tuple(dict.fromkeys(reasons))

    async def execute(
        self,
        command: str,
        *,
        context: str = "",
        operator_requested_execution: bool = False,
        scope_confirmed: bool = False,
        rollback_ready: bool = False,
        verification_ready: bool = True,
        scope_target: str | None = None,
        approval: ExecutionApproval | None = None,
        approval_scope_key: str | None = None,
        now: float | None = None,
    ) -> SupervisedExecutionResult:
        intent = self.preview(
            command,
            context=context,
            operator_requested_execution=operator_requested_execution,
            scope_confirmed=scope_confirmed,
            rollback_ready=rollback_ready,
            verification_ready=verification_ready,
            scope_target=scope_target,
        )
        digest = command_sha256(command)
        denials = self._denial_reasons(
            intent=intent,
            command=command,
            approval=approval,
            now=now,
            approval_scope_key=approval_scope_key,
            rollback_ready=rollback_ready,
            verification_ready=verification_ready,
        )
        if denials:
            return SupervisedExecutionResult(
                status="denied",
                backend=self.backend_name,
                command_sha256=digest,
                intent=intent.to_dict(),
                exit_code=None,
                stdout="",
                stderr="",
                started_at=None,
                completed_at=None,
                duration_ms=None,
                truncated=False,
                denial_reasons=denials,
                evidence=(),
            )

        try:
            argv = _argv_from_command(command)
        except ValueError as exc:
            return SupervisedExecutionResult(
                status="denied",
                backend=self.backend_name,
                command_sha256=digest,
                intent=intent.to_dict(),
                exit_code=None,
                stdout="",
                stderr="",
                started_at=None,
                completed_at=None,
                duration_ms=None,
                truncated=False,
                denial_reasons=(f"invalid_argv:{exc}",),
                evidence=(),
            )

        started_wall = _utc_now()
        started = time.perf_counter()
        try:
            runner_result = await self._runner(
                argv,
                max(1, int(self.policy.timeout_seconds)),
                max(1024, int(self.policy.max_output_bytes)),
            )
            duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
            completed_wall = _utc_now()
        except asyncio.TimeoutError:
            duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
            return SupervisedExecutionResult(
                status="timeout",
                backend=self.backend_name,
                command_sha256=digest,
                intent=intent.to_dict(),
                exit_code=None,
                stdout="",
                stderr="execution timed out",
                started_at=started_wall,
                completed_at=_utc_now(),
                duration_ms=duration_ms,
                truncated=False,
                denial_reasons=(),
                evidence=(),
            )
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
            return SupervisedExecutionResult(
                status="error",
                backend=self.backend_name,
                command_sha256=digest,
                intent=intent.to_dict(),
                exit_code=None,
                stdout="",
                stderr=f"{type(exc).__name__}: {exc}",
                started_at=started_wall,
                completed_at=_utc_now(),
                duration_ms=duration_ms,
                truncated=False,
                denial_reasons=(),
                evidence=(),
            )

        max_bytes = max(1024, int(self.policy.max_output_bytes))
        stdout_raw = runner_result.stdout
        stderr_raw = runner_result.stderr
        truncated = len(stdout_raw) > max_bytes or len(stderr_raw) > max_bytes
        stdout_raw = stdout_raw[:max_bytes]
        stderr_raw = stderr_raw[:max_bytes]

        evidence: list[EvidenceArtifact] = []
        if stdout_raw:
            evidence.append(
                build_evidence_artifact(
                    kind="stdout",
                    data=stdout_raw,
                    media_type="text/plain",
                    source=f"executor:{self.backend_name}",
                    observed_at=completed_wall,
                )
            )
        if stderr_raw:
            evidence.append(
                build_evidence_artifact(
                    kind="stderr",
                    data=stderr_raw,
                    media_type="text/plain",
                    source=f"executor:{self.backend_name}",
                    observed_at=completed_wall,
                )
            )

        raw_evidence: list[tuple[str, bytes]] = [
            ("command", command.encode("utf-8")),
        ]
        if stdout_raw:
            raw_evidence.append(("stdout", stdout_raw))
        if stderr_raw:
            raw_evidence.append(("stderr", stderr_raw))

        return SupervisedExecutionResult(
            status="executed",
            backend=self.backend_name,
            command_sha256=digest,
            intent=intent.to_dict(),
            exit_code=runner_result.exit_code,
            stdout=stdout_raw.decode("utf-8", errors="replace"),
            stderr=stderr_raw.decode("utf-8", errors="replace"),
            started_at=started_wall,
            completed_at=completed_wall,
            duration_ms=duration_ms,
            truncated=truncated,
            denial_reasons=(),
            evidence=tuple(evidence),
            raw_evidence=tuple(raw_evidence),
        )
