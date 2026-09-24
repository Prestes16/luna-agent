import os
import unittest
from unittest.mock import patch

from app.cyber_prompt_kernel import (
    compile_cyber_kernel,
    select_output_contract,
    select_skill,
)
from app.luna_engine import _build_system_prompt


class CyberPromptKernelTests(unittest.TestCase):
    def test_skill_router_selects_web_api_for_http_auth_scenario(self) -> None:
        message = (
            "Target http://127.0.0.1:8080. GET /api/me retornou 200 e "
            "GET /api/admin/users retornou 403. Analise auth bypass."
        )
        self.assertEqual(select_skill(message), "WEB_API")

    def test_skill_router_does_not_activate_unrelated_malware_skill(self) -> None:
        message = "Analise GET /api/me e o limite de autorização observado."
        self.assertEqual(select_skill(message), "WEB_API")
        compiled = compile_cyber_kernel(message)
        self.assertNotIn("ACTIVE CYBER SKILL: MALWARE_ANALYSIS", compiled.text)

    def test_output_contract_is_selected_by_current_objective(self) -> None:
        self.assertEqual(
            select_output_contract("Construa um PoC reproduzível para validar o achado."),
            "EXPLOIT PROOF",
        )
        self.assertEqual(
            select_output_contract("Analise GET /api/me e a autorização HTTP."),
            "WEB / API",
        )

    def test_compiler_is_bounded_and_keeps_execution_plane_separate(self) -> None:
        compiled = compile_cyber_kernel(
            "Use curl para analisar http://127.0.0.1:8080/api/me e forneça um comando."
        )
        self.assertLessEqual(compiled.char_count, 5_200)
        self.assertIn("LUNA CYBER KERNEL V1 — COMPILED", compiled.text)
        self.assertIn("supervised executor only", compiled.text)
        self.assertIn("ACTIVE CYBER SKILL: WEB_API", compiled.text)
        self.assertTrue(compiled.tool_epistemology_included)

    def test_compiler_does_not_import_foreign_product_contracts(self) -> None:
        compiled = compile_cyber_kernel("Analise uma API HTTP autorizada.")
        foreign_markers = ("Claude Fable", "Anthropic", "{antml:", "/mnt/user-data")
        for marker in foreign_markers:
            self.assertNotIn(marker, compiled.text)

    def test_legacy_prompt_remains_default_when_feature_flag_is_off(self) -> None:
        with patch.dict(os.environ, {"LUNA_CYBER_KERNEL_V1": "false"}, clear=False):
            prompt = _build_system_prompt(
                r"D:\\workspace",
                current_message="Analise GET /api/me.",
                cyber_kernel_v1_enabled=False,
            )
        self.assertTrue(prompt.startswith("RUNTIME HARNESS — PREFIXO ESTÁVEL"))
        self.assertNotIn("LUNA CYBER KERNEL V1 — COMPILED", prompt)

    def test_feature_flag_path_compiles_kernel_without_losing_runtime_context(self) -> None:
        prompt = _build_system_prompt(
            r"D:\\workspace",
            current_message="Analise GET /api/me e forneça exatamente um comando curl.",
            scenario_context="SCENARIO CONTEXT\nTarget factual: http://127.0.0.1:8080",
            evidence_delta="EVIDENCE DELTA\nGET /api/me -> HTTP 200",
            cyber_kernel_v1_enabled=True,
        )
        self.assertTrue(prompt.startswith("LUNA CYBER KERNEL V1 — COMPILED"))
        self.assertIn("ACTIVE CYBER SKILL: WEB_API", prompt)
        self.assertIn("CONTEXTO DINÂMICO DE RUNTIME", prompt)
        self.assertIn("127.0.0.1:8080", prompt)
        self.assertIn("GET /api/me -> HTTP 200", prompt)
        self.assertLess(len(prompt), 9_000)

    def test_exact_one_command_instruction_survives_compilation(self) -> None:
        compiled = compile_cyber_kernel(
            "Forneça EXATAMENTE UM comando curl para o endpoint observado."
        )
        self.assertIn("ACTIVE CYBER SKILL: WEB_API", compiled.text)
        self.assertIn("Se pedirem exatamente um comando, entregue exatamente um", compiled.text)


if __name__ == "__main__":
    unittest.main()
