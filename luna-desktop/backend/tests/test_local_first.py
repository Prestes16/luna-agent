import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.luna_engine import (
    LunaEngine,
    _build_system_prompt,
)
from app.module_loader import ModuleLoader
from app.reasoning_pipeline import classify_complexity, validate_model_response
from app.scenario_context import ScenarioContext
from app import security
from main import app


class LocalFirstTests(unittest.IsolatedAsyncioTestCase):
    def test_runtime_prompt_is_small_and_dynamic(self) -> None:
        prompt = _build_system_prompt(
            r"D:\workspace",
            context_summary="decisão atual",
            active_modules={"mentor": "trecho relevante"},
        )
        self.assertLess(len(prompt), 4_000)
        self.assertIn(r"D:\workspace", prompt)
        self.assertNotIn("MODO HUNTER", prompt)
        self.assertTrue(prompt.startswith("RUNTIME HARNESS — PREFIXO ESTÁVEL"))
        self.assertLess(
            prompt.index("Somente resposta final"),
            prompt.index("CONTEXTO DINÂMICO DE RUNTIME"),
        )

    def test_defaults_normalize_cloud_selection_to_local(self) -> None:
        with patch.dict(
            os.environ,
            {"LUNA_MODEL": "luna-cyber-fast", "LUNA_ZERO_CLOUD": "true"},
        ):
            engine = LunaEngine()
        self.assertEqual(engine.config["default_model"], "luna-cyber-fast")
        self.assertTrue(engine.config["zero_cloud_mode"])
        self.assertFalse(engine.config["tool_execution_enabled"])
        self.assertEqual(engine._resolve_model("ola", "gpt-4o"), ("ollama", "luna-cyber-fast"))

    def test_local_runtime_does_not_require_anthropic_sdk(self) -> None:
        with (
            patch("app.luna_engine.AsyncAnthropic", None),
            patch.dict(
                os.environ,
                {
                    "ANTHROPIC_API_KEY": "configured-but-sdk-optional",
                    "LUNA_ZERO_CLOUD": "true",
                },
            ),
        ):
            engine = LunaEngine()
        self.assertIsNone(engine.claude_client)
        self.assertTrue(engine.config["zero_cloud_mode"])
        self.assertNotIn("Claude", engine._available_providers)

    def test_local_diagnostics_exposes_harness_policy(self) -> None:
        engine = LunaEngine()
        diagnostics = engine.get_local_diagnostics()
        self.assertEqual(diagnostics["harness"]["version"], "harness-v1")
        self.assertEqual(diagnostics["harness"]["max_model_attempts"], 2)
        self.assertEqual(diagnostics["harness"]["max_tool_calls"], 0)
        self.assertFalse(diagnostics["harness"]["semantic_response_cache_enabled"])

    def test_instruction_only_build_cannot_be_enabled_by_runtime_config(self) -> None:
        engine = LunaEngine()
        self.assertTrue(engine.config["instruction_only_mode"])
        self.assertFalse(engine._tool_execution_allowed())
        engine.config["tool_execution_enabled"] = True
        self.assertFalse(engine._tool_execution_allowed())

    def test_runtime_prompt_carries_execution_authority_and_exploit_contract(self) -> None:
        from app.luna_engine import _build_system_prompt

        prompt = _build_system_prompt(supervised_mode=True)
        self.assertIn("L0 OBSERVE=AUTO", prompt)
        self.assertIn("L1 PROBE=ON_DEMAND", prompt)
        self.assertIn("L2 MUTATE", prompt)
        self.assertIn("L3 HIGH IMPACT", prompt)
        self.assertIn("artefato mínimo completo", prompt)
        self.assertIn("success predicate", prompt)
        self.assertIn("captura de logs/prints/evidência", prompt)

    def test_runtime_prompt_states_operator_executes_commands(self) -> None:
        prompt = _build_system_prompt(None, supervised_mode=True)
        self.assertIn("o operador executa comandos", prompt)

    async def test_ollama_unavailable_never_falls_back_to_cloud(self) -> None:
        with (
            patch("app.luna_engine._ollama_is_available_sync", return_value=False),
            patch("app.luna_engine._ollama_list_models_async", new=AsyncMock(return_value=[])),
        ):
            engine = LunaEngine()
            events = [
                json.loads(event)
                async for event in engine.stream_agent("ola", model_str="gpt-4o")
            ]
        self.assertEqual(events, [{
            "type": "error",
            "message": "Ollama não está acessível em localhost:11434.",
            "response_source": "system_error",
            "llm_called": False,
        }])

    def test_evidence_gate_rejects_invented_mutation_without_synthesizing(self) -> None:
        context = ScenarioContext()
        context.update(
            "CTF autorizado em http://127.0.0.1:8080. "
            "FATO: GET /admin retornou HTTP 403. "
            "HIPÓTESE: algum header pode alterar roteamento. "
            "Temos somente o status."
        )
        validation = validate_model_response(
            message="e agora?",
            response='curl -i -H "X-Forwarded-Host: internal" http://127.0.0.1:8080/admin',
            scenario=context,
            evidence_delta_count=0,
        )
        self.assertFalse(validation.valid)
        self.assertIn("invented_input_not_observed", validation.reasons)

    def test_simple_greeting_routes_fast_but_requires_llm(self) -> None:
        route = classify_complexity("olá!", evidence_delta_count=0)
        self.assertEqual(route.route, "FAST")
        self.assertTrue(route.llm_required)

    def test_initiator_selects_only_mentor_module(self) -> None:
        route = classify_complexity("Não sei usar o Initiator", evidence_delta_count=0)
        self.assertEqual(route.selected_modules, ("mentor_kali_devtools",))

    def test_lessons_remains_protected_and_accepts_local_ui_token(self) -> None:
        with patch.object(security, "LUNA_API_TOKEN", "local-ui-token"):
            client = TestClient(app)
            self.assertEqual(client.get("/lessons").status_code, 401)
            authorized = client.get(
                "/lessons",
                headers={"X-Luna-Token": "local-ui-token"},
            )
        self.assertEqual(authorized.status_code, 200)
        self.assertIn("total_lessons", authorized.json())


class ModuleLoaderTests(unittest.TestCase):
    def test_loader_is_read_only_and_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            modules_dir = Path(tmp) / "modules"
            modules_dir.mkdir()
            module_path = modules_dir / "module_mentor_kali_devtools.md"
            module_path.write_text(
                "# Mentor\n\n### INITIATOR\n\nSelecione a requisição no Network.\n",
                encoding="utf-8",
            )
            loader = ModuleLoader(tmp)
            content = loader.load_module("mentor_kali_devtools")
            self.assertIsNotNone(content)
            self.assertIsNone(loader.load_module("../escape"))
            self.assertIn("Selecione", loader.extract_section(content or "", "INITIATOR") or "")


if __name__ == "__main__":
    unittest.main()
