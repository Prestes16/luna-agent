"""
Luna Agent - Modelos de dados
Estruturas Pydantic para configuração, requisições, planos e execução.
"""

from __future__ import annotations

from typing import Literal, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────
# Tipos literais
# ─────────────────────────────────────────────────────────────────────────

AgentMode = Literal["observe", "propose", "execute_safe", "blocked"]
ToolName = Literal[
    "list_dir", "read_file", "write_patch", "run_command", "read_log",
    "deploy", "recon", "solana_check", "fuzz", "code_analysis"
]
RiskLevel = Literal["low", "medium", "high", "critical"]
ExecutionTarget = Literal["local", "vps"]
ModelProvider = Literal["openai", "grok", "gemini", "claude"]


# ─────────────────────────────────────────────────────────────────────────
# Configuração do Agente
# ─────────────────────────────────────────────────────────────────────────

class AgentConfig(BaseModel):
    """Configuração central da Luna Agent."""
    
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
    execution_target: ExecutionTarget = "local"
    local_target_root: str = ""
    
    # Multi-modelo
    primary_model: ModelProvider = "openai"
    fallback_models: list[ModelProvider] = Field(default_factory=lambda: ["gemini", "grok"])
    model_routing_strategy: Literal["round_robin", "cost_aware", "latency_aware"] = "cost_aware"
    
    # Memória
    enable_memory: bool = True
    memory_backend: Literal["chromadb", "qdrant", "redis"] = "chromadb"
    memory_ttl_hours: int = 24
    
    # Solana (comercial)
    enable_solana: bool = False
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"
    solana_network: Literal["mainnet", "devnet", "testnet"] = "mainnet"
    credits_per_action: float = 1.0


class ToolAction(BaseModel):
    """Ação que o agente propõe executar."""
    
    action_id: str
    tool: ToolName
    args: dict = Field(default_factory=dict)
    risk: RiskLevel = "low"
    reason: str = ""
    needs_approval: bool = False


class AgentPlan(BaseModel):
    """Plano de execução gerado pelo agente."""
    
    session_id: str
    objective: str
    mode: AgentMode
    summary: str
    proposed_actions: list[ToolAction] = Field(default_factory=list)
    stop_reason: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AgentRequest(BaseModel):
    """Requisição para o agente executar uma tarefa."""
    
    session_id: str = ""
    objective: str
    mode: Optional[AgentMode] = None
    target_root: Optional[str] = None
    approved: bool = False
    execution_target: Optional[ExecutionTarget] = None
    local_target_root: Optional[str] = None


class ApprovalDecision(BaseModel):
    """Decisão de aprovação/rejeição de uma ação."""
    
    session_id: str = ""
    action_id: str
    approved: bool
    approved_by: str = ""
    deny_reason: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentExecutionResult(BaseModel):
    """Resultado da execução de uma ação."""
    
    session_id: str
    ok: bool
    action_id: str = ""
    tool: str = ""
    result: dict = Field(default_factory=dict)
    error: str = ""
    stop_reason: str = ""
    execution_time_ms: float = 0.0


class AgentState(BaseModel):
    """Estado atual do agente."""
    
    current_session_id: str = ""
    current_mode: AgentMode = "observe"
    current_objective: str = ""
    target_root: str = ""
    last_plan_id: str = ""
    last_action_id: str = ""
    last_result: str = ""
    blocked_reason: str = ""
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class AuditEntry(BaseModel):
    """Entrada de auditoria."""
    
    ts: str
    action_id: str
    tool: str
    risk: RiskLevel
    decision: Literal["approved", "denied", "auto_executed", "blocked", "failed", "dispatched"]
    session_id: str = ""
    target: str = ""
    result_ok: Optional[bool] = None
    error: str = ""


# ─────────────────────────────────────────────────────────────────────────
# Chat e Memória
# ─────────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    """Mensagem de chat."""
    
    role: Literal["user", "assistant", "agent", "system"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    """Requisição de chat."""
    
    message: str
    history: list[ChatMessage] = Field(default_factory=list)
    session_id: str | None = None
    mode: str = "dev"
    model: Optional[ModelProvider] = None


class MemoryEntry(BaseModel):
    """Entrada de memória."""
    
    id: str
    session_id: str
    content: str
    embedding: Optional[list[float]] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    ttl_hours: int = 24


# ─────────────────────────────────────────────────────────────────────────
# Worker (Distributed Execution)
# ─────────────────────────────────────────────────────────────────────────

WorkerTaskType = Literal[
    "list_dir", "read_file", "preview_patch", "apply_patch",
    "preview_command", "run_command", "screen_status", "screen_capture"
]


class WorkerTask(BaseModel):
    """Tarefa para um worker executar."""
    
    task_id: str
    session_id: str = ""
    action_id: str = ""
    type: str
    args: dict = Field(default_factory=dict)
    risk: RiskLevel = "low"
    requires_approval: bool = False
    created_at: str = ""


class WorkerTaskResult(BaseModel):
    """Resultado da execução de uma tarefa no worker."""
    
    task_id: str
    ok: bool
    result: dict = Field(default_factory=dict)
    error: str = ""
    stdout: str = ""
    stderr: str = ""
    finished_at: str = ""


class WorkerRegistration(BaseModel):
    """Registro de um worker."""
    
    worker_id: str
    hostname: str = ""
    capabilities: list[str] = Field(default_factory=list)
    allowed_dirs: list[str] = Field(default_factory=list)
    token: str = ""
    version: str = "2.0"


class WorkerHeartbeat(BaseModel):
    """Heartbeat de um worker."""
    
    worker_id: str
    status: str = "online"
    active_task: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WorkerScope(BaseModel):
    """Escopo de permissões de um worker."""
    
    allowed_dirs: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_commands: list[str] = Field(default_factory=list)
    require_approval_for_write: bool = True
    require_approval_for_command: bool = True
    max_actions_per_cycle: int = 5
    max_commands_per_cycle: int = 2


# ─────────────────────────────────────────────────────────────────────────
# Solana / Blockchain
# ─────────────────────────────────────────────────────────────────────────

class SolanaWallet(BaseModel):
    """Carteira Solana da Luna."""
    
    address: str
    private_key: Optional[str] = None  # Nunca serializar em logs
    network: Literal["mainnet", "devnet", "testnet"] = "mainnet"


class SolanaTransaction(BaseModel):
    """Transação Solana."""
    
    tx_id: str
    from_wallet: str
    to_wallet: str
    amount_lamports: int
    credits_purchased: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: Literal["pending", "confirmed", "failed"] = "pending"


class UserCredits(BaseModel):
    """Saldo de créditos do usuário."""
    
    user_id: str
    total_credits: float = 0.0
    used_credits: float = 0.0
    available_credits: float = 0.0
    last_transaction: Optional[datetime] = None
    transactions: list[SolanaTransaction] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────
# Guard Results
# ─────────────────────────────────────────────────────────────────────────

class GuardResult(BaseModel):
    """Resultado de uma verificação de segurança."""
    
    blocked: bool
    reason: str = ""
    event: str = "unknown"
    action: str = ""
    detail: dict = Field(default_factory=dict)
    safe_mode: bool = False
    checkpoint: bool = False
    response: Optional[str] = None
