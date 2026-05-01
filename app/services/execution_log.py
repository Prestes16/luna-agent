"""
luna/execution_log.py
─────────────────────────────────────────────────────────
Execution log da Luna — registra cada evento de execução
controlada com timestamp, tipo, contexto e resultado.

Estrutura de um log entry:
{
    "id":         str   – UUID único do evento
    "ts":         str   – ISO 8601 timestamp UTC
    "session_id": str   – ID da sessão atual
    "project_id": str   – projeto ativo (pode ser "global")
    "event":      str   – tipo do evento (ver EventType)
    "trigger":    str   – o que ativou o evento
    "action":     str   – o que a Luna fez
    "result":     str   – "ok" | "blocked" | "error"
    "detail":     dict  – dados extras livres por evento
    "safe_mode":  bool  – estava em safe_mode?
    "checkpoint": bool  – precisa de aprovação humana?
}
"""

import json
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger("luna.execution_log")

# ─── Diretório de logs ───────────────────────────────────
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
EXEC_LOG_FILE = LOG_DIR / "execution.jsonl"   # um JSON por linha
AUDIT_LOG_FILE = LOG_DIR / "audit.jsonl"       # eventos de segurança


# ─── Tipos de evento ────────────────────────────────────
class EventType(str, Enum):
    # Guards de segurança
    SAFE_MODE_TRIGGER    = "safe_mode_trigger"
    FAIL_CLOSED          = "fail_closed"
    IDENTITY_GUARD       = "identity_guard"
    SCOPE_VIOLATION      = "scope_violation"
    RATE_LIMIT_HIT       = "rate_limit_hit"

    # Execução de código
    CODE_EXEC_REQUEST    = "code_exec_request"
    CODE_EXEC_SUCCESS    = "code_exec_success"
    CODE_EXEC_FAIL       = "code_exec_fail"
    CODE_EXEC_BLOCKED    = "code_exec_blocked"
    CODE_EXEC_TIMEOUT    = "code_exec_timeout"

    # Ferramentas externas
    TOOL_CALL            = "tool_call"
    TOOL_RESULT          = "tool_result"
    TOOL_ERROR           = "tool_error"

    # Memória & contexto
    MEMORY_WRITE         = "memory_write"
    MEMORY_READ          = "memory_read"
    CONTEXT_SWITCH       = "context_switch"

    # Chat / resposta
    CHAT_RESPONSE        = "chat_response"
    STREAM_START         = "stream_start"
    STREAM_END           = "stream_end"

    # Autonomia
    AUTONOMOUS_ACTION    = "autonomous_action"
    CHECKPOINT_REQUIRED  = "checkpoint_required"
    CHECKPOINT_APPROVED  = "checkpoint_approved"
    CHECKPOINT_DENIED    = "checkpoint_denied"

    # Sistema
    HEALTH_CHECK         = "health_check"
    STARTUP              = "startup"
    SHUTDOWN             = "shutdown"
    ERROR                = "error"


# ─── Função principal ───────────────────────────────────
def append_execution_log(
    event:       EventType | str,
    trigger:     str,
    action:      str,
    result:      str                  = "ok",
    session_id:  Optional[str]        = None,
    project_id:  Optional[str]        = None,
    detail:      Optional[dict]       = None,
    safe_mode:   bool                 = False,
    checkpoint:  bool                 = False,
    is_audit:    bool                 = False,
) -> dict:
    """
    Registra um evento de execução no log.

    Args:
        event:      Tipo do evento (EventType ou string)
        trigger:    O que causou o evento
        action:     O que a Luna fez em resposta
        result:     "ok" | "blocked" | "error" | "pending"
        session_id: ID da sessão (gerado se None)
        project_id: Projeto ativo (default "global")
        detail:     Dados extras livres
        safe_mode:  Indica se estava em safe_mode
        checkpoint: Indica se precisa de aprovação humana
        is_audit:   Se True, também escreve no audit log

    Returns:
        O dict do entry criado
    """
    entry = {
        "id":         str(uuid.uuid4()),
        "ts":         datetime.now(timezone.utc).isoformat(),
        "session_id": session_id or "no-session",
        "project_id": project_id or "global",
        "event":      str(event),
        "trigger":    trigger,
        "action":     action,
        "result":     result,
        "detail":     detail or {},
        "safe_mode":  safe_mode,
        "checkpoint": checkpoint,
    }

    # Escreve no execution log
    _write_jsonl(EXEC_LOG_FILE, entry)

    # Eventos de segurança também vão pro audit log
    if is_audit or event in {
        EventType.SAFE_MODE_TRIGGER,
        EventType.FAIL_CLOSED,
        EventType.IDENTITY_GUARD,
        EventType.SCOPE_VIOLATION,
        EventType.CODE_EXEC_BLOCKED,
        EventType.CHECKPOINT_REQUIRED,
        EventType.CHECKPOINT_DENIED,
    }:
        _write_jsonl(AUDIT_LOG_FILE, entry)

    logger.info(
        f"[EXEC_LOG] {entry['event']} | result={result} | "
        f"project={entry['project_id']} | trigger={trigger[:80]}"
    )

    return entry


# ─── Leitura do log ─────────────────────────────────────
def read_execution_log(
    limit:      int           = 50,
    project_id: Optional[str] = None,
    event_type: Optional[str] = None,
    result:     Optional[str] = None,
    audit_only: bool          = False,
) -> list[dict]:
    """
    Lê os últimos N eventos do log com filtros opcionais.

    Args:
        limit:      Máximo de entradas a retornar
        project_id: Filtrar por projeto
        event_type: Filtrar por tipo de evento
        result:     Filtrar por resultado ("ok", "blocked", etc)
        audit_only: Ler só o audit log

    Returns:
        Lista de entries mais recentes primeiro
    """
    target_file = AUDIT_LOG_FILE if audit_only else EXEC_LOG_FILE

    if not target_file.exists():
        return []

    entries = []
    try:
        with open(target_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # Aplica filtros
                    if project_id and entry.get("project_id") != project_id:
                        continue
                    if event_type and entry.get("event") != event_type:
                        continue
                    if result and entry.get("result") != result:
                        continue
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue
    except OSError as e:
        logger.error(f"Erro ao ler execution log: {e}")
        return []

    # Mais recente primeiro, limitado
    return list(reversed(entries))[-limit:]


def get_log_stats() -> dict:
    """Retorna estatísticas rápidas do log de execução."""
    entries = read_execution_log(limit=10_000)
    if not entries:
        return {"total": 0, "by_event": {}, "by_result": {}, "checkpoints_pending": 0}

    by_event:  dict[str, int] = {}
    by_result: dict[str, int] = {}
    checkpoints_pending = 0

    for e in entries:
        ev = e.get("event", "unknown")
        rs = e.get("result", "unknown")
        by_event[ev]  = by_event.get(ev, 0) + 1
        by_result[rs] = by_result.get(rs, 0) + 1
        if e.get("checkpoint") and rs == "pending":
            checkpoints_pending += 1

    return {
        "total":               len(entries),
        "by_event":            by_event,
        "by_result":           by_result,
        "checkpoints_pending": checkpoints_pending,
        "last_event":          entries[-1] if entries else None,
    }


# ─── Helper interno ─────────────────────────────────────
def _write_jsonl(path: Path, entry: dict) -> None:
    """Escreve uma linha JSON no arquivo de forma segura."""
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.error(f"Falha ao escrever em {path}: {e}")
