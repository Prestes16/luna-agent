"""
worker_store.py — Luna Agent Worker Store
Gerencia o estado dos Workers e suas tasks no Brain (VPS).

Estados de task:
  pending          → task criada, aguardando dispatch para um worker
  dispatched       → task enviada para o worker executar
  awaiting_approval → worker reportou que precisa de aprovação humana
  approved         → admin aprovou; task volta para dispatch (re-execução)
  denied           → admin negou; task encerrada
  completed        → worker completou com sucesso
  failed           → worker falhou

A store é in-memory com persistência em JSON para o audit log.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

# ─── Tipos ───────────────────────────────────────────────────────────────────

WorkerTaskStatus = Literal[
    "pending",
    "dispatched",
    "awaiting_approval",
    "approved",
    "denied",
    "completed",
    "failed",
]

# ─── Modelos ──────────────────────────────────────────────────────────────────

class WorkerInfo(BaseModel):
    worker_id: str
    registered_at: str
    last_heartbeat: str
    capabilities: list[str] = Field(default_factory=list)
    platform: str = ""
    version: str = ""


class WorkerTask(BaseModel):
    task_id: str
    session_id: str = ""
    action_id: str = ""
    tool: str
    args: dict = Field(default_factory=dict)
    risk: str = "low"
    reason: str = ""

    # worker que pegou a task
    worker_id: str = ""

    # ciclo de vida
    status: WorkerTaskStatus = "pending"
    requires_approval: bool = False

    # aprovação
    approval_status: Optional[str] = None   # "approved" | "denied"
    approved_by: str = ""
    approved_at: Optional[str] = None
    denied_at: Optional[str] = None
    deny_reason: str = ""

    # timestamps
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    dispatched_at: Optional[str] = None
    completed_at: Optional[str] = None

    # resultado
    result: dict = Field(default_factory=dict)
    error: str = ""
    result_ok: Optional[bool] = None


class WorkerApprovalRequest(BaseModel):
    """Payload enviado pelo Worker quando precisa de aprovação."""
    task_id: str
    action_id: str = ""
    tool: str
    args: dict = Field(default_factory=dict)
    risk: str = "medium"
    reason: str = ""
    worker_id: str = ""
    session_id: str = ""


class WorkerApprovalDecision(BaseModel):
    """Payload enviado pela UI para aprovar/negar uma task."""
    approved: bool
    deny_reason: str = ""
    approved_by: str = "admin"


# ─── Store ────────────────────────────────────────────────────────────────────

_LOCK = threading.Lock()

# workers registrados: {worker_id: WorkerInfo}
_workers: dict[str, WorkerInfo] = {}

# tasks por task_id: {task_id: WorkerTask}
_tasks: dict[str, WorkerTask] = {}

# persistência de audit de worker
_WORKER_AUDIT_FILE = Path("workspaces/luna-agent/worker_audit.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Workers ──────────────────────────────────────────────────────────────────

def register_worker(
    worker_id: str,
    capabilities: list[str],
    platform: str = "",
    version: str = "",
) -> WorkerInfo:
    with _LOCK:
        info = WorkerInfo(
            worker_id=worker_id,
            registered_at=_now(),
            last_heartbeat=_now(),
            capabilities=capabilities,
            platform=platform,
            version=version,
        )
        _workers[worker_id] = info
        return info


def worker_heartbeat(worker_id: str) -> Optional[WorkerInfo]:
    with _LOCK:
        if worker_id not in _workers:
            return None
        _workers[worker_id].last_heartbeat = _now()
        return _workers[worker_id]


def get_workers() -> list[WorkerInfo]:
    with _LOCK:
        return list(_workers.values())


def get_worker(worker_id: str) -> Optional[WorkerInfo]:
    with _LOCK:
        return _workers.get(worker_id)


# ─── Tasks ────────────────────────────────────────────────────────────────────

def create_task(
    tool: str,
    args: dict,
    risk: str = "low",
    reason: str = "",
    session_id: str = "",
    action_id: str = "",
    requires_approval: bool = False,
) -> WorkerTask:
    task = WorkerTask(
        task_id=f"wtask-{uuid4().hex[:10]}",
        session_id=session_id,
        action_id=action_id,
        tool=tool,
        args=args,
        risk=risk,
        reason=reason,
        requires_approval=requires_approval,
    )
    with _LOCK:
        _tasks[task.task_id] = task
    _append_worker_audit("dispatched", task)
    return task


def get_pending_task(worker_id: str) -> Optional[WorkerTask]:
    """Retorna a próxima task 'pending' e a marca como 'dispatched'."""
    with _LOCK:
        for task in _tasks.values():
            if task.status == "pending":
                task.status = "dispatched"
                task.worker_id = worker_id
                task.dispatched_at = _now()
                return task
    return None


def get_task(task_id: str) -> Optional[WorkerTask]:
    with _LOCK:
        return _tasks.get(task_id)


def list_tasks(status_filter: Optional[str] = None) -> list[WorkerTask]:
    with _LOCK:
        tasks = list(_tasks.values())
    if status_filter:
        tasks = [t for t in tasks if t.status == status_filter]
    return sorted(tasks, key=lambda t: t.created_at, reverse=True)


def mark_awaiting_approval(
    task_id: str,
    worker_id: str = "",
    reason: str = "",
) -> Optional[WorkerTask]:
    with _LOCK:
        task = _tasks.get(task_id)
        if not task:
            return None
        task.status = "awaiting_approval"
        task.worker_id = worker_id or task.worker_id
        task.requires_approval = True
        if reason:
            task.reason = reason
    _append_worker_audit("awaiting_approval", task)
    return task


def approve_worker_task(
    task_id: str,
    approved_by: str = "admin",
    deny_reason: str = "",
    approved: bool = True,
) -> Optional[WorkerTask]:
    with _LOCK:
        task = _tasks.get(task_id)
        if not task:
            return None
        if approved:
            task.status = "pending"         # volta para a fila → worker re-executa
            task.approval_status = "approved"
            task.approved_by = approved_by
            task.approved_at = _now()
            task.requires_approval = False  # já aprovado, executa sem pedir de novo
            _append_worker_audit("approved", task)
        else:
            task.status = "denied"
            task.approval_status = "denied"
            task.deny_reason = deny_reason
            task.denied_at = _now()
            _append_worker_audit("denied", task)
    return task


def complete_task(
    task_id: str,
    result: dict,
    ok: bool,
    error: str = "",
) -> Optional[WorkerTask]:
    with _LOCK:
        task = _tasks.get(task_id)
        if not task:
            return None
        task.status = "completed" if ok else "failed"
        task.result = result
        task.result_ok = ok
        task.error = error
        task.completed_at = _now()
    event = "completed" if ok else "failed"
    _append_worker_audit(event, task)
    return task


def list_awaiting_approvals() -> list[WorkerTask]:
    return list_tasks(status_filter="awaiting_approval")


# ─── Audit de Worker ─────────────────────────────────────────────────────────

def _append_worker_audit(event: str, task: WorkerTask) -> None:
    """Registra evento no audit log de worker."""
    _WORKER_AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(_WORKER_AUDIT_FILE.read_text(encoding="utf-8"))
    except Exception:
        existing = []

    entry = {
        "ts":        _now(),
        "event":     event,
        "task_id":   task.task_id,
        "action_id": task.action_id,
        "tool":      task.tool,
        "risk":      task.risk,
        "worker_id": task.worker_id,
        "session_id": task.session_id,
        "status":    task.status,
        "error":     task.error,
        "result_ok": task.result_ok,
    }
    existing.insert(0, entry)
    _WORKER_AUDIT_FILE.write_text(
        json.dumps(existing[:300], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_worker_audit(limit: int = 50) -> list[dict]:
    try:
        return json.loads(_WORKER_AUDIT_FILE.read_text(encoding="utf-8"))[:limit]
    except Exception:
        return []