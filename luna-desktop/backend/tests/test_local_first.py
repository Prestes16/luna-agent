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
from app.supervised_executor import RunnerResult
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

    def test_supervised_executor_defaults_disabled_but_l0_l1_policy_present(self) -> None:
        engine = LunaEngine()
        policy = engine.supervised_executor.public_policy()
        self.assertFalse(policy["enabled"])
        self.assertTrue(policy["allow_l0"])
        self.assertTrue(policy["allow_l1"])
        self.assertFalse(policy["allow_l2"])
        self.assertFalse(policy["allow_l3"])

        diagnostics = engine.get_local_diagnostics()
        self.assertIn("supervised_executor", diagnostics)
        self.assertFalse(diagnostics["supervised_executor"]["enabled"])

    async def test_supervised_executor_config_refresh_is_independent_of_model_tool_loop(self) -> None:
        engine = LunaEngine()
        await engine.update_config({
            "supervised_executor_enabled": True,
            "supervised_allow_l0": True,
            "supervised_allow_l1": True,
        })
        self.assertTrue(engine.supervised_executor.public_policy()["enabled"])
        self.assertFalse(engine._tool_execution_allowed())

    def test_preview_supervised_command_uses_scenario_scope_and_target(self) -> None:
        engine = LunaEngine()
        scenario = ScenarioContext()
        scenario.update("CTF autorizado em http://10.10.10.5")
        engine.scenario_contexts["exec"] = scenario
        preview = engine.preview_supervised_command(
            "nmap -sV 10.10.10.5",
            conversation_id="exec",
            operator_request_text="Luna, rode esse nmap no alvo autorizado.",
        )
        self.assertEqual(preview["authority"], "ON_DEMAND")
        self.assertEqual(preview["target"], "10.10.10.5")

    async def test_engine_supervised_executor_runs_bound_l1_only_through_separate_gate(self) -> None:
        engine = LunaEngine()
        scenario = ScenarioContext()
        scenario.update("CTF autorizado em http://10.10.10.5")
        engine.scenario_contexts["exec-run"] = scenario

        calls = []

        async def fake_runner(argv, timeout_seconds, max_output_bytes):
            calls.append((argv, timeout_seconds, max_output_bytes))
            return RunnerResult(
                exit_code=0,
                stdout=b"80/tcp open http\n",
                stderr=b"",
            )

        engine.supervised_executor._runner = fake_runner
        stored = []

        def evidence_sink(conversation_id, command_sha256, kind, raw, observed_at):
            stored.append((conversation_id, command_sha256, kind, raw, observed_at))
            return {"kind": kind, "byte_length": len(raw)}

        engine.execution_evidence_sink = evidence_sink
        denied = await engine.execute_supervised_command(
            "nmap -sV 10.10.10.5",
            conversation_id="exec-run",
            operator_request_text="Luna, rode esse nmap no alvo autorizado.",
        )
        self.assertEqual(denied["status"], "denied")
        self.assertIn("supervised_executor_disabled", denied["denial_reasons"])
        self.assertEqual(calls, [])

        await engine.update_config({"supervised_executor_enabled": True})
        allowed = await engine.execute_supervised_command(
            "nmap -sV 10.10.10.5",
            conversation_id="exec-run",
            operator_request_text="Luna, rode esse nmap no alvo autorizado.",
        )
        self.assertEqual(allowed["status"], "executed")
        self.assertEqual(allowed["intent"]["authority"], "ON_DEMAND")
        self.assertEqual(allowed["stdout"], "80/tcp open http\n")
        self.assertEqual(len(allowed["evidence"]), 1)
        self.assertEqual(len(allowed["evidence_records"]), 1)
        self.assertEqual(stored[0][0], "exec-run")
        self.assertEqual(stored[0][2], "stdout")
        self.assertEqual(stored[0][3], b"80/tcp open http\n")
        self.assertFalse(engine._tool_execution_allowed())
        self.assertEqual(len(calls), 1)

    async def test_engine_one_shot_approval_executes_privileged_probe_once(self) -> None:
        engine = LunaEngine()
        scenario = ScenarioContext()
        scenario.update("CTF autorizado em http://10.10.10.5")
        engine.scenario_contexts["approval"] = scenario
        await engine.update_config({"supervised_executor_enabled": True})

        calls = []

        async def fake_runner(argv, timeout_seconds, max_output_bytes):
            calls.append(argv)
            return RunnerResult(exit_code=0, stdout=b"syn-ok\n", stderr=b"")

        engine.supervised_executor._runner = fake_runner
        command = "sudo nmap -sS 10.10.10.5"
        grant = engine.issue_supervised_execution_approval(
            command,
            conversation_id="approval",
            operator_request_text="Luna, rode o SYN scan no alvo autorizado.",
            operator_confirmed=True,
        )
        self.assertEqual(engine.execution_approval_store.count(), 1)

        first = await engine.execute_supervised_command(
            command,
            conversation_id="approval",
            operator_request_text="Luna, rode o SYN scan no alvo autorizado.",
            approval_token=grant["approval_token"],
        )
        self.assertEqual(first["status"], "executed")
        self.assertEqual(engine.execution_approval_store.count(), 0)
        self.assertEqual(len(calls), 1)

        second = await engine.execute_supervised_command(
            command,
            conversation_id="approval",
            operator_request_text="Luna, rode o SYN scan no alvo autorizado.",
            approval_token=grant["approval_token"],
        )
        self.assertEqual(second["status"], "denied")
        self.assertIn(
            "approval_token_invalid_or_expired",
            second["denial_reasons"],
        )
        self.assertEqual(len(calls), 1)

    def test_instruction_only_build_cannot_be_enabled_by_runtime_config(self) -> None:
        engine = LunaEngine()
        self.assertTrue(engine.config["instruction_only_mode"])
        self.assertFalse(engine._tool_execution_allowed())
        engine.config["tool_execution_enabled"] = True
        self.assertFalse(engine._tool_execution_allowed())

    def test_runtime_prompt_carries_execution_authority_and_exploit_contract(self) -> None:
        from app.luna_engine import _build_system_prompt

        prompt = _build_system_prompt(None, supervised_mode=True)
        self.assertIn("L0 OBSERVE=AUTO", prompt)
        self.assertIn("L1 PROBE=ON_DEMAND", prompt)
        self.assertIn("L2 MUTATE", prompt)
        self.assertIn("L3 HIGH IMPACT", prompt)
        self.assertIn("artefato mínimo completo", prompt)
        self.assertIn("success predicate", prompt)
        self.assertIn("captura de logs/prints/evidência", prompt)

    def test_runtime_prompt_states_operator_controls_execution(self) -> None:
        prompt = _build_system_prompt(None, supervised_mode=True)
        self.assertIn("o operador controla alvo/escopo/autoridade", prompt)
        self.assertIn("executor supervisionado sob demanda", prompt)
        self.assertIn("loop de ferramentas do modelo permanece bloqueado", prompt)

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
