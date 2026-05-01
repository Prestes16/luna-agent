from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .agent_models import AgentConfig, AgentPlan, AgentState


WORKSPACE_DIR = Path("workspaces") / "luna-agent"
CONFIG_FILE = WORKSPACE_DIR / "agent_config.json"
STATE_FILE = WORKSPACE_DIR / "AGENT_STATE.md"
APPROVALS_FILE = WORKSPACE_DIR / "approvals.json"
LAST_PLAN_FILE = WORKSPACE_DIR / "last_plan.json"
AUDIT_FILE = WORKSPACE_DIR / "audit_log.json"


def ensure_agent_files() -> None:
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


def load_config() -> AgentConfig:
    ensure_agent_files()
    data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return AgentConfig(**data)


# Alias para compatibilidade com main.py
def load_agent_config() -> AgentConfig:
    return load_config()


def save_config(cfg: AgentConfig) -> None:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")


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

    lines = [
        "# Agent State",
        "",
        f"- session_id: {state.current_session_id}",
        f"- mode: {state.current_mode}",
        f"- objective: {state.current_objective}",
        f"- target_root: {state.target_root}",
        f"- last_plan_id: {state.last_plan_id}",
        f"- last_action_id: {state.last_action_id}",
        f"- last_result: {state.last_result}",
        f"- blocked_reason: {state.blocked_reason}",
    ]
    STATE_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_last_plan(plan: AgentPlan) -> None:
    ensure_agent_files()
    LAST_PLAN_FILE.write_text(plan.model_dump_json(indent=2), encoding="utf-8")


def load_last_plan() -> Optional[AgentPlan]:
    ensure_agent_files()
    raw = LAST_PLAN_FILE.read_text(encoding="utf-8").strip()
    if not raw or raw == "{}":
        return None
    return AgentPlan(**json.loads(raw))


def load_approvals() -> list[dict]:
    ensure_agent_files()
    return json.loads(APPROVALS_FILE.read_text(encoding="utf-8"))


def save_approvals(items: list[dict]) -> None:
    ensure_agent_files()
    APPROVALS_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def approve_action(
    action_id: str,
    session_id: str = "",
    approved: bool = True,
    approved_by: str = "",
    deny_reason: str = "",
) -> None:
    items = load_approvals()
    items = [i for i in items if i.get("action_id") != action_id]
    items.append({
        "action_id": action_id,
        "approved": approved,
        "session_id": session_id,
        "approved_by": approved_by,
        "deny_reason": deny_reason,
    })
    save_approvals(items)


def is_action_approved(action_id: str) -> bool:
    for item in load_approvals():
        if item.get("action_id") == action_id:
            return bool(item.get("approved", False))
    return False


def append_audit_entry(entry: dict) -> None:
    ensure_agent_files()
    try:
        items = json.loads(AUDIT_FILE.read_text(encoding="utf-8"))
    except Exception:
        items = []
    items.insert(0, entry)
    AUDIT_FILE.write_text(json.dumps(items[:200], indent=2, ensure_ascii=False), encoding="utf-8")


def load_audit_log(limit: int = 50) -> list[dict]:
    ensure_agent_files()
    try:
        return json.loads(AUDIT_FILE.read_text(encoding="utf-8"))[:limit]
    except Exception:
        return []


def load_agent_state() -> Optional[AgentState]:
    """Carrega o estado atual do agente a partir do AGENT_STATE.md."""
    ensure_agent_files()
    if not STATE_FILE.exists():
        return None
    try:
        lines = STATE_FILE.read_text(encoding="utf-8").splitlines()
        data = {}
        for line in lines:
            if line.startswith("- ") and ": " in line:
                key, _, value = line[2:].partition(": ")
                data[key.strip()] = value.strip()
        return AgentState(
            current_session_id=data.get("session_id", ""),
            current_mode=data.get("mode", "observe"),
            current_objective=data.get("objective", ""),
            target_root=data.get("target_root", ""),
            last_plan_id=data.get("last_plan_id", ""),
            last_action_id=data.get("last_action_id", ""),
            last_result=data.get("last_result", ""),
            blocked_reason=data.get("blocked_reason", ""),
        )
    except Exception:
        return None