"""Local typed memory plane for Luna Cyber.

Design goals:
- local-only SQLite persistence;
- typed records with explicit provenance and source hashes;
- FTS5 lexical retrieval with a deterministic recent fallback;
- strict separation between durable facts/evidence, hypotheses and episodes;
- never treat model output as a durable fact automatically;
- preserve exact authorized evidence, including credentials/sensitive artifacts;
- classify sensitive artifacts instead of redacting them;
- no semantic response cache and no remote/vector dependency.

The JSON project store remains compatible during migration. ProjectStore dual-writes
and lazily syncs legacy facts/messages into this plane.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


MEMORY_KINDS = frozenset(
    {
        "evidence",
        "operator_fact",
        "derived_fact",
        "validated_finding",
        "hypothesis",
        "episode",
        "procedure",
        "decision",
    }
)
MEMORY_STATUSES = frozenset({"active", "superseded"})
EVIDENCE_LEVELS = frozenset(
    {
        "observed",
        "declared",
        "deterministic",
        "validated",
        "hypothesis",
        "episode",
        "model_output",
        "procedural",
    }
)
SEMANTIC_FACT_KINDS = (
    "evidence",
    "operator_fact",
    "derived_fact",
    "validated_finding",
)
EPISODIC_KINDS = ("episode", "decision")
HYPOTHESIS_KINDS = ("hypothesis",)

_TOKEN_RE = re.compile(r"[^\W_]{2,}", re.UNICODE)
_STOP_TERMS = frozenset(
    {
        "para", "como", "com", "sem", "uma", "que", "das", "dos", "por",
        "the", "and", "from", "this", "that", "sobre", "onde", "quando",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


SENSITIVITY_LEVELS = frozenset({"normal", "sensitive", "credential", "classified"})


def classify_sensitive_artifact(value: str) -> str:
    """Classify exact local evidence without altering the artifact."""
    text = str(value or "")
    normalized = text.casefold()
    if re.search(
        r"(?im)(authorization\s*:\s*bearer\s+\S+|set-cookie\s*:|"
        r"api[_-]?key\s*[:=]|password\s*[:=]|passwd\s*[:=]|"
        r"secret\s*[:=]|private[_-]?key\s*[:=]|"
        r"-----begin [^-]*private key-----)",
        text,
    ):
        return "credential"
    if any(
        marker in normalized
        for marker in (
            "classified", "confidential", "restricted", "sigil",
            "investigação classificada", "investigacao classificada",
        )
    ):
        return "classified"
    if any(
        marker in normalized
        for marker in (
            "credential", "credencial", "token", "cookie", "session id",
            "session_id", "access_token", "refresh_token",
        )
    ):
        return "sensitive"
    return "normal"


@dataclass(frozen=True)
class MemoryRecord:
    id: int
    project_id: int
    kind: str
    content: str
    provenance: str
    source: str
    source_hash: str
    observed_at: str
    evidence_level: str
    valid_until: Optional[str]
    supersedes: Optional[int]
    status: str
    sensitivity: str
    content_sha256: str
    content_bytes: int
    secret_redacted: bool
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "kind": self.kind,
            "content": self.content,
            "provenance": self.provenance,
            "source": self.source,
            "source_hash": self.source_hash,
            "observed_at": self.observed_at,
            "evidence_level": self.evidence_level,
            "valid_until": self.valid_until,
            "supersedes": self.supersedes,
            "status": self.status,
            "sensitivity": self.sensitivity,
            "content_sha256": self.content_sha256,
            "content_bytes": self.content_bytes,
            "secret_redacted": self.secret_redacted,
            "metadata": dict(self.metadata),
        }


class MemoryPlane:
    """SQLite/FTS5 typed memory with explicit fact/hypothesis separation."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.fts5_enabled = False
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    evidence_level TEXT NOT NULL,
                    valid_until TEXT,
                    supersedes INTEGER,
                    status TEXT NOT NULL DEFAULT 'active',
                    sensitivity TEXT NOT NULL DEFAULT 'normal',
                    content_sha256 TEXT NOT NULL DEFAULT '',
                    content_bytes INTEGER NOT NULL DEFAULT 0,
                    secret_redacted INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(project_id, source_hash)
                );

                CREATE INDEX IF NOT EXISTS idx_memory_project_kind_status
                    ON memory_records(project_id, kind, status, id DESC);
                CREATE INDEX IF NOT EXISTS idx_memory_project_observed
                    ON memory_records(project_id, observed_at DESC, id DESC);
                CREATE INDEX IF NOT EXISTS idx_memory_source_hash
                    ON memory_records(project_id, source_hash);
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(memory_records)").fetchall()
            }
            if "sensitivity" not in columns:
                connection.execute(
                    "ALTER TABLE memory_records ADD COLUMN sensitivity TEXT NOT NULL DEFAULT 'normal'"
                )
            if "content_sha256" not in columns:
                connection.execute(
                    "ALTER TABLE memory_records ADD COLUMN content_sha256 TEXT NOT NULL DEFAULT ''"
                )
            if "content_bytes" not in columns:
                connection.execute(
                    "ALTER TABLE memory_records ADD COLUMN content_bytes INTEGER NOT NULL DEFAULT 0"
                )

            try:
                connection.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                        content,
                        provenance,
                        source,
                        tokenize='unicode61 remove_diacritics 2'
                    )
                    """
                )
                self.fts5_enabled = True
            except sqlite3.OperationalError:
                self.fts5_enabled = False

    @staticmethod
    def _validate_project_id(project_id: int) -> int:
        if isinstance(project_id, bool) or not isinstance(project_id, int) or project_id < 1:
            raise ValueError("project_id must be a positive integer")
        return project_id

    @staticmethod
    def _validate_kind(kind: str) -> str:
        normalized = str(kind or "").strip().casefold()
        if normalized not in MEMORY_KINDS:
            raise ValueError(f"unsupported memory kind: {kind}")
        return normalized

    @staticmethod
    def _validate_evidence_level(level: str) -> str:
        normalized = str(level or "").strip().casefold()
        if normalized not in EVIDENCE_LEVELS:
            raise ValueError(f"unsupported evidence level: {level}")
        return normalized

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> MemoryRecord:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        return MemoryRecord(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            kind=str(row["kind"]),
            content=str(row["content"]),
            provenance=str(row["provenance"]),
            source=str(row["source"]),
            source_hash=str(row["source_hash"]),
            observed_at=str(row["observed_at"]),
            evidence_level=str(row["evidence_level"]),
            valid_until=str(row["valid_until"]) if row["valid_until"] is not None else None,
            supersedes=int(row["supersedes"]) if row["supersedes"] is not None else None,
            status=str(row["status"]),
            sensitivity=str(row["sensitivity"] or "normal"),
            content_sha256=str(row["content_sha256"] or hashlib.sha256(str(row["content"]).encode("utf-8")).hexdigest()),
            content_bytes=int(row["content_bytes"] or len(str(row["content"]).encode("utf-8"))),
            secret_redacted=bool(row["secret_redacted"]),
            metadata=metadata,
        )

    @staticmethod
    def _source_hash(
        *,
        project_id: int,
        kind: str,
        source: str,
        content: str,
        dedupe_key: Optional[str],
    ) -> str:
        identity = dedupe_key if dedupe_key is not None else content
        payload = f"{project_id}|{kind}|{source}|{identity}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def add_record(
        self,
        *,
        project_id: int,
        kind: str,
        content: str,
        provenance: str,
        source: str,
        evidence_level: str,
        observed_at: Optional[str] = None,
        valid_until: Optional[str] = None,
        supersedes: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
        dedupe_key: Optional[str] = None,
        sensitivity: Optional[str] = None,
    ) -> MemoryRecord:
        project_id = self._validate_project_id(project_id)
        kind = self._validate_kind(kind)
        evidence_level = self._validate_evidence_level(evidence_level)
        if not isinstance(content, str) or not content.strip():
            raise ValueError("content must be a non-empty string")
        if len(content) > 50_000:
            raise ValueError("content exceeds memory limit")
        provenance = str(provenance or "").strip()
        source = str(source or "").strip()
        if not provenance or len(provenance) > 500:
            raise ValueError("invalid provenance")
        if not source or len(source) > 200:
            raise ValueError("invalid source")
        if valid_until is not None and len(str(valid_until)) > 80:
            raise ValueError("invalid valid_until")
        if supersedes is not None and (isinstance(supersedes, bool) or int(supersedes) < 1):
            raise ValueError("supersedes must be a positive record id")

        exact_content = content.strip()
        exact_provenance = provenance
        exact_source = source
        sensitivity_value = str(sensitivity or classify_sensitive_artifact(exact_content)).casefold()
        if sensitivity_value not in SENSITIVITY_LEVELS:
            raise ValueError("invalid sensitivity")
        content_bytes = len(exact_content.encode("utf-8"))
        content_sha256 = hashlib.sha256(exact_content.encode("utf-8")).hexdigest()
        timestamp = str(observed_at or _now())
        metadata_obj = dict(metadata or {})
        metadata_json = json.dumps(metadata_obj, ensure_ascii=False, sort_keys=True)
        source_hash = self._source_hash(
            project_id=project_id,
            kind=kind,
            source=exact_source,
            content=exact_content,
            dedupe_key=dedupe_key,
        )

        with self._lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM memory_records WHERE project_id = ? AND source_hash = ?",
                (project_id, source_hash),
            ).fetchone()
            if existing is not None:
                return self._record_from_row(existing)

            if supersedes is not None:
                previous = connection.execute(
                    "SELECT id FROM memory_records WHERE id = ? AND project_id = ?",
                    (int(supersedes), project_id),
                ).fetchone()
                if previous is None:
                    raise ValueError("superseded record does not belong to project")

            cursor = connection.execute(
                """
                INSERT INTO memory_records (
                    project_id, kind, content, provenance, source, source_hash,
                    observed_at, evidence_level, valid_until, supersedes, status,
                    sensitivity, content_sha256, content_bytes, secret_redacted, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    kind,
                    exact_content,
                    exact_provenance,
                    exact_source,
                    source_hash,
                    timestamp,
                    evidence_level,
                    str(valid_until) if valid_until is not None else None,
                    int(supersedes) if supersedes is not None else None,
                    sensitivity_value,
                    content_sha256,
                    content_bytes,
                    0,
                    metadata_json,
                ),
            )
            record_id = int(cursor.lastrowid)

            if supersedes is not None:
                connection.execute(
                    "UPDATE memory_records SET status = 'superseded' WHERE id = ?",
                    (int(supersedes),),
                )

            if self.fts5_enabled:
                try:
                    connection.execute(
                        "INSERT INTO memory_fts(rowid, content, provenance, source) VALUES (?, ?, ?, ?)",
                        (record_id, exact_content, exact_provenance, exact_source),
                    )
                except sqlite3.OperationalError:
                    self.fts5_enabled = False

            row = connection.execute(
                "SELECT * FROM memory_records WHERE id = ?",
                (record_id,),
            ).fetchone()
            assert row is not None
            return self._record_from_row(row)

    def get(self, record_id: int) -> Optional[MemoryRecord]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM memory_records WHERE id = ?",
                (int(record_id),),
            ).fetchone()
        return self._record_from_row(row) if row is not None else None

    def list_records(
        self,
        project_id: int,
        *,
        kinds: Optional[Iterable[str]] = None,
        status: str = "active",
        limit: int = 100,
    ) -> list[MemoryRecord]:
        project_id = self._validate_project_id(project_id)
        status = str(status or "active").casefold()
        if status not in MEMORY_STATUSES:
            raise ValueError("invalid memory status")
        normalized_kinds = tuple(self._validate_kind(kind) for kind in (kinds or ()))
        limit = max(1, min(int(limit), 500))

        clauses = ["project_id = ?", "status = ?"]
        params: list[Any] = [project_id, status]
        if normalized_kinds:
            placeholders = ",".join("?" for _ in normalized_kinds)
            clauses.append(f"kind IN ({placeholders})")
            params.extend(normalized_kinds)
        params.append(limit)

        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM memory_records
                WHERE {' AND '.join(clauses)}
                ORDER BY observed_at DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    @staticmethod
    def _fts_query(query: str) -> str:
        terms = []
        for token in _TOKEN_RE.findall(query.casefold()):
            if token in _STOP_TERMS or token in terms:
                continue
            terms.append(token)
            if len(terms) >= 12:
                break
        return " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms)

    def search(
        self,
        project_id: int,
        query: str,
        *,
        kinds: Optional[Iterable[str]] = None,
        limit: int = 8,
    ) -> list[MemoryRecord]:
        project_id = self._validate_project_id(project_id)
        normalized_kinds = tuple(self._validate_kind(kind) for kind in (kinds or ()))
        limit = max(1, min(int(limit), 50))
        fts_query = self._fts_query(str(query or ""))

        if self.fts5_enabled and fts_query:
            kind_clause = ""
            params: list[Any] = [fts_query, project_id]
            if normalized_kinds:
                placeholders = ",".join("?" for _ in normalized_kinds)
                kind_clause = f" AND r.kind IN ({placeholders})"
                params.extend(normalized_kinds)
            params.append(limit)
            try:
                with self._lock, self._connect() as connection:
                    rows = connection.execute(
                        f"""
                        SELECT r.*, bm25(memory_fts) AS rank
                        FROM memory_fts
                        JOIN memory_records AS r ON r.id = memory_fts.rowid
                        WHERE memory_fts MATCH ?
                          AND r.project_id = ?
                          AND r.status = 'active'
                          {kind_clause}
                        ORDER BY rank ASC, r.observed_at DESC, r.id DESC
                        LIMIT ?
                        """,
                        params,
                    ).fetchall()
                if rows:
                    return [self._record_from_row(row) for row in rows]
            except sqlite3.OperationalError:
                self.fts5_enabled = False

        # Deterministic fallback: recent active records with optional lexical overlap.
        candidates = self.list_records(
            project_id,
            kinds=normalized_kinds or None,
            status="active",
            limit=max(limit * 6, 24),
        )
        query_terms = {
            token for token in _TOKEN_RE.findall(str(query or "").casefold())
            if token not in _STOP_TERMS
        }
        if not query_terms:
            return candidates[:limit]

        scored: list[tuple[int, int, MemoryRecord]] = []
        total = max(1, len(candidates))
        for index, record in enumerate(candidates):
            record_terms = set(_TOKEN_RE.findall(record.content.casefold()))
            overlap = len(query_terms & record_terms)
            recency = total - index
            scored.append((overlap, recency, record))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        relevant = [record for overlap, _recency, record in scored if overlap > 0]
        return (relevant or candidates)[:limit]

    def retrieval_context(
        self,
        project_id: int,
        query: str,
        *,
        semantic_top_k: int = 5,
        episodic_top_k: int = 4,
        hypothesis_top_k: int = 3,
        max_chars: int = 4_500,
    ) -> str:
        facts = self.search(
            project_id,
            query,
            kinds=SEMANTIC_FACT_KINDS,
            limit=semantic_top_k,
        )
        hypotheses = self.search(
            project_id,
            query,
            kinds=HYPOTHESIS_KINDS,
            limit=hypothesis_top_k,
        )
        episodes = self.search(
            project_id,
            query,
            kinds=EPISODIC_KINDS,
            limit=episodic_top_k,
        )

        lines = [
            "PROJECT MEMORY PLANE",
            (
                "backend=local-sqlite; "
                f"fts5={'enabled' if self.fts5_enabled else 'fallback'}; "
                "vector_backend=not_enabled; semantic_response_cache=off"
            ),
            (
                "memory_rule=model output is never a durable fact automatically; "
                "hypotheses remain explicitly non-factual until validated"
            ),
        ]
        if facts:
            lines.append("SEMANTIC DURABLE FACTS:")
            for item in facts:
                lines.append(
                    f"- [{item.kind}|{item.evidence_level}|{item.sensitivity}|{item.provenance}] {item.content}"
                )
        if hypotheses:
            lines.append("HYPOTHESES — NOT FACTS:")
            for item in hypotheses:
                lines.append(f"- [{item.sensitivity}|{item.provenance}] {item.content}")
        if episodes:
            lines.append("EPISODIC RECENT/RELEVANT:")
            for item in reversed(episodes):
                lines.append(
                    f"- [{item.observed_at[:25]}|{item.evidence_level}|{item.sensitivity}|{item.source}] "
                    f"{item.content[:360]}"
                )
        return "\n".join(lines)[:max_chars]

    def delete_project(self, project_id: int) -> int:
        project_id = self._validate_project_id(project_id)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT id FROM memory_records WHERE project_id = ?",
                (project_id,),
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            if ids and self.fts5_enabled:
                try:
                    connection.executemany(
                        "DELETE FROM memory_fts WHERE rowid = ?",
                        [(record_id,) for record_id in ids],
                    )
                except sqlite3.OperationalError:
                    self.fts5_enabled = False
            connection.execute(
                "DELETE FROM memory_records WHERE project_id = ?",
                (project_id,),
            )
            return len(ids)

    def stats(self, project_id: Optional[int] = None) -> dict[str, Any]:
        params: tuple[Any, ...] = ()
        where = ""
        if project_id is not None:
            project_id = self._validate_project_id(project_id)
            where = " WHERE project_id = ?"
            params = (project_id,)
        with self._lock, self._connect() as connection:
            count = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM memory_records{where}",
                    params,
                ).fetchone()[0]
            )
        return {
            "records": count,
            "fts5_enabled": self.fts5_enabled,
            "semantic_response_cache_enabled": False,
            "vector_backend_enabled": False,
            "exact_sensitive_artifact_retention": True,
        }
