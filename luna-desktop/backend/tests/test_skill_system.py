import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agent_harness import AgentHarness
from app.luna_engine import LunaEngine, _build_system_prompt
from app.skill_loader import SkillLoader
from app.skill_router import SkillRouter


EXPECTED_SKILLS = {
    "audit-context-building",
    "entry-point-analyzer",
    "differential-review",
    "variant-analysis",
    "static-analysis",
    "semgrep-rule-creator",
    "property-based-testing",
    "constant-time-analysis",
    "post-patch-validation",
    "insecure-defaults",
    "solana-vulnerability-scanner",
    "token-integration-analyzer",
    "harness-writing",
    "coverage-analysis",
    "security-data-analysis",
}


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

    def test_repository_catalog_loads_all_expected_skills(self) -> None:
        loader = SkillLoader()
        loaded = loader.load_all()
        self.assertEqual(set(loaded), EXPECTED_SKILLS)
        for name, skill in loaded.items():
            self.assertTrue(skill.description, name)
            self.assertFalse(skill.public_metadata()["allowed_tools_authoritative"], name)
            self.assertIn(
                skill.metadata["luna-execution"],
                {"instruction-only"},
                name,
            )

    def test_audit_context_skill_is_read_only(self) -> None:
        skill = SkillLoader().load_skill("audit-context-building")
        self.assertIsNotNone(skill)
        self.assertEqual(skill.metadata["luna-domain"], "offensive-security")
        self.assertEqual(skill.metadata["luna-host-write"], "deny")
        self.assertIn("Read", skill.allowed_tools)
        self.assertNotIn("Bash", skill.allowed_tools)


class SkillRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = SkillLoader()
        self.skills = self.loader.load_all()
        self.router = SkillRouter()

    def select(self, message: str, scenario: str = ""):
        return self.router.select(message, self.skills, scenario_context=scenario)

    def test_audit_context_activates_for_unfamiliar_audit(self) -> None:
        decision = self.select(
            "Quero iniciar uma auditoria nesta codebase desconhecida e mapear a arquitetura."
        )
        self.assertIn("audit-context-building", decision.selected_skills)

    def test_solana_audit_composes_specialized_and_context_skills(self) -> None:
        decision = self.select(
            "Quero uma auditoria Solana deste programa e primeiro mapear a superfície de ataque."
        )
        self.assertEqual(
            decision.selected_skills,
            ("solana-vulnerability-scanner", "audit-context-building"),
        )
        self.assertLessEqual(len(decision.selected_skills), 2)

    def test_entry_point_analyzer_routes_explicit_surface_mapping(self) -> None:
        decision = self.select(
            "Mapeie os entry points e operações privilegiadas deste contrato Anchor."
        )
        self.assertEqual(decision.selected_skills[0], "entry-point-analyzer")

    def test_differential_review_routes_pr_or_diff(self) -> None:
        decision = self.select(
            "Faça review diff de segurança deste pull request e calcule o blast radius."
        )
        self.assertEqual(decision.selected_skills[0], "differential-review")

    def test_variant_requires_known_root_cause_context(self) -> None:
        blocked = self.select("Existem outras ocorrências desse mesmo bug?")
        self.assertNotIn("variant-analysis", blocked.selected_skills)

        enabled = self.select(
            "Existem outras ocorrências desse mesmo bug?",
            scenario="Finding confirmado: root cause é ownership check ausente.",
        )
        self.assertEqual(enabled.selected_skills[0], "variant-analysis")

    def test_static_analysis_and_semgrep_rule_do_not_conflict(self) -> None:
        scan = self.select("Faça static analysis e um Semgrep scan neste repositório.")
        self.assertEqual(scan.selected_skills[0], "static-analysis")

        rule = self.select("Crie uma regra Semgrep customizada para esse padrão.")
        self.assertEqual(rule.selected_skills[0], "semgrep-rule-creator")
        self.assertNotIn("static-analysis", rule.selected_skills)

    def test_post_patch_requires_fix_context(self) -> None:
        decision = self.select(
            "Validar correção: confirme se este patch resolveu o finding e não regrediu."
        )
        self.assertEqual(decision.selected_skills[0], "post-patch-validation")

    def test_insecure_defaults_and_token_integration_route(self) -> None:
        insecure = self.select(
            "Audite insecure defaults, default credentials e caminhos fail-open."
        )
        self.assertEqual(insecure.selected_skills[0], "insecure-defaults")

        token = self.select(
            "Revise esta token integration para fee-on-transfer e weird ERC20."
        )
        self.assertEqual(token.selected_skills[0], "token-integration-analyzer")

    def test_crypto_and_testing_skills_route_independently(self) -> None:
        ct = self.select("Revise esta rotina constant-time por timing side-channel.")
        self.assertEqual(ct.selected_skills[0], "constant-time-analysis")

        pbt = self.select("Crie property-based tests com proptest para estes invariantes.")
        self.assertEqual(pbt.selected_skills[0], "property-based-testing")

        harness = self.select("Escreva um fuzzing harness LLVMFuzzerTestOneInput para o parser.")
        self.assertEqual(harness.selected_skills[0], "harness-writing")

        coverage = self.select("O fuzzer plateau: analise a fuzz coverage do harness.")
        self.assertEqual(coverage.selected_skills[0], "coverage-analysis")

    def test_security_data_analysis_is_specific(self) -> None:
        security_data = self.select(
            "Analise estes logs de segurança e faça correlação de eventos por host."
        )
        self.assertEqual(security_data.selected_skills[0], "security-data-analysis")

        generic = self.select("Analise este CSV e calcule a média por mês.")
        self.assertNotIn("security-data-analysis", generic.selected_skills)

    def test_manual_skill_request_can_activate_even_if_auto_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "manual-only"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                """---
name: manual-only
description: Manual test skill.
metadata:
  luna-auto-activate: "false"
  luna-priority: "1"
  luna-execution: "instruction-only"
---
# Manual
""",
                encoding="utf-8",
            )
            skill = SkillLoader(tmp).load_skill("manual-only")
            decision = SkillRouter().select(
                "/skill manual-only use this procedure",
                {"manual-only": skill},
            )
        self.assertEqual(decision.selected_skills, ("manual-only",))

    def test_scenario_context_alone_cannot_auto_activate_a_skill(self) -> None:
        decision = self.select(
            "e agora?",
            scenario="auditoria codebase threat model entry points finding vulnerability",
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
        self.assertEqual(set(diagnostics["skills"]["loaded"]), EXPECTED_SKILLS)
        for metadata in diagnostics["skills"]["catalog"].values():
            self.assertFalse(metadata["allowed_tools_authoritative"])

    def test_skill_whitelist_can_be_narrowed_without_changing_authority(self) -> None:
        with (
            patch("app.luna_engine._ollama_is_available_sync", return_value=False),
            patch.dict(
                os.environ,
                {
                    "LUNA_ENABLED_SKILLS": "audit-context-building,security-data-analysis",
                    "LUNA_SKILLS_ENABLED": "true",
                },
            ),
        ):
            engine = LunaEngine()
        self.assertEqual(
            set(engine.active_skills),
            {"audit-context-building", "security-data-analysis"},
        )
        self.assertFalse(engine._tool_execution_allowed())
        self.assertEqual(engine.harness.public_policy()["max_tool_calls"], 0)


if __name__ == "__main__":
    unittest.main()
