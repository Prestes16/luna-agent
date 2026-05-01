from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


AgentMode = Literal["observe", "propose", "execute_safe", "blocked"]
ToolName = Literal["list_dir", "read_file", "write_patch", "run_command", "read_log", "deploy", "recon", "solana_check", "fuzz"]
RiskLevel = Literal["low", "medium", "high"]
ExecutionTarget = Literal["vps", "local"]


class AgentConfig(BaseModel):
    enabled: bool = True
    mode: AgentMode = "propose"
    target_root: str = ""
    safe_base_dirs: list[str] = Field(default_factory=list)
    allow_write: bool = True
    allow_run_command: bool = True
    max_actions_per_cycle: int = 1
    max_commands_per_cycle: int = 1
    require_approval_for_write: bool = True
    require_approval_for_command: bool = True
    execution_target: ExecutionTarget = "vps"
    local_target_root: str = ""  # path on local machine, used when execution_target="local"


class ToolAction(BaseModel):
    action_id: str
    tool: ToolName
    args: dict = Field(default_factory=dict)
    risk: RiskLevel = "low"
    reason: str = ""
    needs_approval: bool = False


class AgentPlan(BaseModel):
    session_id: str
    objective: str
    mode: AgentMode
    summary: str
    proposed_actions: list[ToolAction] = Field(default_factory=list)
    stop_reason: str = ""


class AgentRequest(BaseModel):
    session_id: str = ""
    objective: str
    mode: Optional[AgentMode] = None
    target_root: Optional[str] = None
    approved: bool = False
    execution_target: Optional[ExecutionTarget] = None
    local_target_root: Optional[str] = None


class ApprovalDecision(BaseModel):
    session_id: str = ""
    action_id: str
    approved: bool
    approved_by: str = ""
    deny_reason: str = ""


class AgentExecutionResult(BaseModel):
    session_id: str
    ok: bool
    action_id: str = ""
    tool: str = ""
    result: dict = Field(default_factory=dict)
    error: str = ""
    stop_reason: str = ""


class AgentState(BaseModel):
    current_session_id: str = ""
    current_mode: AgentMode = "observe"
    current_objective: str = ""
    target_root: str = ""
    last_plan_id: str = ""
    last_action_id: str = ""
    last_result: str = ""
    blocked_reason: str = ""


class AuditEntry(BaseModel):
    ts: str
    action_id: str
    tool: str
    risk: RiskLevel
    decision: Literal["approved", "denied", "auto_executed", "blocked", "failed", "dispatched"]
    session_id: str = ""
    target: str = ""
    result_ok: Optional[bool] = None
    error: str = ""


# ── Worker models ─────────────────────────────────────────────────────────────

WorkerTaskType = Literal[
    "list_dir", "read_file", "preview_patch", "apply_patch",
    "preview_command", "run_command", "screen_status", "screen_capture"
]


class WorkerTask(BaseModel):
    task_id: str
    session_id: str = ""
    action_id: str = ""
    type: str
    args: dict = Field(default_factory=dict)
    risk: RiskLevel = "low"
    requires_approval: bool = False
    created_at: str = ""


class WorkerTaskResult(BaseModel):
    task_id: str
    ok: bool
    result: dict = Field(default_factory=dict)
    error: str = ""
    stdout: str = ""
    stderr: str = ""
    finished_at: str = ""


class WorkerRegistration(BaseModel):
    worker_id: str
    hostname: str = ""
    capabilities: list[str] = Field(default_factory=list)
    allowed_dirs: list[str] = Field(default_factory=list)
    token: str = ""
    version: str = "1.0"


class WorkerHeartbeat(BaseModel):
    worker_id: str
    status: str = "online"
    active_task: Optional[str] = None


class WorkerScope(BaseModel):
    allowed_dirs: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_commands: list[str] = Field(default_factory=list)
    require_approval_for_write: bool = True
    require_approval_for_command: bool = True
    max_actions_per_cycle: int = 5
    max_commands_per_cycle: int = 2
