from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.memory.episodic import EpisodicMemory
from app.action_chain import ActionChain


def main() -> None:
    test_db = str(Path.home() / ".luna-agent" / "episodic_test.db")
    episodic = EpisodicMemory(db_path=test_db)
    session_a = episodic.record_session(
        session_id="sess-a",
        workspace_path="D:/luna-agent",
        task_type="build",
        summary="Criou estrutura inicial de memória episódica",
        tools_used=["write_file", "read_file"],
        outcome="success",
        key_facts=["SQLite em ~/.luna-agent", "Formato de prompt estabilizado"],
    )
    session_b = episodic.record_session(
        session_id="sess-b",
        workspace_path="D:/luna-agent",
        task_type="debug",
        summary="Corrigiu inconsistência de imports em runtime",
        tools_used=["read_file", "patch_file", "run_command"],
        outcome="partial",
        key_facts=["Guardrail não pode quebrar SSE", "run_command precisa registrar correção"],
    )

    recall = episodic.recall(workspace_path="D:/luna-agent", limit=5)
    facts = episodic.recall_key_facts("D:/luna-agent", limit=10)
    formatted = episodic.format_for_prompt(workspace_path="D:/luna-agent", task_type="build", limit=3)

    chain = ActionChain()
    chain_id = chain.start("Integrar módulos novos")
    chain.advance(chain_id, "execute", "Executando integração")
    chain.advance(chain_id, "verify", "Validando resultado")
    chain.record_correction(chain_id, "exit_code=1", "retry")
    chain.advance(chain_id, "correct", "Aplicando ajuste")
    chain.advance(chain_id, "deliver", "Gerando entrega final")
    state = chain.get_state(chain_id)
    exported = chain.export_for_memory(chain_id)
    summary = chain.build_delivery_summary(chain_id, ["read_file", "patch_file", "run_command"])

    print("== EpisodicMemory ==")
    print("session ids:", session_a, session_b)
    print("recall count:", len(recall))
    print("facts:", facts)
    print("formatted prompt:")
    print(formatted)
    print("\n== ActionChain ==")
    print("chain_id:", chain_id)
    print("state phases:", len(state.get("phases", [])))
    print("exported keys:", sorted(exported.keys()))
    print(summary)


if __name__ == "__main__":
    main()