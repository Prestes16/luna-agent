"""
Luna Agent - State Store
Persistência de configuração, estado e auditoria.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from app.models import AgentConfig, AgentPlan, AgentState, AuditEntry


logger = logging.getLogger("luna.state_store")


# ─────────────────────────────────────────────────────────────────────────
# Caminhos de Arquivos
# ─────────────────────────────────────────────────────────────────────────

WORKSPACE_DIR = Path("workspaces") / "luna-agent"
CONFIG_FILE = WORKSPACE_DIR / "agent_config.json"
STATE_FILE = WORKSPACE_DIR / "agent_state.json"
APPROVALS_FILE = WORKSPACE_DIR / "approvals.json"
LAST_PLAN_FILE = WORKSPACE_DIR / "last_plan.json"
AUDIT_FILE = WORKSPACE_DIR / "audit_log.json"


# ─────────────────────────────────────────────────────────────────────────
# Inicialização
# ─────────────────────────────────────────────────────────────────────────

def ensure_workspace() -> None:
    """Garantir que os arquivos de workspace existem."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    
    if not CONFIG_FILE.exists():
        save_config(AgentConfig())
    
    if not APPROVALS_FILE.exists():
        APPROVALS_FILE.write_text("[]", encoding="utf-8")
    
    if not LAST_PLAN_FILE.exists():
        LAST_PLAN_FILE.write_text("{}", encoding="utf-8")
    
    if not AUDIT_FILE.exists():
        AUDIT_FILE.write_text("[]", encoding="utf-8")
    
    if not STATE_FILE.exists():
        update_agent_state()


# ─────────────────────────────────────────────────────────────────────────
# Configuração
# ─────────────────────────────────────────────────────────────────────────

def load_config() -> AgentConfig:
    """Carregar configuração do agente."""
    ensure_workspace()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return AgentConfig(**data)
    except Exception as e:
        logger.error(f"Erro ao carregar config: {e}")
        return AgentConfig()


def save_config(cfg: AgentConfig) -> None:
    """Salvar configuração do agente."""
    ensure_workspace()
    CONFIG_FILE.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Configuração salva")


# ─────────────────────────────────────────────────────────────────────────
# Estado
# ─────────────────────────────────────────────────────────────────────────

def load_agent_state() -> AgentState:
    """Carregar estado do agente."""
    ensure_workspace()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return AgentState(**data)
    except Exception as e:
        logger.error(f"Erro ao carregar estado: {e}")
        return AgentState()


def update_agent_state(
    objective: str = "",
    mode: str = "observe",
    target_root: str = "",
    last_plan: str = "",
    last_action: str = "",
    last_result: str = "",
    blocked_reason: str = "",
    session_id: str = "",
) -> None:
    """Atualizar estado do agente."""
    # Não chamar ensure_workspace() aqui para evitar recursão infinita.
    # ensure_workspace() já chama update_agent_state() para criar o STATE_FILE.
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    state = AgentState(
        current_session_id=session_id,
        current_mode=mode,
        current_objective=objective,
        target_root=target_root,
        last_plan_id=last_plan,
        last_action_id=last_action,
        last_result=last_result,
        blocked_reason=blocked_reason,
    )
    
    STATE_FILE.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    logger.debug("Estado do agente atualizado")


# ─────────────────────────────────────────────────────────────────────────
# Planos
# ─────────────────────────────────────────────────────────────────────────

def save_last_plan(plan: AgentPlan) -> None:
    """Salvar último plano."""
    ensure_workspace()
    LAST_PLAN_FILE.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    logger.debug(f"Plano salvo: {plan.session_id}")


def load_last_plan() -> Optional[AgentPlan]:
    """Carregar último plano."""
    ensure_workspace()
    try:
        raw = LAST_PLAN_FILE.read_text(encoding="utf-8").strip()
        if not raw or raw == "{}":
            return None
        data = json.loads(raw)
        return AgentPlan(**data)
    except Exception as e:
        logger.error(f"Erro ao carregar último plano: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────
# Aprovações
# ─────────────────────────────────────────────────────────────────────────

def approve_action(
    action_id: str,
    approved: bool = True,
    approved_by: str = "user",
    deny_reason: str = "",
) -> None:
    """Registrar aprovação de uma ação."""
    ensure_workspace()
    
    try:
        approvals = json.loads(APPROVALS_FILE.read_text(encoding="utf-8"))
    except Exception:
        approvals = []
    
    approval = {
        "action_id": action_id,
        "approved": approved,
        "approved_by": approved_by,
        "deny_reason": deny_reason,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    approvals.append(approval)
    APPROVALS_FILE.write_text(json.dumps(approvals, indent=2), encoding="utf-8")
    logger.info(f"Aprovação registrada: {action_id} = {approved}")


def is_action_approved(action_id: str) -> bool:
    """Verificar se uma ação foi aprovada."""
    ensure_workspace()
    
    try:
        approvals = json.loads(APPROVALS_FILE.read_text(encoding="utf-8"))
        for approval in approvals:
            if approval.get("action_id") == action_id and approval.get("approved"):
                return True
    except Exception:
        pass
    
    return False


# ─────────────────────────────────────────────────────────────────────────
# Auditoria
# ─────────────────────────────────────────────────────────────────────────

def append_audit_entry(entry: dict) -> None:
    """Adicionar entrada ao log de auditoria."""
    ensure_workspace()
    
    try:
        audit_log = json.loads(AUDIT_FILE.read_text(encoding="utf-8"))
    except Exception:
        audit_log = []
    
    audit_log.append(entry)
    
    # Manter apenas últimas 10000 entradas
    if len(audit_log) > 10000:
        audit_log = audit_log[-10000:]
    
    AUDIT_FILE.write_text(json.dumps(audit_log, indent=2), encoding="utf-8")
    logger.debug(f"Entrada de auditoria adicionada: {entry.get('action_id')}")


def load_audit_log(limit: int = 100) -> list[dict]:
    """Carregar log de auditoria."""
    ensure_workspace()
    
    try:
        audit_log = json.loads(AUDIT_FILE.read_text(encoding="utf-8"))
        return audit_log[-limit:]
    except Exception as e:
        logger.error(f"Erro ao carregar auditoria: {e}")
        return []
