"""
Luna Agent - Runtime
Loop de execução ReAct com planejamento, execução e crítica.
"""

from __future__ import annotations

import logging
from uuid import uuid4
from typing import Optional

from app.models import (
    AgentConfig,
    AgentPlan,
    AgentRequest,
    ToolAction,
    AgentExecutionResult,
    RiskLevel,
)
from app.policy import (
    is_target_root_allowed,
    requires_approval_for_tool,
    classify_tool_risk,
)
from app.model_router import ModelRouter
from app.services.memory import stm_add, ltm_add, build_memory_context


logger = logging.getLogger("luna.runtime")


class AgentRuntime:
    """Runtime do agente com loop ReAct."""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.model_router = ModelRouter(config)
        self.last_plan: Optional[AgentPlan] = None
        self.last_result: Optional[AgentExecutionResult] = None
    
    def plan(
        self,
        objective: str,
        session_id: str = "",
        context: str = "",
    ) -> AgentPlan:
        """
        Fase 1: Planejamento (Thinking)
        Gerar um plano de ações baseado no objetivo.
        """
        
        sid = (session_id or "").strip() or f"agent-{uuid4().hex[:8]}"
        
        # Verificar se agente está habilitado
        if not self.config.enabled:
            return AgentPlan(
                session_id=sid,
                objective=objective,
                mode="blocked",
                summary="Agente desabilitado pela configuração.",
                proposed_actions=[],
                stop_reason="agent_disabled",
            )
        
        # Verificar target_root
        if not self.config.target_root or not is_target_root_allowed(self.config.target_root):
            return AgentPlan(
                session_id=sid,
                objective=objective,
                mode="blocked",
                summary="target_root inválido ou fora da política.",
                proposed_actions=[],
                stop_reason="invalid_target_root",
            )
        
        # Construir prompt para planejamento
        memory_context = build_memory_context(sid)
        system_prompt = self._build_system_prompt()
        planning_prompt = self._build_planning_prompt(
            objective, context, memory_context
        )
        
        # Chamar modelo para gerar plano
        try:
            response = self.model_router.call_model(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": planning_prompt},
                ],
                temperature=0.3,
                max_tokens=1024,
            )
            
            # Parsear resposta e extrair ações
            actions = self._parse_plan_response(response)
            
            plan = AgentPlan(
                session_id=sid,
                objective=objective,
                mode="propose",
                summary=response[:200],
                proposed_actions=actions,
                stop_reason="",
            )
            
            self.last_plan = plan
            stm_add(sid, "agent", f"Plano: {response[:500]}")
            
            return plan
        
        except Exception as e:
            logger.error(f"Erro ao gerar plano: {e}")
            return AgentPlan(
                session_id=sid,
                objective=objective,
                mode="blocked",
                summary=f"Erro ao gerar plano: {e}",
                proposed_actions=[],
                stop_reason="planning_error",
            )
    
    def execute(
        self,
        plan: AgentPlan,
        approved_actions: Optional[list[str]] = None,
    ) -> AgentExecutionResult:
        """
        Fase 2: Execução (Acting)
        Executar ações aprovadas do plano.
        """
        
        approved_actions = approved_actions or []
        
        # Executar apenas primeira ação (max_actions_per_cycle=1)
        if not plan.proposed_actions:
            return AgentExecutionResult(
                session_id=plan.session_id,
                ok=False,
                error="Nenhuma ação proposta",
                stop_reason="no_actions",
            )
        
        action = plan.proposed_actions[0]
        
        # Verificar aprovação se necessária
        if action.needs_approval and action.action_id not in approved_actions:
            return AgentExecutionResult(
                session_id=plan.session_id,
                ok=False,
                action_id=action.action_id,
                tool=action.tool,
                error="Ação requer aprovação",
                stop_reason="awaiting_approval",
            )
        
        # Executar ação
        try:
            result = self._execute_tool(action)
            self.last_result = result
            return result
        except Exception as e:
            logger.error(f"Erro ao executar ação {action.action_id}: {e}")
            return AgentExecutionResult(
                session_id=plan.session_id,
                ok=False,
                action_id=action.action_id,
                tool=action.tool,
                error=str(e),
                stop_reason="execution_error",
            )
    
    def critique(
        self,
        plan: AgentPlan,
        result: AgentExecutionResult,
        session_id: str = "",
    ) -> str:
        """
        Fase 3: Crítica (Self-Critique)
        Avaliar resultado e decidir próximos passos.
        """
        
        sid = session_id or plan.session_id
        
        # Construir prompt de crítica
        critique_prompt = self._build_critique_prompt(plan, result)
        
        try:
            response = self.model_router.call_model(
                messages=[
                    {"role": "system", "content": self._build_system_prompt()},
                    {"role": "user", "content": critique_prompt},
                ],
                temperature=0.5,
                max_tokens=512,
            )
            
            stm_add(sid, "agent", f"Crítica: {response[:500]}")
            return response
        
        except Exception as e:
            logger.error(f"Erro ao fazer crítica: {e}")
            return f"Erro ao avaliar resultado: {e}"
    
    # ─── Métodos Auxiliares ───────────────────────────────────────────────
    
    def _build_system_prompt(self) -> str:
        """Construir prompt de sistema."""
        return (
            "Você é a Luna, uma agente autônoma técnica de elite. "
            "Sua missão é ajudar com desenvolvimento, análise de segurança e automação. "
            "Você é capaz, confiável e segue rigorosamente as políticas de segurança. "
            "Sempre explique seu raciocínio e seja transparente sobre limitações."
        )
    
    def _build_planning_prompt(
        self,
        objective: str,
        context: str,
        memory_context: str,
    ) -> str:
        """Construir prompt de planejamento."""
        return f"""
Objetivo: {objective}

Contexto: {context}

{memory_context}

Gere um plano estruturado com as seguintes ações propostas:
1. Listar ações específicas (list_dir, read_file, run_command, etc.)
2. Explicar o risco de cada ação (low, medium, high)
3. Indicar quais ações requerem aprovação

Formato esperado:
Ação 1: [tool] - [descrição]
Risco: [low/medium/high]
Requer aprovação: [sim/não]
"""
    
    def _build_critique_prompt(
        self,
        plan: AgentPlan,
        result: AgentExecutionResult,
    ) -> str:
        """Construir prompt de crítica."""
        return f"""
Plano executado:
{plan.summary}

Resultado:
Sucesso: {result.ok}
Ferramenta: {result.tool}
Erro: {result.error}

Avalie:
1. O resultado atendeu ao objetivo?
2. Houve erros ou problemas?
3. Quais são os próximos passos?
"""
    
    def _parse_plan_response(self, response: str) -> list[ToolAction]:
        """Parsear resposta do modelo para extrair ações."""
        
        actions = []
        lines = response.split("\n")
        
        for line in lines:
            line = line.strip()
            if not line or not line.startswith("Ação"):
                continue
            
            # Extrair informações simples da linha
            # Formato esperado: "Ação 1: list_dir - descrição"
            try:
                parts = line.split("-")
                if len(parts) >= 2:
                    tool_part = parts[0].split(":")
                    if len(tool_part) >= 2:
                        tool = tool_part[1].strip().lower()
                        
                        # Validar tool
                        valid_tools = [
                            "list_dir", "read_file", "write_patch", "run_command",
                            "read_log", "deploy", "recon", "solana_check", "fuzz",
                        ]
                        if tool in valid_tools:
                            risk = self._extract_risk(line)
                            needs_approval = "sim" in line.lower() or "yes" in line.lower()
                            
                            actions.append(ToolAction(
                                action_id=f"act-{uuid4().hex[:8]}",
                                tool=tool,
                                args={"path": self.config.target_root},
                                risk=risk,
                                reason=" ".join(parts[1:]),
                                needs_approval=needs_approval,
                            ))
            except Exception as e:
                logger.debug(f"Erro ao parsear ação: {e}")
                continue
        
        return actions
    
    def _extract_risk(self, text: str) -> RiskLevel:
        """Extrair nível de risco do texto."""
        text_lower = text.lower()
        if "high" in text_lower or "alto" in text_lower:
            return "high"
        elif "medium" in text_lower or "médio" in text_lower:
            return "medium"
        else:
            return "low"
    
    def _execute_tool(self, action: ToolAction) -> AgentExecutionResult:
        """Executar uma ferramenta."""
        
        # Implementação simplificada
        # Em produção, isso chamaria os tools reais
        
        logger.info(f"Executando {action.tool}: {action.args}")
        
        return AgentExecutionResult(
            session_id="",
            ok=True,
            action_id=action.action_id,
            tool=action.tool,
            result={"status": "executed", "output": "Ferramenta executada com sucesso"},
            execution_time_ms=100.0,
        )
