import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agent_harness import AgentHarness
from app.luna_engine import LunaEngine, _build_system_prompt
from app.skill_loader import SkillLoader
from app.skill_router import SkillRouter


class SkillLoaderTests(unittest.TestCase):
    def test_loader_reads_agent_skill_subset_without_granting_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "sample-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                """---
name: sample-skill
description: >
  Build context for a sample security review.
metadata:
  luna-auto-activate: "true"
  luna-triggers: "audit, threat model"
allowed-tools: Read Grep Bash
---
# Sample

Read evidence before conclusions.
""",
                encoding="utf-8",
            )
            loader = SkillLoader(root)
            skill = loader.load_skill("sample-skill")

        self.assertIsNotNone(skill)
        self.assertEqual(skill.name, "sample-skill")
        self.assertIn("security review", skill.description)
        self.assertEqual(skill.allowed_tools, ("Read", "Grep", "Bash"))
        self.assertFalse(skill.public_metadata()["allowed_tools_authoritative"])

    def test_loader_rejects_traversal_and_name_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "safe-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                """---
name: other-skill
description: mismatch
---
body
""",
                encoding="utf-8",
            )
            loader = SkillLoader(root)
            self.assertIsNone(loader.load_skill("../outside"))
            self.assertIsNone(loader.load_skill("safe-skill"))

    def test_repository_audit_context_skill_is_valid_and_read_only(self) -> None:
        loader = SkillLoader()
        skill = loader.load_skill("audit-context-building")
        self.assertIsNotNone(skill)
        self.assertEqual(skill.metadata["luna-domain"], "offensive-security")
        self.assertEqual(skill.metadata["luna-execution"], "instruction-only")
        self.assertEqual(skill.metadata["luna-host-write"], "deny")
        self.assertIn("Read", skill.allowed_tools)
        self.assertNotIn("Bash", skill.allowed_tools)


class SkillRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = SkillLoader()
        self.skills = self.loader.load_enabled(["audit-context-building"])
        self.router = SkillRouter()

    def test_audit_context_activates_for_unfamiliar_audit(self) -> None:
        decision = self.router.select(
            "Quero iniciar uma auditoria nesta codebase desconhecida e mapear a arquitetura.",
            self.skills,
        )
        self.assertEqual(decision.selected_skills, ("audit-context-building",))
        self.assertTrue(any("trigger=" in reason for reason in decision.reasons))

    def test_audit_context_activates_for_threat_model(self) -> None:
        decision = self.router.select(
            "Construa um modelo de ameaça e identifique as trust boundaries deste serviço.",
            self.skills,
        )
        self.assertEqual(decision.selected_skills, ("audit-context-building",))

    def test_direct_probe_does_not_accidentally_activate_context_skill(self) -> None:
        decision = self.router.select(
            "Rode nmap -sV no alvo autorizado 10.10.10.5.",
            self.skills,
        )
        self.assertEqual(decision.selected_skills, ())

    def test_generic_data_analysis_does_not_activate_security_context_skill(self) -> None:
        decision = self.router.select(
            "Analise este CSV e calcule a média por mês.",
            self.skills,
        )
        self.assertEqual(decision.selected_skills, ())


class SkillRuntimeIntegrationTests(unittest.TestCase):
    def test_prompt_marks_skill_as_procedural_not_execution_authority(self) -> None:
        prompt = _build_system_prompt(
            None,
            active_skills={
                "audit-context-building": "Construa entendimento antes de procurar falhas."
            },
            supervised_mode=True,
        )
        self.assertIn("Skill procedural ativa", prompt)
        self.assertIn("sem autoridade de execução", prompt)
        self.assertIn("audit-context-building", prompt)
        self.assertIn("loop de ferramentas do modelo permanece bloqueado", prompt)

    def test_skill_system_does_not_change_harness_execution_authority(self) -> None:
        harness = AgentHarness()
        self.assertEqual(harness.public_policy()["max_tool_calls"], 0)

        with patch("app.luna_engine._ollama_is_available_sync", return_value=False):
            engine = LunaEngine()
        diagnostics = engine.get_local_diagnostics()

        self.assertFalse(engine._tool_execution_allowed())
        self.assertEqual(diagnostics["harness"]["max_tool_calls"], 0)
        self.assertIn("audit-context-building", diagnostics["skills"]["loaded"])
        self.assertFalse(
            diagnostics["skills"]["catalog"]["audit-context-building"][
                "allowed_tools_authoritative"
            ]
        )


if __name__ == "__main__":
    unittest.main()
