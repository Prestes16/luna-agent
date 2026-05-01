"""
Luna Agent - Camada de Segurança (Guards)
Verificações de identidade, escopo, modo seguro e fail-closed.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.models import GuardResult


logger = logging.getLogger("luna.guards")


# ─────────────────────────────────────────────────────────────────────────
# Padrões de Jailbreak (Identity Guard)
# ─────────────────────────────────────────────────────────────────────────

IDENTITY_TRIGGERS = [
    r"\bignore\s+(all\s+)?(previous\s+)?instructions\b",
    r"\bforget\s+(you\s+are|who\s+you\s+are|your\s+(name|identity|rules))\b",
    r"\bpretend\s+(to\s+be|you\s+are)\s+(?!luna)",
    r"\bact\s+as\s+(?!luna)",
    r"\byou\s+are\s+now\s+(?!luna)",
    r"\bdan\b.*\bmode\b",
    r"\bjailbreak\b",
    r"\bno\s+restrictions?\b",
    r"\bdeveloper\s+mode\b",
    r"\bsystem\s+prompt\b.*\bignore\b",
    r"\brepeat\s+(your\s+)?(system\s+)?prompt\b",
    r"\bprint\s+(your\s+)?(instructions|system\s+prompt)\b",
    r"\bwhat\s+(are|is)\s+your\s+(system\s+prompt|instructions|rules)\b",
    r"\bcall\s+yourself\s+(?!luna)",
    r"\byour\s+name\s+is\s+(?!luna)",
    r"\brespond\s+as\s+(?!luna)",
]

IDENTITY_RESPONSE = (
    "Sou a Luna — sua copilota técnica. Não opero fora desse escopo. "
    "Se precisar de algo dentro das minhas capacidades, estou aqui."
)


# ─────────────────────────────────────────────────────────────────────────
# Padrões de Escopo (Scope Guard)
# ─────────────────────────────────────────────────────────────────────────

CHECKPOINT_PATTERNS = [
    r"\b(deletar?|drop|truncate|rm\s+-rf)\b.*\b(banco|database|tabela|table|produção|prod)\b",
    r"\bdeploye?\b.*\bprodução\b",
    r"\bpush\b.*\b(main|master|prod)\b",
    r"\btransfer(ir)?\b.*\b(sol|token|crypto|carteira)\b",
    r"\bsend\b.*\b(transaction|lamport|sol)\b.*\b(mainnet|main-net)\b",
]

BLOCKED_PATTERNS = [
    r"\b(ddos|dos)\s+(attack|atacar)\b",
    r"\bransomware\b",
    r"\bmalware\b.*\b(criar|create|build|fazer)\b",
    r"\binfectar\s+(servidor|sistema|computador)\b",
    r"\b(cpf|rg|senha|password)\s+(de\s+)?(alguém|pessoa|usuário|user)\b",
    r"\bapagar\s+(tudo|sistema|os)\b",
    r"\bformat(ar)?\s+(hd|disk|sistema)\b",
]

BLOCKED_RESPONSE = (
    "Essa ação está fora do escopo seguro de operação. "
    "Se for parte de um teste legítimo, configure o escopo no painel antes."
)

CHECKPOINT_RESPONSE = (
    "⚠️ Ação de alto impacto detectada. Registrei um checkpoint — "
    "confirme manualmente antes de prosseguir: `/approve {checkpoint_id}`"
)


# ─────────────────────────────────────────────────────────────────────────
# Padrões de Modo Seguro (Safe Mode Guard)
# ─────────────────────────────────────────────────────────────────────────

SAFE_MODE_TRIGGERS = [
    r"\b(pentest|penetration|exploit|vulnerability|vuln|cve)\b",
    r"\b(payload|shellcode|rop|gadget)\b",
    r"\b(reverse\s+engineering|disassembly|ida|ghidra)\b",
    r"\b(fuzzing|fuzz|afl|libfuzzer)\b",
    r"\b(malware|ransomware|trojan|worm)\b.*\b(analysis|análise)\b",
]

SAFE_MODE_PREFACE = (
    "⚠️ Modo Seguro Ativado: Detectei contexto de pesquisa de segurança/hacking. "
    "Vou proceder com cautela e documentar todas as ações. "
)


# ─────────────────────────────────────────────────────────────────────────
# Resultado de Guard
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class GuardCheckResult:
    """Resultado de uma verificação de guard."""
    
    blocked: bool
    reason: str = ""
    event: str = "unknown"
    action: str = ""
    detail: dict = field(default_factory=dict)
    safe_mode: bool = False
    checkpoint: bool = False
    response: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────
# Guards
# ─────────────────────────────────────────────────────────────────────────

def identity_guard(
    message: str,
    session_id: Optional[str] = None,
) -> GuardCheckResult:
    """Verificar tentativas de jailbreak/mudança de identidade."""
    
    msg_lower = message.lower()
    
    for pattern in IDENTITY_TRIGGERS:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            logger.warning(f"Identity guard bloqueou: {pattern}")
            return GuardCheckResult(
                blocked=True,
                reason=f"Padrão de identidade detectado: {pattern}",
                event="identity_guard",
                action="blocked",
                response=IDENTITY_RESPONSE,
                detail={"pattern": pattern},
            )
    
    return GuardCheckResult(blocked=False, event="identity_guard", action="pass")


def scope_guard(
    message: str,
    session_id: Optional[str] = None,
) -> GuardCheckResult:
    """Verificar se a ação está no escopo seguro."""
    
    msg_lower = message.lower()
    
    # Verificar bloqueios duros
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            logger.warning(f"Scope guard bloqueou: {pattern}")
            return GuardCheckResult(
                blocked=True,
                reason=f"Ação bloqueada: {pattern}",
                event="scope_violation",
                action="blocked",
                response=BLOCKED_RESPONSE,
                detail={"pattern": pattern, "type": "hard_block"},
            )
    
    # Verificar checkpoints
    for pattern in CHECKPOINT_PATTERNS:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            logger.info(f"Checkpoint detectado: {pattern}")
            return GuardCheckResult(
                blocked=False,
                reason=f"Checkpoint requerido: {pattern}",
                event="checkpoint_required",
                action="checkpoint",
                checkpoint=True,
                response=CHECKPOINT_RESPONSE,
                detail={"pattern": pattern, "type": "checkpoint"},
            )
    
    return GuardCheckResult(blocked=False, event="scope_guard", action="pass")


def safe_mode_guard(
    message: str,
    session_id: Optional[str] = None,
) -> GuardCheckResult:
    """Detectar contexto de pesquisa de segurança/hacking."""
    
    msg_lower = message.lower()
    
    for pattern in SAFE_MODE_TRIGGERS:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            logger.info(f"Safe mode ativado: {pattern}")
            return GuardCheckResult(
                blocked=False,
                reason=f"Contexto de segurança detectado: {pattern}",
                event="safe_mode_trigger",
                action="safe_mode_on",
                safe_mode=True,
                detail={"pattern": pattern},
            )
    
    return GuardCheckResult(blocked=False, event="safe_mode_guard", action="pass")


def fail_closed_guard(
    message: str,
    error: Optional[Exception] = None,
) -> GuardCheckResult:
    """Fallback quando algo quebra (fail-closed)."""
    
    if error:
        logger.error(f"Fail-closed guard ativado: {error}")
        return GuardCheckResult(
            blocked=True,
            reason="Erro de segurança detectado",
            event="fail_closed",
            action="blocked",
            response="Detectei um erro de segurança. Operação bloqueada por precaução.",
            detail={"error": str(error)},
        )
    
    return GuardCheckResult(blocked=False, event="fail_closed", action="pass")


# ─────────────────────────────────────────────────────────────────────────
# Pipeline de Guards
# ─────────────────────────────────────────────────────────────────────────

def run_all_guards(
    message: str,
    session_id: Optional[str] = None,
) -> tuple[GuardCheckResult, bool]:
    """
    Executar pipeline completo de guards.
    
    Retorna:
        (GuardCheckResult, safe_mode_active)
    """
    
    safe_mode_active = False
    
    # 1. Identity Guard
    result = identity_guard(message, session_id)
    if result.blocked:
        return result, safe_mode_active
    
    # 2. Scope Guard
    result = scope_guard(message, session_id)
    if result.blocked:
        return result, safe_mode_active
    
    if result.checkpoint:
        return result, safe_mode_active
    
    # 3. Safe Mode Guard
    result = safe_mode_guard(message, session_id)
    if result.safe_mode:
        safe_mode_active = True
    
    return GuardCheckResult(blocked=False, event="all_guards", action="pass"), safe_mode_active
