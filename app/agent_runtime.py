from __future__ import annotations

from uuid import uuid4

from .agent_models import (
    AgentConfig,
    AgentExecutionResult,
    AgentPlan,
    ToolAction,
)
from .agent_policy import (
    is_target_root_allowed,
    requires_approval_for_tool,
)
from .agent_state_store import (
    load_last_plan,
    save_last_plan,
    update_agent_state,
)
from .agent_tools import (
    list_dir,
    read_file,
    read_log,
    run_command,
    write_patch,
)
from .tools.recon_tool import run_recon
from .tools.solana_tool import run_solana_check
from .tools.fuzz_tool import run_fuzz


class AgentRuntime:
    def __init__(self, cfg: AgentConfig):
        self.config = cfg

    def plan(self, objective: str, session_id: str = "") -> AgentPlan:
        sid = (session_id or "").strip() or f"agent-{uuid4().hex[:8]}"

        if not self.config.enabled:
            plan = AgentPlan(
                session_id=sid,
                objective=objective,
                mode="blocked",
                summary="Agente desabilitado pela configuração.",
                proposed_actions=[],
                stop_reason="agent_disabled",
            )
            save_last_plan(plan)
            update_agent_state(
                objective=objective,
                mode="blocked",
                target_root=self.config.target_root,
                last_plan="",
                last_result="Agente desabilitado",
                blocked_reason="agent_disabled",
                session_id=sid,
            )
            return plan

        if not self.config.target_root or not is_target_root_allowed(self.config.target_root):
            plan = AgentPlan(
                session_id=sid,
                objective=objective,
                mode="blocked",
                summary="target_root inválido ou fora da política.",
                proposed_actions=[],
                stop_reason="invalid_target_root",
            )
            save_last_plan(plan)
            update_agent_state(
                objective=objective,
                mode="blocked",
                target_root=self.config.target_root,
                last_plan="",
                last_result="target_root inválido",
                blocked_reason="invalid_target_root",
                session_id=sid,
            )
            return plan

        # Análise de intenção do objetivo para selecionar a ação mais adequada
        obj_lower = objective.lower()
        actions = []

        # Intenção: listar/explorar/mapear estrutura
        if any(kw in obj_lower for kw in [
            "listar", "list", "explorar", "explore", "mapear", "map",
            "ver", "view", "estrutura", "structure", "diretório", "directory",
            "pasta", "folder", "arquivos", "files", "conteúdo"
        ]):
            actions.append(ToolAction(
                action_id=f"act-{uuid4().hex[:8]}",
                tool="list_dir",
                args={"path": self.config.target_root},
                risk="low",
                reason="Listar o diretório alvo para entender a estrutura.",
                needs_approval=requires_approval_for_tool("list_dir", self.config),
            ))

        # Intenção: ler/analisar arquivo
        elif any(kw in obj_lower for kw in [
            "ler", "read", "analisar", "analyze", "ver arquivo",
            "código", "code", "conteúdo do arquivo"
        ]):
            actions.append(ToolAction(
                action_id=f"act-{uuid4().hex[:8]}",
                tool="read_file",
                args={"path": self.config.target_root},
                risk="low",
                reason="Ler o arquivo alvo para análise.",
                needs_approval=requires_approval_for_tool("read_file", self.config),
            ))

        # Intenção: executar comando
        elif any(kw in obj_lower for kw in [
            "executar", "execute", "rodar", "run", "comando", "command",
            "compilar", "compile", "testar", "test", "build"
        ]):
            actions.append(ToolAction(
                action_id=f"act-{uuid4().hex[:8]}",
                tool="run_command",
                args={"cmd": "echo 'Aguardando comando específico'", "cwd": self.config.target_root},
                risk="medium",
                reason="Executar comando no ambiente alvo. Requer aprovação.",
                needs_approval=requires_approval_for_tool("run_command", self.config),
            ))

        # Intenção: ler logs
        elif any(kw in obj_lower for kw in [
            "log", "logs", "histórico", "history", "auditoria", "audit"
        ]):
            actions.append(ToolAction(
                action_id=f"act-{uuid4().hex[:8]}",
                tool="read_log",
                args={"path": self.config.target_root},
                risk="low",
                reason="Ler logs do sistema para diagnóstico.",
                needs_approval=requires_approval_for_tool("read_log", self.config),
            ))

        # Intenção: Reconhecimento (Bug Bounty)
        elif any(kw in obj_lower for kw in ["recon", "reconhecimento", "mapear alvo", "subfinder", "httpx", "gau"]):
            actions.append(ToolAction(
                action_id=f"act-{uuid4().hex[:8]}",
                tool="recon",
                args={"target": self.config.target_root},
                risk="low",
                reason="Executar reconhecimento no alvo.",
                needs_approval=requires_approval_for_tool("recon", self.config),
            ))

        # Intenção: Solana Check
        elif any(kw in obj_lower for kw in ["solana", "anchor", "verificar contrato", "auditar", "check program"]):
            actions.append(ToolAction(
                action_id=f"act-{uuid4().hex[:8]}",
                tool="solana_check",
                args={"path": self.config.target_root},
                risk="medium",
                reason="Verificar e auditar o programa Solana.",
                needs_approval=requires_approval_for_tool("solana_check", self.config),
            ))

        # Intenção: Fuzzing
        elif any(kw in obj_lower for kw in ["fuzz", "fuzzing", "ffuf", "feroxbuster", "endpoints"]):
            actions.append(ToolAction(
                action_id=f"act-{uuid4().hex[:8]}",
                tool="fuzz",
                args={"target": self.config.target_root},
                risk="medium",
                reason="Executar fuzzing no alvo.",
                needs_approval=requires_approval_for_tool("fuzz", self.config),
            ))

        # Padrão: iniciar com list_dir para orientação
        else:
            actions.append(ToolAction(
                action_id=f"act-{uuid4().hex[:8]}",
                tool="list_dir",
                args={"path": self.config.target_root},
                risk="low",
                reason="Ação inicial padrão: listar diretório alvo para orientação.",
                needs_approval=requires_approval_for_tool("list_dir", self.config),
            ))

        action = actions[0]  # Ciclo mínimo: uma ação por vez

        plan = AgentPlan(
            session_id=sid,
            objective=objective,
            mode=self.config.mode,
            summary=f"Plano gerado para: {objective[:80]}. Ação: {action.tool}.",
            proposed_actions=actions,
            stop_reason="awaiting_approval" if action.needs_approval else "ready_to_execute",
        )

        save_last_plan(plan)
        update_agent_state(
            objective=objective,
            mode=self.config.mode,
            target_root=self.config.target_root,
            last_plan=action.action_id,
            last_result="Plano inicial gerado",
            blocked_reason="",
            session_id=sid,
        )
        return plan

    def execute(self, action: ToolAction, session_id: str = "") -> AgentExecutionResult:
        sid = (session_id or "").strip() or f"agent-{uuid4().hex[:8]}"

        last_plan = load_last_plan()
        preserved_objective = last_plan.objective if last_plan else ""
        preserved_plan_id = action.action_id

        if action.needs_approval:
            update_agent_state(
                objective=preserved_objective,
                mode="blocked",
                target_root=self.config.target_root,
                last_plan=preserved_plan_id,
                last_action=action.action_id,
                last_result="Ação bloqueada aguardando aprovação",
                blocked_reason="approval_required",
                session_id=sid,
            )
            return AgentExecutionResult(
                session_id=sid,
                ok=False,
                action_id=action.action_id,
                tool=action.tool,
                error="ação exige aprovação",
                stop_reason="approval_required",
            )

        if action.tool == "list_dir":
            result = list_dir(action.args["path"], self.config)
        elif action.tool == "read_file":
            result = read_file(action.args["path"], self.config)
        elif action.tool == "write_patch":
            result = write_patch(
                action.args["path"],
                action.args["old"],
                action.args["new"],
                self.config,
            )
        elif action.tool == "run_command":
            result = run_command(
                action.args["cmd"],
                action.args["cwd"],
                self.config,
            )
        elif action.tool == "read_log":
            result = read_log(action.args["path"], self.config)
        elif action.tool == "recon":
            target = action.args.get("target", "")
            result = run_recon(target)
        elif action.tool == "solana_check":
            path = action.args.get("path", ".")
            result = run_solana_check(path)
        elif action.tool == "fuzz":
            target = action.args.get("target", "")
            result = run_fuzz(target)
        else:
            result = {"ok": False, "error": f"tool não suportada: {action.tool}"}

        ok = bool(result.get("ok", False))
        update_agent_state(
            objective=preserved_objective,
            mode=self.config.mode if ok else "blocked",
            target_root=self.config.target_root,
            last_plan=preserved_plan_id,
            last_action=action.action_id,
            last_result="execução concluída" if ok else result.get("error", "erro"),
            blocked_reason="" if ok else "tool_execution_failed",
            session_id=sid,
        )

        return AgentExecutionResult(
            session_id=sid,
            ok=ok,
            action_id=action.action_id,
            tool=action.tool,
            result=result if ok else {},
            error="" if ok else result.get("error", "erro"),
            stop_reason="completed_one_cycle" if ok else "tool_execution_failed",
        )

    def preview(self, action: ToolAction) -> dict:
        """
        Retorna uma prévia do que a ação faria, sem executar.
        Útil para revisão humana antes de aprovação.
        """
        cfg = self.config

        if action.tool == "list_dir":
            path = action.args.get("path", cfg.target_root)
            return {
                "tool": action.tool,
                "action": f"Listar conteúdo do diretório: {path}",
                "risk": action.risk,
                "needs_approval": action.needs_approval,
            }

        elif action.tool == "read_file":
            path = action.args.get("path", "")
            return {
                "tool": action.tool,
                "action": f"Ler arquivo: {path}",
                "risk": action.risk,
                "needs_approval": action.needs_approval,
            }

        elif action.tool == "write_patch":
            path = action.args.get("path", "")
            find = action.args.get("old", "")[:100]
            replace = action.args.get("new", "")[:100]
            return {
                "tool": action.tool,
                "action": f"Aplicar patch em: {path}",
                "find_preview": find,
                "replace_preview": replace,
                "risk": action.risk,
                "needs_approval": action.needs_approval,
            }

        elif action.tool == "run_command":
            command = action.args.get("cmd", "")
            cwd = action.args.get("cwd", cfg.target_root)
            return {
                "tool": action.tool,
                "action": f"Executar: {command}",
                "cwd": cwd,
                "risk": action.risk,
                "needs_approval": action.needs_approval,
            }

        elif action.tool == "read_log":
            path = action.args.get("path", "")
            return {
                "tool": action.tool,
                "action": f"Ler log: {path}",
                "risk": action.risk,
                "needs_approval": action.needs_approval,
            }

        elif action.tool == "recon":
            target = action.args.get("target", "")
            return {
                "tool": action.tool,
                "action": f"Executar reconhecimento no alvo: {target}",
                "risk": action.risk,
                "needs_approval": action.needs_approval,
            }

        elif action.tool == "solana_check":
            path = action.args.get("path", ".")
            return {
                "tool": action.tool,
                "action": f"Auditar programa Solana em: {path}",
                "risk": action.risk,
                "needs_approval": action.needs_approval,
            }

        elif action.tool == "fuzz":
            target = action.args.get("target", "")
            return {
                "tool": action.tool,
                "action": f"Executar fuzzing no alvo: {target}",
                "risk": action.risk,
                "needs_approval": action.needs_approval,
            }

        return {
            "tool": action.tool,
            "action": "Ação desconhecida",
            "risk": action.risk,
            "needs_approval": action.needs_approval,
        }
