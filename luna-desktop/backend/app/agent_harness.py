"""Deterministic Agent Harness for Luna local runtime.

Architecture goals derived from the runtime/cache/memory/eval design:
- keep the LLM inside a bounded loop;
- keep tool execution operator-only in this build;
- separate ephemeral, procedural, semantic and episodic context provenance;
- cache only safe exact retrieval work with TTL/invalidation;
- never semantic-cache model answers for changing security state;
- emit compact trace metadata for evals and regression testing.

This module does not execute host commands or external tools.
"""

from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from .harness_checkpoints import CheckpointStore, HarnessCheckpoint


@dataclass(frozen=True)
class HarnessPolicy:
    version: str = "harness-v1"
    max_model_attempts: int = 2  # initial generation + one bounded replan
    max_tool_calls: int = 0  # instruction-only build
    human_approval_for_sensitive_actions: bool = True
    semantic_response_cache_enabled: bool = False
    write_actions_require_idempotency_key: bool = True
    retry_strategy: str = "exponential_backoff+jitter"
    transport_retry_limit: int = 2
    retrieval_cache_ttl_seconds: int = 300
    retrieval_cache_max_entries: int = 256


@dataclass(frozen=True)
class MemoryPlaneSnapshot:
    ephemeral_present: bool
    procedural_sources: tuple[str, ...]
    semantic_present: bool
    episodic_present: bool
    provenance: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TurnHarnessTrace:
    session_id: str
    turn_id: str
    route: str
    policy_version: str
    model_attempts: int = 0
    replans: int = 0
    guardrails_in: list[str] = field(default_factory=list)
    guardrails_out: list[str] = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0
    termination_reason: str = "pending"
    memory: MemoryPlaneSnapshot | None = None
    last_checkpoint_id: int | None = None
    checkpoint_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


@dataclass
class _CacheEntry:
    value: str
    expires_at: float
    created_at: float


class ExactTTLCache:
    """Small process-local exact cache. No semantic answer caching."""

    def __init__(self, *, max_entries: int = 256) -> None:
        self.max_entries = max(1, int(max_entries))
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = threading.RLock()

    @staticmethod
    def key(namespace: str, payload: str, version: str = "1") -> str:
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"{namespace}:{version}:{digest}"

    def get(self, key: str) -> str | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None
            return entry.value

    def put(self, key: str, value: str, *, ttl_seconds: int) -> None:
        ttl = max(1, int(ttl_seconds))
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            if len(self._entries) >= self.max_entries:
                oldest_key = min(
                    self._entries,
                    key=lambda item: self._entries[item].created_at,
                )
                self._entries.pop(oldest_key, None)
            self._entries[key] = _CacheEntry(
                value=value,
                expires_at=now + ttl,
                created_at=now,
            )

    def invalidate_namespace(self, namespace: str) -> int:
        prefix = f"{namespace}:"
        with self._lock:
            keys = [key for key in self._entries if key.startswith(prefix)]
            for key in keys:
                self._entries.pop(key, None)
            return len(keys)

    def _prune(self, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        expired = [
            key for key, entry in self._entries.items() if entry.expires_at <= current
        ]
        for key in expired:
            self._entries.pop(key, None)

    def size(self) -> int:
        with self._lock:
            self._prune()
            return len(self._entries)


class AgentHarness:
    """Bounded runtime facade around generation, memory, cache and guardrails."""

    def __init__(
        self,
        policy: HarnessPolicy | None = None,
        checkpoint_store: CheckpointStore | None = None,
    ) -> None:
        self.policy = policy or HarnessPolicy()
        self.retrieval_cache = ExactTTLCache(
            max_entries=self.policy.retrieval_cache_max_entries
        )
        self.checkpoint_store = checkpoint_store

    def attach_checkpoint_store(self, store: CheckpointStore | None) -> None:
        self.checkpoint_store = store

    def begin_turn(self, *, session_id: str, route: str) -> TurnHarnessTrace:
        trace = TurnHarnessTrace(
            session_id=session_id,
            turn_id=uuid.uuid4().hex[:16],
            route=route,
            policy_version=self.policy.version,
        )
        trace.guardrails_in.extend((
            "current_turn_factual_context",
            "secret_redaction",
            "instruction_only_tool_lock",
        ))
        return trace

    def memory_snapshot(
        self,
        *,
        evidence_delta: str = "",
        scenario_context: str = "",
        active_modules: dict[str, str] | None = None,
        project_context: str = "",
        context_summary: str = "",
        history_count: int = 0,
    ) -> MemoryPlaneSnapshot:
        modules = tuple(sorted((active_modules or {}).keys()))
        provenance: list[str] = []
        if evidence_delta or scenario_context:
            provenance.append("ephemeral:scenario+current-evidence")
        if modules:
            provenance.extend(f"procedural:{module}" for module in modules)
        if project_context:
            provenance.append("semantic:project-facts/context")
        if context_summary or history_count:
            provenance.append("episodic:recent-history/summary")
        return MemoryPlaneSnapshot(
            ephemeral_present=bool(evidence_delta or scenario_context),
            procedural_sources=modules,
            semantic_present=bool(project_context),
            episodic_present=bool(context_summary or history_count),
            provenance=tuple(provenance),
        )

    def cached_retrieval(self, *, namespace: str, payload: str) -> tuple[str | None, str]:
        key = ExactTTLCache.key(namespace, payload, self.policy.version)
        return self.retrieval_cache.get(key), key

    def store_retrieval(self, *, key: str, value: str) -> None:
        self.retrieval_cache.put(
            key,
            value,
            ttl_seconds=self.policy.retrieval_cache_ttl_seconds,
        )

    def checkpoint(
        self,
        trace: TurnHarnessTrace,
        *,
        stage: str,
        state: dict[str, Any],
        human_review_required: bool = False,
    ) -> HarnessCheckpoint | None:
        store = self.checkpoint_store
        if store is None:
            return None
        try:
            checkpoint = store.save(
                thread_id=trace.session_id,
                turn_id=trace.turn_id,
                stage=stage,
                state=state,
                human_review_required=human_review_required,
                parent_checkpoint_id=trace.last_checkpoint_id,
            )
        except Exception as error:
            trace.checkpoint_errors.append(type(error).__name__)
            return None
        trace.last_checkpoint_id = checkpoint.checkpoint_id
        return checkpoint

    def latest_checkpoint(self, thread_id: str) -> HarnessCheckpoint | None:
        if self.checkpoint_store is None:
            return None
        return self.checkpoint_store.latest(thread_id)

    def checkpoint_history(
        self,
        thread_id: str,
        *,
        limit: int = 50,
    ) -> list[HarnessCheckpoint]:
        if self.checkpoint_store is None:
            return []
        return self.checkpoint_store.history(thread_id, limit=limit)

    def record_model_attempt(self, trace: TurnHarnessTrace) -> None:
        trace.model_attempts += 1

    def should_replan(self, trace: TurnHarnessTrace, *, validation_valid: bool) -> bool:
        if validation_valid:
            return False
        return trace.model_attempts < self.policy.max_model_attempts

    def record_replan(self, trace: TurnHarnessTrace) -> None:
        trace.replans += 1

    def record_output_guardrails(
        self,
        trace: TurnHarnessTrace,
        *,
        validator_passed: bool,
        validation_reasons: tuple[str, ...] | list[str] = (),
    ) -> None:
        trace.guardrails_out[:] = [
            "response_validator",
            "construction_grounding",
            "quantitative_integrity",
            "exact_arithmetic",
            "command_policy",
            "host_safety",
        ]
        if validator_passed:
            trace.termination_reason = "validated_response"
        elif validation_reasons:
            trace.termination_reason = "guardrail_rejection"

    def finalize_error(self, trace: TurnHarnessTrace, reason: str) -> None:
        trace.termination_reason = reason

    def public_policy(self) -> dict[str, Any]:
        return {
            "version": self.policy.version,
            "max_model_attempts": self.policy.max_model_attempts,
            "max_tool_calls": self.policy.max_tool_calls,
            "human_approval_for_sensitive_actions": (
                self.policy.human_approval_for_sensitive_actions
            ),
            "semantic_response_cache_enabled": (
                self.policy.semantic_response_cache_enabled
            ),
            "write_actions_require_idempotency_key": (
                self.policy.write_actions_require_idempotency_key
            ),
            "retry_strategy": self.policy.retry_strategy,
            "transport_retry_limit": self.policy.transport_retry_limit,
            "retrieval_cache_ttl_seconds": self.policy.retrieval_cache_ttl_seconds,
            "checkpointing_enabled": self.checkpoint_store is not None,
            "checkpoint_count": (
                self.checkpoint_store.count()
                if self.checkpoint_store is not None
                else 0
            ),
        }
