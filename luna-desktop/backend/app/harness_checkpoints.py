"""Durable per-thread checkpoints for the Luna Agent Harness.

The reference architecture calls for graph/thread checkpoints that enable
resume, time-travel inspection and human-in-the-loop state. Luna keeps that
capability local-first with SQLite rather than adding LangGraph/Postgres as a
runtime dependency.

Only compact harness/control metadata should be stored here; raw secrets, tool
credentials and hidden model reasoning do not belong in checkpoints.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HarnessCheckpoint:
    checkpoint_id: int
    thread_id: str
    turn_id: str
    stage: str
    state: dict[str, Any]
    state_hash: str
    human_review_required: bool
    parent_checkpoint_id: int | None
    created_at: float
    expires_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CheckpointStore:
    """SQLite checkpoint store with WAL, TTL pruning and bounded state size."""

    def __init__(
        self,
        path: str | Path,
        *,
        ttl_days: int = 30,
        max_state_chars: int = 64_000,
    ) -> None:
        self.path = Path(path)
        self.ttl_seconds = max(1, int(ttl_days)) * 86_400
        self.max_state_chars = max(1_024, int(max_state_chars))
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self.prune_expired()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=5.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS harness_checkpoints (
                    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    state_hash TEXT NOT NULL,
                    human_review_required INTEGER NOT NULL DEFAULT 0,
                    parent_checkpoint_id INTEGER,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_harness_checkpoint_thread
                    ON harness_checkpoints(thread_id, checkpoint_id DESC);
                CREATE INDEX IF NOT EXISTS idx_harness_checkpoint_turn
                    ON harness_checkpoints(turn_id, checkpoint_id DESC);
                CREATE INDEX IF NOT EXISTS idx_harness_checkpoint_expiry
                    ON harness_checkpoints(expires_at);
                """
            )

    @staticmethod
    def _validate_identifier(value: str, field: str) -> str:
        text = str(value or "").strip()
        if not text or len(text) > 160 or any(ord(char) < 32 for char in text):
            raise ValueError(f"invalid {field}")
        return text

    def _serialize_state(self, state: dict[str, Any]) -> tuple[str, str]:
        if not isinstance(state, dict):
            raise TypeError("checkpoint state must be a dict")
        payload = json.dumps(
            state,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        if len(payload) > self.max_state_chars:
            raise ValueError("checkpoint state exceeds max_state_chars")
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return payload, digest

    def save(
        self,
        *,
        thread_id: str,
        turn_id: str,
        stage: str,
        state: dict[str, Any],
        human_review_required: bool = False,
        parent_checkpoint_id: int | None = None,
        now: float | None = None,
    ) -> HarnessCheckpoint:
        thread_id = self._validate_identifier(thread_id, "thread_id")
        turn_id = self._validate_identifier(turn_id, "turn_id")
        stage = self._validate_identifier(stage, "stage")
        payload, digest = self._serialize_state(state)
        created_at = float(time.time() if now is None else now)
        expires_at = created_at + self.ttl_seconds

        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO harness_checkpoints (
                    thread_id, turn_id, stage, state_json, state_hash,
                    human_review_required, parent_checkpoint_id, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    thread_id,
                    turn_id,
                    stage,
                    payload,
                    digest,
                    1 if human_review_required else 0,
                    parent_checkpoint_id,
                    created_at,
                    expires_at,
                ),
            )
            checkpoint_id = int(cursor.lastrowid)
        return HarnessCheckpoint(
            checkpoint_id=checkpoint_id,
            thread_id=thread_id,
            turn_id=turn_id,
            stage=stage,
            state=dict(state),
            state_hash=digest,
            human_review_required=bool(human_review_required),
            parent_checkpoint_id=parent_checkpoint_id,
            created_at=created_at,
            expires_at=expires_at,
        )

    def _row_to_checkpoint(self, row: sqlite3.Row) -> HarnessCheckpoint:
        return HarnessCheckpoint(
            checkpoint_id=int(row["checkpoint_id"]),
            thread_id=str(row["thread_id"]),
            turn_id=str(row["turn_id"]),
            stage=str(row["stage"]),
            state=json.loads(str(row["state_json"])),
            state_hash=str(row["state_hash"]),
            human_review_required=bool(row["human_review_required"]),
            parent_checkpoint_id=(
                int(row["parent_checkpoint_id"])
                if row["parent_checkpoint_id"] is not None
                else None
            ),
            created_at=float(row["created_at"]),
            expires_at=float(row["expires_at"]),
        )

    def get(self, checkpoint_id: int) -> HarnessCheckpoint | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM harness_checkpoints WHERE checkpoint_id = ?",
                (int(checkpoint_id),),
            ).fetchone()
        return self._row_to_checkpoint(row) if row is not None else None

    def latest(self, thread_id: str) -> HarnessCheckpoint | None:
        thread_id = self._validate_identifier(thread_id, "thread_id")
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM harness_checkpoints
                WHERE thread_id = ?
                ORDER BY checkpoint_id DESC LIMIT 1
                """,
                (thread_id,),
            ).fetchone()
        return self._row_to_checkpoint(row) if row is not None else None

    def history(self, thread_id: str, *, limit: int = 50) -> list[HarnessCheckpoint]:
        thread_id = self._validate_identifier(thread_id, "thread_id")
        limit = max(1, min(int(limit), 500))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM harness_checkpoints
                WHERE thread_id = ?
                ORDER BY checkpoint_id DESC LIMIT ?
                """,
                (thread_id, limit),
            ).fetchall()
        return [self._row_to_checkpoint(row) for row in rows]

    def prune_expired(self, *, now: float | None = None) -> int:
        cutoff = float(time.time() if now is None else now)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM harness_checkpoints WHERE expires_at <= ?",
                (cutoff,),
            )
            return max(0, int(cursor.rowcount))

    def count(self) -> int:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM harness_checkpoints"
            ).fetchone()
        return int(row["count"]) if row is not None else 0
