from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class ThinkingResult:
    plan_steps: list[str]
    risks: list[str]
    tool_budget: dict
    approach: str
    success_criteria: list[str]
    raw: str

    def to_prompt_injection(self) -> str:
        lines = ["## Plano de ação"]
        for index, step in enumerate(self.plan_steps or [], start=1):
            lines.append(f"{index}. {step}")
        if self.approach:
            lines.append("## Abordagem")
            lines.append(self.approach)
        if self.risks:
            lines.append("## Riscos")
            for risk in self.risks:
                lines.append(f"- {risk}")
        if self.success_criteria:
            lines.append("## Critérios de sucesso")
            for item in self.success_criteria:
                lines.append(f"- {item}")
        return "\n".join(lines)

    def to_guardrail_context(self) -> str:
        steps = "; ".join(self.plan_steps[:3]) if self.plan_steps else ""
        risks = "; ".join(self.risks[:2]) if self.risks else ""
        return f"Plano: {steps}\nRiscos: {risks}\nSucesso: {'; '.join(self.success_criteria[:2])}"


class ThinkingLayer:
    def __init__(self, client, model_id: str):
        self.client = client
        self.model_id = model_id

    def should_think(self, message: str, task_type: str) -> bool:
        try:
            lowered = (message or "").lower()
            if task_type in {"build", "debug", "bounty", "review", "solana", "security_audit", "bug_fix", "code_generation"}:
                return True
            trigger_words = ["implemente", "construa", "corrija", "debug", "bounty", "solana", "segurança", "security"]
            implicit_steps = sum(1 for token in [" e ", " depois ", " então ", " then "] if token in lowered)
            return any(word in lowered for word in trigger_words) or implicit_steps >= 2
        except Exception:
            return False

    def think(
        self,
        message: str,
        task_type: str,
        memory_context: str = "",
        workspace_context: str = "",
    ) -> ThinkingResult | None:
        try:
            prompt = (
                "Você é Luna. Antes de agir, raciocine sobre esta tarefa. "
                "Produza JSON válido com as chaves: plan_steps, risks, tool_budget, approach, success_criteria.\n\n"
                f"TASK_TYPE: {task_type}\n"
                f"MESSAGE: {message}\n\n"
                f"MEMORY:\n{memory_context[:1500]}\n\n"
                f"WORKSPACE:\n{workspace_context[:1500]}"
            )
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": "Responda apenas JSON válido."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=1024,
            )
            raw = (response.choices[0].message.content or "").strip()
            data = json.loads(raw)
            return ThinkingResult(
                plan_steps=[str(item) for item in data.get("plan_steps", [])],
                risks=[str(item) for item in data.get("risks", [])],
                tool_budget=dict(data.get("tool_budget", {})),
                approach=str(data.get("approach", "")),
                success_criteria=[str(item) for item in data.get("success_criteria", [])],
                raw=raw,
            )
        except Exception:
            return None