"""Armazenamento local, atômico e sem banco externo para a tela Projects."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any

from .evidence_vault import EvidenceVault
from .memory_plane import MemoryPlane


DEFAULT_PROJECTS_DIR = Path(r"D:\LunaCyber\projects")
PROJECT_TYPES = frozenset({"app", "bounty", "solana", "script", "research", "other"})
PROJECT_COLORS = frozenset({"cyan", "purple", "green", "orange", "red"})
MESSAGE_ROLES = frozenset({"user", "luna", "system"})
_SAFE_NAME = re.compile(r"^[^\x00-\x1f<>:\"/\\|?*]{1,100}$")
_TERM_RE = re.compile(r"(?u)\b[\w./:+-]{3,}\b")
_TERM_STOP = frozenset({
    "para", "com", "sem", "uma", "uns", "das", "dos", "que", "the", "and",
    "this", "that", "from", "como", "qual", "quais", "onde", "quando", "sobre",
})


def _terms(value: str) -> set[str]:
    return {
        item.casefold()
        for item in _TERM_RE.findall(value or "")
        if item.casefold() not in _TERM_STOP
    }


def _relevance(value: str, query_terms: set[str]) -> float:
    if not query_terms:
        return 0.0
    value_terms = _terms(value)
    if not value_terms:
        return 0.0
    overlap = len(value_terms & query_terms)
    return overlap / max(1, len(query_terms))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ProjectValidationError(ValueError):
    """Entrada inválida recebida pela API local."""


class ProjectNotFoundError(LookupError):
    """Projeto local inexistente."""


class ProjectStore:
    def __init__(self, root: str | Path | None = None) -> None:
        configured = root or os.getenv("LUNA_PROJECTS_DIR") or DEFAULT_PROJECTS_DIR
        self.root = Path(configured).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._index = self.root / "index.json"
        self._lock = threading.RLock()
        self.memory_plane = MemoryPlane(self.root / ".memory" / "memory.sqlite3")
        self.evidence_vault = EvidenceVault(self.root / ".evidence")
        if not self._index.exists():
            self._write_json(self._index, {"version": 1, "projects": []})

    @staticmethod
    def _validate_name(value: Any) -> str:
        if not isinstance(value, str):
            raise ProjectValidationError("name deve ser string")
        name = value.strip()
        if not _SAFE_NAME.fullmatch(name) or name in {".", ".."}:
            raise ProjectValidationError("name contém caracteres inválidos")
        return name

    @staticmethod
    def _validate_workspace_path(value: Any) -> str:
        if value in {None, ""}:
            return ""
        if not isinstance(value, str) or len(value) > 1024 or "\x00" in value:
            raise ProjectValidationError("path inválido")
        candidate = value.strip()
        parts = PureWindowsPath(candidate).parts if ":" in candidate or "\\" in candidate else Path(candidate).parts
        if ".." in parts:
            raise ProjectValidationError("path traversal não é permitido")
        if not (Path(candidate).is_absolute() or PureWindowsPath(candidate).is_absolute()):
            raise ProjectValidationError("path deve ser absoluto")
        return candidate

    @staticmethod
    def _validate_text(value: Any, field: str, max_length: int, required: bool = False) -> str:
        if value is None and not required:
            return ""
        if not isinstance(value, str):
            raise ProjectValidationError(f"{field} deve ser string")
        text = value.strip()
        if required and not text:
            raise ProjectValidationError(f"{field} é obrigatório")
        if len(text) > max_length or "\x00" in text:
            raise ProjectValidationError(f"{field} excede o limite permitido")
        return text

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _data_dir(self, project_id: int) -> Path:
        if isinstance(project_id, bool) or not isinstance(project_id, int) or project_id < 1:
            raise ProjectValidationError("project_id inválido")
        target = (self.root / str(project_id)).resolve()
        if target.parent != self.root:
            raise ProjectValidationError("project_id fora do diretório permitido")
        return target

    def _load_index(self) -> dict[str, Any]:
        data = self._read_json(self._index, {"version": 1, "projects": []})
        if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
            raise RuntimeError("index.json de Projects está corrompido")
        return data

    def _find(self, data: dict[str, Any], project_id: int) -> dict[str, Any]:
        self._data_dir(project_id)
        project = next((item for item in data["projects"] if item.get("id") == project_id), None)
        if project is None:
            raise ProjectNotFoundError(f"Projeto {project_id} não encontrado")
        return project

    def list_projects(self) -> list[dict[str, Any]]:
        with self._lock:
            projects = list(self._load_index()["projects"])
        return sorted(projects, key=lambda item: (not bool(item.get("pinned")), item.get("name", "").casefold()))

    def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = self._validate_name(payload.get("name"))
        workspace_path = self._validate_workspace_path(payload.get("path", ""))
        project_type = payload.get("project_type", "other")
        color = payload.get("color", "cyan")
        if project_type not in PROJECT_TYPES:
            raise ProjectValidationError("project_type inválido")
        if color not in PROJECT_COLORS:
            raise ProjectValidationError("color inválida")
        description = self._validate_text(payload.get("description", ""), "description", 2_000)

        with self._lock:
            data = self._load_index()
            if any(item.get("name", "").casefold() == name.casefold() for item in data["projects"]):
                raise ProjectValidationError("já existe um projeto com esse nome")
            project_id = max((int(item.get("id", 0)) for item in data["projects"]), default=0) + 1
            timestamp = _now()
            project = {
                "id": project_id,
                "name": name,
                "path": workspace_path,
                "project_type": project_type,
                "description": description,
                "created_at": timestamp,
                "updated_at": timestamp,
                "last_session_at": timestamp,
                "session_count": 0,
                "color": color,
                "pinned": False,
            }
            self._data_dir(project_id).mkdir(parents=True, exist_ok=False)
            self._write_json(self._data_dir(project_id) / "messages.json", [])
            self._write_json(self._data_dir(project_id) / "facts.json", [])
            data["projects"].append(project)
            self._write_json(self._index, data)
            return dict(project)

    def update_project(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {"name", "path", "project_type", "description", "color", "pinned"}
        unknown = set(payload) - allowed
        if unknown:
            raise ProjectValidationError(f"campos não permitidos: {', '.join(sorted(unknown))}")
        with self._lock:
            data = self._load_index()
            project = self._find(data, project_id)
            if "name" in payload:
                name = self._validate_name(payload["name"])
                if any(item["id"] != project_id and item.get("name", "").casefold() == name.casefold() for item in data["projects"]):
                    raise ProjectValidationError("já existe um projeto com esse nome")
                project["name"] = name
            if "path" in payload:
                project["path"] = self._validate_workspace_path(payload["path"])
            if "project_type" in payload:
                if payload["project_type"] not in PROJECT_TYPES:
                    raise ProjectValidationError("project_type inválido")
                project["project_type"] = payload["project_type"]
            if "description" in payload:
                project["description"] = self._validate_text(payload["description"], "description", 2_000)
            if "color" in payload:
                if payload["color"] not in PROJECT_COLORS:
                    raise ProjectValidationError("color inválida")
                project["color"] = payload["color"]
            if "pinned" in payload:
                if not isinstance(payload["pinned"], bool):
                    raise ProjectValidationError("pinned deve ser boolean")
                project["pinned"] = payload["pinned"]
            project["updated_at"] = _now()
            self._write_json(self._index, data)
            return dict(project)

    def delete_project(self, project_id: int) -> None:
        with self._lock:
            data = self._load_index()
            self._find(data, project_id)
            data["projects"] = [item for item in data["projects"] if item.get("id") != project_id]
            self._write_json(self._index, data)
            target = self._data_dir(project_id)
            if target.exists():
                shutil.rmtree(target)
            self.memory_plane.delete_project(project_id)
            self.evidence_vault.delete_project(project_id)

    def add_evidence_artifact(
        self,
        project_id: int,
        *,
        data: bytes,
        kind: str,
        media_type: str,
        source: str,
        original_name: str = "",
        description: str = "",
        sensitivity: str = "normal",
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            data_index = self._load_index()
            self._find(data_index, project_id)
        record = self.evidence_vault.store(
            project_id=project_id,
            data=data,
            kind=kind,
            media_type=media_type,
            source=source,
            original_name=original_name,
            description=description,
            sensitivity=sensitivity,
            observed_at=observed_at,
        )
        return record.to_dict()

    def list_evidence_artifacts(
        self,
        project_id: int,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._lock:
            data_index = self._load_index()
            self._find(data_index, project_id)
        return [
            item.to_dict()
            for item in self.evidence_vault.list_project(project_id, limit=limit)
        ]

    def get_evidence_artifact_metadata(
        self,
        project_id: int,
        record_id: int,
    ) -> dict[str, Any]:
        with self._lock:
            data_index = self._load_index()
            self._find(data_index, project_id)
        record = self.evidence_vault.get(record_id, project_id=project_id)
        if record is None:
            raise ProjectNotFoundError(
                f"Evidência {record_id} não encontrada no projeto {project_id}"
            )
        return record.to_dict()

    def read_evidence_artifact(self, project_id: int, record_id: int) -> tuple[dict[str, Any], bytes]:
        with self._lock:
            data_index = self._load_index()
            self._find(data_index, project_id)
        record = self.evidence_vault.get(record_id, project_id=project_id)
        if record is None:
            raise ProjectNotFoundError(
                f"Evidência {record_id} não encontrada no projeto {project_id}"
            )
        raw = self.evidence_vault.read_bytes(record_id, project_id=project_id)
        return record.to_dict(), raw

    def verify_evidence_artifact(self, project_id: int, record_id: int) -> bool:
        with self._lock:
            data_index = self._load_index()
            self._find(data_index, project_id)
        return self.evidence_vault.verify(record_id, project_id=project_id)

    def list_messages(self, project_id: int) -> list[dict[str, Any]]:
        with self._lock:
            data = self._load_index()
            self._find(data, project_id)
            messages = self._read_json(self._data_dir(project_id) / "messages.json", [])
            if not isinstance(messages, list):
                raise RuntimeError("messages.json está corrompido")
            return messages

    def add_message(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        role = payload.get("role")
        if role not in MESSAGE_ROLES:
            raise ProjectValidationError("role inválido")
        content = self._validate_text(payload.get("content"), "content", 50_000, required=True)
        model = self._validate_text(payload.get("model", ""), "model", 100)
        with self._lock:
            data = self._load_index()
            project = self._find(data, project_id)
            path = self._data_dir(project_id) / "messages.json"
            messages = self._read_json(path, [])
            message_id = max((int(item.get("id", 0)) for item in messages), default=0) + 1
            message = {
                "id": message_id,
                "project_id": project_id,
                "role": role,
                "content": content,
                "timestamp": _now(),
                "model": model,
                "is_compressed": False,
                "original_count": 1,
            }
            messages.append(message)
            self._write_json(path, messages)
            project["updated_at"] = message["timestamp"]
            project["last_session_at"] = message["timestamp"]
            if project.get("session_count", 0) == 0:
                project["session_count"] = 1
            self._write_json(self._index, data)
            self.memory_plane.add_record(
                project_id=project_id,
                kind="episode",
                content=content,
                provenance="project_store:messages.json",
                source=f"conversation:{role}",
                evidence_level="model_output" if role == "luna" else "episode",
                observed_at=message["timestamp"],
                metadata={"role": role, "model": model},
                dedupe_key=f"message:{message_id}:{message['timestamp']}",
            )
            return message

    def list_facts(self, project_id: int) -> list[str]:
        with self._lock:
            data = self._load_index()
            self._find(data, project_id)
            facts = self._read_json(self._data_dir(project_id) / "facts.json", [])
            if not isinstance(facts, list) or not all(isinstance(fact, str) for fact in facts):
                raise RuntimeError("facts.json está corrompido")
            return facts

    def add_fact(self, project_id: int, value: Any) -> list[str]:
        fact = self._validate_text(value, "fact", 1_000, required=True)
        with self._lock:
            facts = self.list_facts(project_id)
            if fact.casefold() not in {existing.casefold() for existing in facts}:
                if len(facts) >= 200:
                    raise ProjectValidationError("limite de 200 fatos atingido")
                facts.append(fact)
                self._write_json(self._data_dir(project_id) / "facts.json", facts)
            self.memory_plane.add_record(
                project_id=project_id,
                kind="operator_fact",
                content=fact,
                provenance="project_store:facts.json",
                source="project_fact",
                evidence_level="declared",
                dedupe_key=f"fact:{fact.casefold()}",
            )
            return facts

    def _sync_legacy_memory(
        self,
        project_id: int,
        *,
        facts: list[str],
        messages: list[dict[str, Any]],
    ) -> None:
        """Lazily migrate legacy JSON into typed memory without changing API contracts."""
        # Legacy JSON remains exact evidence. Migration only dual-writes into SQLite;
        # it never rewrites credentials, cookies, tokens or classified artifacts.

        for fact in facts:
            self.memory_plane.add_record(
                project_id=project_id,
                kind="operator_fact",
                content=fact,
                provenance="project_store:facts.json",
                source="project_fact",
                evidence_level="declared",
                dedupe_key=f"fact:{fact.casefold()}",
            )

        for item in messages[-64:]:
            if item.get("is_compressed"):
                continue
            role = str(item.get("role", "system"))
            if role not in MESSAGE_ROLES:
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            timestamp = str(item.get("timestamp", "")) or _now()
            message_id = int(item.get("id", 0) or 0)
            self.memory_plane.add_record(
                project_id=project_id,
                kind="episode",
                content=content,
                provenance="project_store:messages.json",
                source=f"conversation:{role}",
                evidence_level="model_output" if role == "luna" else "episode",
                observed_at=timestamp,
                metadata={"role": role, "model": str(item.get("model", ""))},
                dedupe_key=f"message:{message_id}:{timestamp}",
            )

    def retrieval_context(
        self,
        project_id: int,
        query: str,
        *,
        semantic_top_k: int = 5,
        episodic_top_k: int = 4,
    ) -> str:
        """Query-focused typed local memory with provenance and fact/hypothesis separation."""
        query = self._validate_text(query, "query", 20_000, required=True)
        semantic_top_k = max(1, min(int(semantic_top_k), 12))
        episodic_top_k = max(1, min(int(episodic_top_k), 12))

        with self._lock:
            data = self._load_index()
            project = dict(self._find(data, project_id))
            facts = list(self.list_facts(project_id))
            messages = list(self.list_messages(project_id))
            self._sync_legacy_memory(
                project_id,
                facts=facts,
                messages=messages,
            )

        memory_context = self.memory_plane.retrieval_context(
            project_id,
            query,
            semantic_top_k=semantic_top_k,
            episodic_top_k=episodic_top_k,
        )
        prefix = (
            f"PROJECT MEMORY: {project.get('name', '')}\n"
            f"type={project.get('project_type', 'other')}\n"
        )
        return (prefix + memory_context)[:4_500]

    def context(self, project_id: int) -> str:
        with self._lock:
            data = self._load_index()
            project = self._find(data, project_id)
            facts = self.list_facts(project_id)
            messages = self.list_messages(project_id)
        lines = [f"Projeto: {project['name']}", f"Tipo: {project['project_type']}"]
        if project.get("path"):
            lines.append(f"Workspace: {project['path']}")
        if project.get("description"):
            lines.append(f"Descrição: {project['description']}")
        if facts:
            lines.extend(["", "Fatos conhecidos:", *[f"- {fact}" for fact in facts]])
        recent = [message for message in messages if not message.get("is_compressed")][-8:]
        if recent:
            lines.extend(["", "Atividade recente:"])
            for message in recent:
                content = str(message.get("content", "")).replace("\n", " ")[:240]
                lines.append(f"- {message.get('role', 'system')}: {content}")
        return "\n".join(lines)

    def compress(self, project_id: int) -> dict[str, int]:
        with self._lock:
            messages = self.list_messages(project_id)
            if len(messages) <= 20:
                return {"before": len(messages), "after": len(messages), "compressed": 0}
            older, recent = messages[:-10], messages[-10:]
            summaries = []
            for message in older:
                content = str(message.get("content", "")).replace("\n", " ")[:300]
                summaries.append(f"{message.get('role', 'system')}: {content}")
            compressed = {
                "id": max((int(item.get("id", 0)) for item in messages), default=0) + 1,
                "project_id": project_id,
                "role": "system",
                "content": "Resumo local de mensagens anteriores:\n" + "\n".join(summaries)[:12_000],
                "timestamp": _now(),
                "model": "local-summary",
                "is_compressed": True,
                "original_count": len(older),
            }
            result = [compressed, *recent]
            self._write_json(self._data_dir(project_id) / "messages.json", result)
            return {"before": len(messages), "after": len(result), "compressed": len(older)}
