from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path.home() / ".luna-agent" / "projects.db"


@dataclass
class Project:
    id: int
    name: str
    path: str
    project_type: str
    description: str
    created_at: str
    updated_at: str
    last_session_at: str
    session_count: int
    color: str
    pinned: bool


@dataclass
class ProjectMessage:
    id: int
    project_id: int
    role: str
    content: str
    timestamp: str
    model: str
    is_compressed: bool
    original_count: int


class ProjectsDB:
    def __init__(self):
        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()
        except Exception as e:
            import logging
            logging.getLogger("luna.projects").error(f"ProjectsDB init error: {e}")

    @contextmanager
    def _conn(self):
        """Context-managed SQLite connection — always closes, even on exception."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        try:
            with self._conn() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS projects (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        name            TEXT NOT NULL,
                        path            TEXT NOT NULL DEFAULT '',
                        project_type    TEXT NOT NULL DEFAULT 'other',
                        description     TEXT NOT NULL DEFAULT '',
                        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                        updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
                        last_session_at TEXT NOT NULL DEFAULT (datetime('now')),
                        session_count   INTEGER NOT NULL DEFAULT 0,
                        color           TEXT NOT NULL DEFAULT 'cyan',
                        pinned          INTEGER NOT NULL DEFAULT 0
                    );

                    CREATE TABLE IF NOT EXISTS project_messages (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id      INTEGER NOT NULL,
                        role            TEXT NOT NULL,
                        content         TEXT NOT NULL,
                        timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
                        model           TEXT NOT NULL DEFAULT '',
                        is_compressed   INTEGER NOT NULL DEFAULT 0,
                        original_count  INTEGER NOT NULL DEFAULT 1,
                        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS project_facts (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id  INTEGER NOT NULL,
                        fact        TEXT NOT NULL,
                        source      TEXT NOT NULL DEFAULT 'auto',
                        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_projects_last_session_at ON projects(last_session_at);
                    CREATE INDEX IF NOT EXISTS idx_project_messages_project_id ON project_messages(project_id);
                    CREATE INDEX IF NOT EXISTS idx_project_facts_project_id ON project_facts(project_id);
                    """
                )
                conn.commit()
        except Exception as e:
            import logging
            logging.getLogger("luna.projects").error(f"_init_db error: {e}")

    def _row_to_project(self, row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "path": row["path"],
            "project_type": row["project_type"],
            "description": row["description"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_session_at": row["last_session_at"],
            "session_count": row["session_count"],
            "color": row["color"],
            "pinned": bool(row["pinned"]),  # SQLite INTEGER → Python bool
        }

    def _row_to_message(self, row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "role": row["role"],
            "content": row["content"],
            "timestamp": row["timestamp"],
            "model": row["model"],
            "is_compressed": bool(row["is_compressed"]),
            "original_count": row["original_count"],
        }

    def create_project(
        self,
        name: str,
        path: str = "",
        project_type: str = "other",
        description: str = "",
        color: str = "cyan",
    ) -> int:
        try:
            with self._conn() as conn:
                cur = conn.execute(
                    "INSERT INTO projects (name, path, project_type, description, color) VALUES (?,?,?,?,?)",
                    (name, path, project_type, description, color),
                )
                conn.commit()
                return int(cur.lastrowid or 0)
        except Exception as e:
            import logging
            logging.getLogger("luna.projects").error(f"create_project error: {e}")
            return 0

    def get_project(self, project_id: int) -> Optional[dict]:
        try:
            with self._conn() as conn:
                row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            return self._row_to_project(row) if row else None
        except Exception:
            return None

    def list_projects(self) -> list[dict]:
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM projects ORDER BY pinned DESC, last_session_at DESC"
                ).fetchall()
            return [self._row_to_project(r) for r in rows]
        except Exception:
            return []

    def update_project(self, project_id: int, **kwargs) -> bool:
        try:
            allowed = {"name", "path", "project_type", "description", "color", "pinned"}
            fields = {k: v for k, v in kwargs.items() if k in allowed}
            if not fields:
                return False
            fields["updated_at"] = datetime.now().isoformat()
            set_clause = ", ".join(f"{k}=?" for k in fields)
            with self._conn() as conn:
                cur = conn.execute(
                    f"UPDATE projects SET {set_clause} WHERE id=?",
                    [*fields.values(), project_id],
                )
                conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            import logging
            logging.getLogger("luna.projects").error(f"update_project error: {e}")
            return False

    def delete_project(self, project_id: int) -> bool:
        try:
            with self._conn() as conn:
                cur = conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
                conn.commit()
            return cur.rowcount > 0
        except Exception:
            return False

    def touch_project(self, project_id: int) -> None:
        try:
            with self._conn() as conn:
                conn.execute(
                    "UPDATE projects SET last_session_at=datetime('now'), updated_at=datetime('now'), session_count=session_count+1 WHERE id=?",
                    (project_id,),
                )
                conn.commit()
        except Exception:
            pass

    def add_message(
        self,
        project_id: int,
        role: str,
        content: str,
        model: str = "",
        is_compressed: bool = False,
        original_count: int = 1,
    ) -> int:
        try:
            with self._conn() as conn:
                cur = conn.execute(
                    """INSERT INTO project_messages
                       (project_id, role, content, model, is_compressed, original_count)
                       VALUES (?,?,?,?,?,?)""",
                    (project_id, role, content, model, int(is_compressed), original_count),
                )
                conn.commit()
                return int(cur.lastrowid or 0)
        except Exception as e:
            import logging
            logging.getLogger("luna.projects").error(f"add_message error: {e}")
            return 0

    def get_messages(self, project_id: int, limit: int = 100) -> list[dict]:
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    """SELECT * FROM project_messages WHERE project_id=?
                       ORDER BY id DESC LIMIT ?""",
                    (project_id, limit),
                ).fetchall()
            return list(reversed([self._row_to_message(r) for r in rows]))
        except Exception:
            return []

    def count_messages(self, project_id: int) -> int:
        try:
            with self._conn() as conn:
                n = conn.execute(
                    "SELECT COUNT(*) FROM project_messages WHERE project_id=? AND is_compressed=0",
                    (project_id,),
                ).fetchone()[0]
            return n
        except Exception:
            return 0

    def compress_messages(self, project_id: int, keep_recent: int = 10) -> int:
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    """SELECT id, role, content FROM project_messages
                       WHERE project_id=? AND is_compressed=0
                       ORDER BY id ASC""",
                    (project_id,),
                ).fetchall()
                if len(rows) <= keep_recent:
                    return 0
                to_compress = rows[:-keep_recent]
                ids_to_delete = [r["id"] for r in to_compress]
                summary_parts = []
                for r in to_compress:
                    # Use generic role labels — never hardcode user names
                    prefix = "Usuário" if r["role"] == "user" else "Luna" if r["role"] == "luna" else "Sistema"
                    content_preview = r["content"][:200].replace("\n", " ")
                    summary_parts.append(f"{prefix}: {content_preview}")
                summary = (
                    f"[CONTEXTO COMPRIMIDO — {len(to_compress)} mensagens anteriores]\n"
                    + "\n".join(summary_parts[:30])
                )
                conn.execute(
                    """INSERT INTO project_messages
                       (project_id, role, content, is_compressed, original_count)
                       VALUES (?, 'system', ?, 1, ?)""",
                    (project_id, summary, len(to_compress)),
                )
                conn.execute(
                    f"DELETE FROM project_messages WHERE id IN ({','.join('?' * len(ids_to_delete))})",
                    ids_to_delete,
                )
                conn.commit()
            return len(to_compress)
        except Exception as e:
            import logging
            logging.getLogger("luna.projects").error(f"compress_messages error: {e}")
            return 0

    def add_fact(self, project_id: int, fact: str, source: str = "auto") -> int:
        try:
            with self._conn() as conn:
                existing = conn.execute(
                    "SELECT id FROM project_facts WHERE project_id=? AND fact=?",
                    (project_id, fact),
                ).fetchone()
                if existing:
                    return int(existing["id"])
                cur = conn.execute(
                    "INSERT INTO project_facts (project_id, fact, source) VALUES (?,?,?)",
                    (project_id, fact, source),
                )
                conn.commit()
                return int(cur.lastrowid or 0)
        except Exception:
            return 0

    def get_facts(self, project_id: int, limit: int = 15) -> list[str]:
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT fact FROM project_facts WHERE project_id=? ORDER BY id DESC LIMIT ?",
                    (project_id, limit),
                ).fetchall()
            return [r["fact"] for r in rows]
        except Exception:
            return []

    def format_context_for_prompt(self, project_id: int) -> str:
        try:
            project = self.get_project(project_id)
            if not project:
                return ""
            facts = self.get_facts(project_id)
            msgs = self.get_messages(project_id, limit=20)
            parts = [
                f"## Projeto ativo: {project['name']}",
                f"Tipo: {project['project_type']} | Pasta: {project['path'] or 'não definida'}",
            ]
            if project["description"]:
                parts.append(f"Descrição: {project['description']}")
            if facts:
                parts.append("\n### Fatos conhecidos sobre este projeto:")
                parts.extend(f"- {f}" for f in facts)
            if msgs:
                parts.append(f"\n### Últimas {len(msgs)} mensagens deste projeto:")
                for m in msgs[-10:]:
                    role = "Usuário" if m["role"] == "user" else "Luna" if m["role"] == "luna" else "Sistema"
                    content_preview = m["content"][:300].replace("\n", " ")
                    if m["is_compressed"]:
                        parts.append(f"[Contexto anterior comprimido: {m['original_count']} msgs]")
                    else:
                        parts.append(f"{role}: {content_preview}")
            return "\n".join(parts)
        except Exception:
            return ""
