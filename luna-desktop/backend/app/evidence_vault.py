"""Immutable local evidence vault for report-grade artifacts.

The vault stores exact bytes content-addressed by SHA-256 and keeps project-scoped
metadata in SQLite. Logs, protocol transcripts, debugger output, PCAPs and screenshots
can therefore be referenced later without asking the LLM to reconstruct evidence.

Sensitive/credential/classified artifacts are preserved exactly by design. Sanitized
exports are a separate presentation concern.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SENSITIVITY_LEVELS = frozenset({"normal", "sensitive", "credential", "classified"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class EvidenceVaultRecord:
    id: int
    project_id: int
    kind: str
    media_type: str
    source: str
    original_name: str
    description: str
    sha256: str
    byte_length: int
    observed_at: str
    sensitivity: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvidenceVault:
    def __init__(
        self,
        root: str | Path,
        *,
        max_artifact_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.blob_root = self.root / "blobs"
        self.db_path = self.root / "evidence.sqlite3"
        self.max_artifact_bytes = max(1024, int(max_artifact_bytes))
        self.root.mkdir(parents=True, exist_ok=True)
        self.blob_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS evidence_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    original_name TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    sha256 TEXT NOT NULL,
                    byte_length INTEGER NOT NULL,
                    observed_at TEXT NOT NULL,
                    sensitivity TEXT NOT NULL DEFAULT 'normal'
                );

                CREATE INDEX IF NOT EXISTS idx_evidence_project
                    ON evidence_records(project_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_evidence_sha
                    ON evidence_records(sha256);
                """
            )

    @staticmethod
    def _project_id(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("project_id must be a positive integer")
        return value

    @staticmethod
    def _bounded_text(value: str, field: str, limit: int, *, required: bool = True) -> str:
        text = str(value or "").strip()
        if required and not text:
            raise ValueError(f"{field} is required")
        if "\x00" in text or len(text) > limit:
            raise ValueError(f"invalid {field}")
        return text

    def _blob_path(self, sha256: str) -> Path:
        return self.blob_root / sha256[:2] / f"{sha256}.blob"

    @staticmethod
    def _from_row(row: sqlite3.Row) -> EvidenceVaultRecord:
        return EvidenceVaultRecord(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            kind=str(row["kind"]),
            media_type=str(row["media_type"]),
            source=str(row["source"]),
            original_name=str(row["original_name"]),
            description=str(row["description"]),
            sha256=str(row["sha256"]),
            byte_length=int(row["byte_length"]),
            observed_at=str(row["observed_at"]),
            sensitivity=str(row["sensitivity"]),
        )

    def _write_blob_once(self, path: Path, raw: bytes) -> None:
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.replace(temp_name, path)
            except FileExistsError:
                os.unlink(temp_name)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise

    def store(
        self,
        *,
        project_id: int,
        data: bytes,
        kind: str,
        media_type: str,
        source: str,
        original_name: str = "",
        description: str = "",
        observed_at: str | None = None,
        sensitivity: str = "normal",
    ) -> EvidenceVaultRecord:
        project_id = self._project_id(project_id)
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("evidence data must be bytes")
        raw = bytes(data)
        if not raw:
            raise ValueError("evidence data must not be empty")
        if len(raw) > self.max_artifact_bytes:
            raise ValueError("evidence artifact exceeds configured byte limit")

        kind = self._bounded_text(kind, "kind", 80)
        media_type = self._bounded_text(media_type, "media_type", 120)
        source = self._bounded_text(source, "source", 300)
        original_name = self._bounded_text(
            original_name, "original_name", 255, required=False
        )
        description = self._bounded_text(
            description, "description", 2000, required=False
        )
        sensitivity = str(sensitivity or "normal").casefold().strip()
        if sensitivity not in SENSITIVITY_LEVELS:
            raise ValueError("invalid sensitivity")

        digest = hashlib.sha256(raw).hexdigest()
        blob_path = self._blob_path(digest)
        timestamp = str(observed_at or _now())

        with self._lock:
            self._write_blob_once(blob_path, raw)
            with self._connection() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO evidence_records (
                        project_id, kind, media_type, source, original_name,
                        description, sha256, byte_length, observed_at, sensitivity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        kind,
                        media_type,
                        source,
                        original_name,
                        description,
                        digest,
                        len(raw),
                        timestamp,
                        sensitivity,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM evidence_records WHERE id = ?",
                    (int(cursor.lastrowid),),
                ).fetchone()
        assert row is not None
        return self._from_row(row)

    def get(self, record_id: int, *, project_id: int | None = None) -> EvidenceVaultRecord | None:
        clauses = ["id = ?"]
        params: list[Any] = [int(record_id)]
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(self._project_id(project_id))
        with self._lock, self._connection() as connection:
            row = connection.execute(
                f"SELECT * FROM evidence_records WHERE {' AND '.join(clauses)}",
                params,
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def list_project(self, project_id: int, *, limit: int = 200) -> list[EvidenceVaultRecord]:
        project_id = self._project_id(project_id)
        limit = max(1, min(int(limit), 1000))
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM evidence_records
                WHERE project_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def read_bytes(self, record_id: int, *, project_id: int | None = None) -> bytes:
        record = self.get(record_id, project_id=project_id)
        if record is None:
            raise FileNotFoundError("evidence record not found")
        path = self._blob_path(record.sha256)
        raw = path.read_bytes()
        if len(raw) != record.byte_length:
            raise IOError("evidence byte length mismatch")
        if hashlib.sha256(raw).hexdigest() != record.sha256:
            raise IOError("evidence SHA-256 mismatch")
        return raw

    def verify(self, record_id: int, *, project_id: int | None = None) -> bool:
        try:
            self.read_bytes(record_id, project_id=project_id)
            return True
        except (FileNotFoundError, IOError, OSError):
            return False

    def delete_project(self, project_id: int) -> int:
        project_id = self._project_id(project_id)
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT sha256 FROM evidence_records WHERE project_id = ?",
                (project_id,),
            ).fetchall()
            digests = [str(row["sha256"]) for row in rows]
            cursor = connection.execute(
                "DELETE FROM evidence_records WHERE project_id = ?",
                (project_id,),
            )
            deleted = max(0, int(cursor.rowcount))

            orphaned: list[str] = []
            for digest in set(digests):
                remaining = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM evidence_records WHERE sha256 = ?",
                        (digest,),
                    ).fetchone()[0]
                )
                if remaining == 0:
                    orphaned.append(digest)

        for digest in orphaned:
            path = self._blob_path(digest)
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            try:
                path.parent.rmdir()
            except OSError:
                pass
        return deleted

    def stats(self, project_id: int | None = None) -> dict[str, int]:
        where = ""
        params: tuple[Any, ...] = ()
        if project_id is not None:
            where = " WHERE project_id = ?"
            params = (self._project_id(project_id),)
        with self._lock, self._connection() as connection:
            count, total_bytes = connection.execute(
                f"""
                SELECT COUNT(*), COALESCE(SUM(byte_length), 0)
                FROM evidence_records{where}
                """,
                params,
            ).fetchone()
        return {
            "records": int(count),
            "referenced_bytes": int(total_bytes),
        }
