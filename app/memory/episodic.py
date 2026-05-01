from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_load_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item).strip()]
    except Exception:
        return []
    return []


def _ago_text(timestamp: str) -> str:
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt
        seconds = max(int(delta.total_seconds()), 0)
        if seconds < 60:
            return "há poucos segundos"
        if seconds < 3600:
            minutes = seconds // 60
            return f"há {minutes} minuto{'s' if minutes != 1 else ''}"
        if seconds < 86400:
            hours = seconds // 3600
            return f"há {hours} hora{'s' if hours != 1 else ''}"
        days = seconds // 86400
        return f"há {days} dia{'s' if days != 1 else ''}"
    except Exception:
        return "há algum tempo"


class EpisodicMemory:
    def __init__(self, db_path: str = None):
        try:
            self.db_path = Path(db_path) if db_path else Path.home() / ".luna-agent" / "episodic.db"
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.init_db()
        except Exception:
            self.db_path = Path.home() / ".luna-agent" / "episodic.db"

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT,
                        workspace_path TEXT,
                        task_type TEXT,
                        summary TEXT,
                        outcome TEXT,
                        tools_used TEXT,
                        timestamp TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS key_facts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT,
                        workspace_path TEXT,
                        fact TEXT,
                        timestamp TEXT
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_workspace ON sessions(workspace_path)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_task_type ON sessions(task_type)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_workspace ON key_facts(workspace_path)")
                conn.commit()
        except Exception:
            pass

    def record_session(
        self,
        session_id: str,
        workspace_path: str,
        task_type: str,
        summary: str,
        tools_used: list[str],
        outcome: str,
        key_facts: list[str],
        timestamp: str = None,
    ) -> int:
        try:
            ts = timestamp or _utc_now_iso()
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO sessions (
                        session_id, workspace_path, task_type, summary, outcome, tools_used, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        workspace_path or "",
                        task_type or "general",
                        (summary or "")[:2000],
                        outcome or "partial",
                        json.dumps(list(tools_used or []), ensure_ascii=False),
                        ts,
                    ),
                )
                for fact in key_facts or []:
                    fact_text = str(fact).strip()
                    if not fact_text:
                        continue
                    conn.execute(
                        """
                        INSERT INTO key_facts (session_id, workspace_path, fact, timestamp)
                        VALUES (?, ?, ?, ?)
                        """,
                        (session_id, workspace_path or "", fact_text[:1000], ts),
                    )
                conn.commit()
                return int(cursor.lastrowid or 0)
        except Exception:
            return 0

    def recall(
        self,
        workspace_path: str = None,
        task_type: str = None,
        limit: int = 5,
    ) -> list[dict]:
        try:
            query = "SELECT session_id, summary, outcome, tools_used, timestamp FROM sessions WHERE 1=1"
            params: list[str | int] = []
            if workspace_path:
                query += " AND workspace_path = ?"
                params.append(workspace_path)
            if task_type:
                query += " AND task_type = ?"
                params.append(task_type)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            with self._connect() as conn:
                rows = conn.execute(query, params).fetchall()

            results: list[dict] = []
            for row in rows:
                key_facts = self._load_session_facts(row["session_id"], workspace_path or "")
                results.append(
                    {
                        "session_id": row["session_id"],
                        "summary": row["summary"],
                        "outcome": row["outcome"],
                        "key_facts": key_facts,
                        "tools_used": _safe_load_json_list(row["tools_used"]),
                        "timestamp": row["timestamp"],
                        "ago": _ago_text(row["timestamp"]),
                    }
                )
            return results
        except Exception:
            return []

    def _load_session_facts(self, session_id: str, workspace_path: str) -> list[str]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT fact FROM key_facts
                    WHERE session_id = ? AND workspace_path = ?
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 10
                    """,
                    (session_id, workspace_path),
                ).fetchall()
            return [str(row["fact"]) for row in rows]
        except Exception:
            return []

    def recall_key_facts(self, workspace_path: str, limit: int = 10) -> list[str]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT fact FROM key_facts
                    WHERE workspace_path = ?
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 100
                    """,
                    (workspace_path,),
                ).fetchall()
            unique: list[str] = []
            seen: set[str] = set()
            for row in rows:
                fact = str(row["fact"]).strip()
                key = fact.lower()
                if not fact or key in seen:
                    continue
                seen.add(key)
                unique.append(fact)
                if len(unique) >= limit:
                    break
            return unique
        except Exception:
            return []

    def format_for_prompt(
        self,
        workspace_path: str = None,
        task_type: str = None,
        limit: int = 3,
    ) -> str:
        try:
            sessions = self.recall(workspace_path=workspace_path, task_type=task_type, limit=limit)
            if not sessions:
                return ""
            lines = ["## Memória das últimas sessões"]
            for item in sessions:
                lines.append(f"### Sessão de {item['ago']}")
                lines.append(f"- Resumo: {item['summary']}")
                lines.append(f"- Resultado: {item['outcome']}")
                if item["tools_used"]:
                    lines.append(f"- Ferramentas: {', '.join(item['tools_used'][:8])}")
                if item["key_facts"]:
                    for fact in item["key_facts"][:4]:
                        lines.append(f"- Fato: {fact}")
            facts = self.recall_key_facts(workspace_path or "", limit=6) if workspace_path else []
            if facts:
                lines.append("## Fatos importantes recorrentes")
                for fact in facts:
                    lines.append(f"- {fact}")
            return "\n".join(lines)
        except Exception:
            return ""