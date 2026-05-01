from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ActionPhase:
    name: str
    status: str
    started_at: str
    completed_at: str
    notes: str


class ActionChain:
    def __init__(self):
        self._chains: dict[str, dict] = {}

    def start(self, task_summary: str) -> str:
        chain_id = f"chain-{uuid.uuid4().hex[:10]}"
        self._chains[chain_id] = {
            "task_summary": task_summary,
            "phases": [],
            "corrections": [],
            "verify_retries": 0,
            "key_facts": [],
        }
        self.advance(chain_id, "plan", "Chain iniciada")
        return chain_id

    def advance(self, chain_id: str, phase: str, notes: str = "") -> ActionPhase:
        chain = self._chains.get(chain_id)
        if not chain:
            return ActionPhase(phase, "failed", _now_iso(), _now_iso(), "chain inexistente")
        now = _now_iso()
        if chain["phases"]:
            last = chain["phases"][-1]
            if last.status == "running":
                last.status = "done"
                last.completed_at = now
        current = ActionPhase(name=phase, status="running", started_at=now, completed_at="", notes=notes)
        chain["phases"].append(current)
        if phase == "verify":
            chain["verify_retries"] += 1
        return current

    def record_correction(self, chain_id: str, error: str, fix: str):
        chain = self._chains.get(chain_id)
        if not chain:
            return
        chain["corrections"].append({"error": error[:500], "fix": fix[:300], "timestamp": _now_iso()})
        if fix:
            chain["key_facts"].append(f"Correção aplicada: {fix[:200]}")

    def get_state(self, chain_id: str) -> dict:
        chain = self._chains.get(chain_id, {})
        return {
            "task_summary": chain.get("task_summary", ""),
            "phases": [asdict(phase) for phase in chain.get("phases", [])],
            "corrections": list(chain.get("corrections", [])),
            "verify_retries": chain.get("verify_retries", 0),
        }

    def should_retry(self, chain_id: str) -> bool:
        chain = self._chains.get(chain_id)
        if not chain:
            return False
        return int(chain.get("verify_retries", 0)) < 3

    def build_delivery_summary(self, chain_id: str, tools_used: list[str]) -> str:
        chain = self._chains.get(chain_id, {})
        corrections = chain.get("corrections", [])
        lines = [
            f"✅ {chain.get('task_summary', 'Tarefa')} concluída",
            f"⚙️ Ferramentas usadas: {', '.join(tools_used[:12]) if tools_used else 'nenhuma'}",
            f"🛠️ Correções aplicadas: {len(corrections)}",
        ]
        for item in corrections[:4]:
            lines.append(f"- {item['fix']}")
        return "\n".join(lines)

    def export_for_memory(self, chain_id: str) -> dict:
        chain = self._chains.get(chain_id, {})
        return {
            "task_summary": chain.get("task_summary", ""),
            "corrections": list(chain.get("corrections", [])),
            "key_facts": list(dict.fromkeys(chain.get("key_facts", [])))[:10],
            "phases": [asdict(phase) for phase in chain.get("phases", [])],
        }