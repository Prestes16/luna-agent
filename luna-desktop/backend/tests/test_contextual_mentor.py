import json
import unittest
from unittest.mock import AsyncMock, patch

from app.luna_engine import LunaEngine, _build_system_prompt
from app.reasoning_pipeline import (
    action_fingerprint,
    build_replan_instruction,
    classify_complexity,
    validate_model_response,
)
from app.scenario_context import ScenarioContext
from tests.run_reasoning_pipeline_v3 import COMPLEX_FIXTURE, DEEP_FIXTURE, OLD_CONTEXT


GOOD_COMPLEX_RESPONSE = """FATOS: /api/me sem token retornou 401 com Bearer; o login retornou
role=user; o token funcionou em /api/me; a UI checa role admin; /api/admin/users foi
observado e ainda não foi testado.

INFERÊNCIAS: A autenticação Bearer funciona. O check client-side prova apenas a
apresentação visual e não prova autorização no backend.

HIPÓTESE: /api/admin/users pode exigir role admin no servidor.

```bash
curl -i -H "Authorization: Bearer TEST_TOKEN_123" http://127.0.0.1:8080/api/admin/users
```
"""


def scripted_model(engine: LunaEngine, *responses: str):
    remaining = list(responses)

    async def stream(
        client,
        model_name,
        messages,
        system,
        workspace,
        call_counter,
        history_out,
        reasoning_effort=None,
        turn_telemetry=None,
    ):
        scripted = remaining.pop(0)
        if isinstance(scripted, tuple):
            response, forced_finish_reason = scripted
        else:
            response, forced_finish_reason = scripted, None
        if turn_telemetry is not None:
            turn_telemetry["llm_called"] = True
            turn_telemetry["request_count"] += 1
            turn_telemetry.setdefault("attempt_efforts", []).append(reasoning_effort or "none")
            turn_telemetry.update({
                "chunks": turn_telemetry.get("chunks", 0) + max(1, len(response) // 32),
                "elapsed_ms": 1.0,
                "first_token_ms": 0.5 if response else None,
                "finish_reason": forced_finish_reason or ("stop" if response else "length"),
            })
        history_out[:] = [*messages, {"role": "assistant", "content": response}]
        for start in range(0, len(response), 32):
            yield json.dumps({"type": "text_chunk", "text": response[start:start + 32]})

    return patch.object(engine, "_stream_openai_with_tools", new=stream)


class ModelFirstPipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        with patch("app.luna_engine._ollama_is_available_sync", return_value=True):
            self.engine = LunaEngine()
        self.engine._ollama_available = True

    async def collect(self, prompt: str, session_id: str, *responses: str):
        with (
            patch.object(
                self.engine,
                "_auto_route_with_ollama_model",
                new=AsyncMock(return_value=("ollama", "luna-cyber-fast")),
            ),
            scripted_model(self.engine, *responses),
        ):
            events = [
                json.loads(raw)
                async for raw in self.engine.stream_agent(prompt, session_id=session_id)
            ]
        text = "".join(event.get("text", "") for event in events if event["type"] == "text_chunk")
        return text, events, self.engine.turn_metadata[session_id]

    async def test_complex_fixture_calls_model_and_replans_once(self) -> None:
        scenario = ScenarioContext()
        scenario.update(OLD_CONTEXT)
        self.engine.scenario_contexts["complex"] = scenario

        text, events, metadata = await self.collect(
            COMPLEX_FIXTURE,
            "complex",
            "",
            GOOD_COMPLEX_RESPONSE,
        )

        self.assertEqual(text, GOOD_COMPLEX_RESPONSE)
        self.assertEqual(metadata["response_source"], "model")
        self.assertTrue(metadata["llm_called"])
        self.assertEqual(metadata["provider"], "ollama")
        self.assertEqual(metadata["request_count"], 2)
        self.assertEqual(metadata["loop_guard"], "replan_passed")
        self.assertEqual(metadata["route"], "ANALYZE")
        self.assertNotIn("reasoning", {event["type"] for event in events})
        self.assertNotEqual(
            action_fingerprint(text),
            action_fingerprint("curl -i http://127.0.0.1:8080/"),
        )
        self.assertIn("TEST_TOKEN_123", json.dumps(self.engine.histories["complex"]))

    async def test_anti_loop_rejects_resolved_root_action(self) -> None:
        scenario = ScenarioContext()
        scenario.update(OLD_CONTEXT)
        self.engine.scenario_contexts["loop"] = scenario
        resolved = "```bash\ncurl -i http://127.0.0.1:8080/\n```"
        progressed = "O baseline da raiz já está resolvido. Traga um endpoint ou log novo observado."

        text, _, metadata = await self.collect("e agora?", "loop", resolved, progressed)

        self.assertEqual(text, progressed)
        self.assertEqual(metadata["request_count"], 2)
        self.assertEqual(metadata["loop_guard"], "replan_passed")

    async def test_explicit_retest_is_allowed_without_replan(self) -> None:
        scenario = ScenarioContext()
        scenario.update(OLD_CONTEXT)
        self.engine.scenario_contexts["retest"] = scenario
        response = "```bash\ncurl -i http://127.0.0.1:8080/\n```"

        text, _, metadata = await self.collect(
            "Repita o baseline para medir uma resposta variável de cache.",
            "retest",
            response,
        )

        self.assertEqual(text, response)
        self.assertEqual(metadata["request_count"], 1)
        self.assertEqual(metadata["loop_guard"], "retest_allowed")

    async def test_length_stop_forces_one_replan_even_when_partial_text_looks_valid(self) -> None:
        scenario = ScenarioContext()
        scenario.update(OLD_CONTEXT)
        self.engine.scenario_contexts["truncated"] = scenario

        text, _, metadata = await self.collect(
            COMPLEX_FIXTURE,
            "truncated",
            (GOOD_COMPLEX_RESPONSE, "length"),
            GOOD_COMPLEX_RESPONSE,
        )
        self.assertEqual(text, GOOD_COMPLEX_RESPONSE)
        self.assertEqual(metadata["request_count"], 2)
        self.assertTrue(metadata["replan_used"])
        self.assertEqual(metadata["loop_guard"], "replan_passed")

    async def test_fast_greeting_still_uses_model(self) -> None:
        text, _, metadata = await self.collect("olá", "fast", "Olá! Como posso ajudar?")
        self.assertEqual(text, "Olá! Como posso ajudar?")
        self.assertEqual(metadata["route"], "FAST")
        self.assertEqual(metadata["reasoning_effort"], "none")
        self.assertTrue(metadata["llm_called"])


class ScenarioAndRouterTests(unittest.TestCase):
    def test_complex_delta_preserves_new_evidence_and_exact_token(self) -> None:
        context = ScenarioContext()
        context.update(OLD_CONTEXT)
        delta = context.update(COMPLEX_FIXTURE)
        prompt = delta.to_prompt_block()

        self.assertGreaterEqual(delta.count, 9)
        self.assertIn("/api/admin/users", prompt)
        self.assertIn("Authorization Bearer observado: TEST_TOKEN_123", "\n".join(context.observed_facts))
        self.assertIn("TEST_TOKEN_123", "\n".join(context.observed_facts))

    def test_router_does_not_count_url_authority_as_endpoint(self) -> None:
        route = classify_complexity(
            "Target http://127.0.0.1:8080. GET /api/me. GET /api/admin/users.",
            evidence_delta_count=0,
        )
        self.assertIn("multiple_endpoints=2", route.reasons)
        self.assertNotIn("multiple_endpoints=3", route.reasons)

    def test_router_canonicalizes_trailing_prose_punctuation(self) -> None:
        route = classify_complexity(
            "Target http://127.0.0.1:8080. GET /api/me com token. "
            "GET /api/admin/users com token. Bundle referencia /api/admin/users.",
            evidence_delta_count=0,
        )
        self.assertIn("multiple_endpoints=2", route.reasons)
        self.assertNotIn("multiple_endpoints=3", route.reasons)

    def test_router_covers_none_low_medium(self) -> None:
        fast = classify_complexity("olá", evidence_delta_count=0)
        analyze = classify_complexity(COMPLEX_FIXTURE, evidence_delta_count=12)
        deep = classify_complexity(
            "Analise um modelo de ameaça com cadeia de vulnerabilidades, código e cinco artefatos.",
            evidence_delta_count=8,
        )
        self.assertEqual((fast.route, fast.reasoning_effort), ("FAST", "none"))
        self.assertEqual((analyze.route, analyze.reasoning_effort), ("ANALYZE", "low"))
        self.assertEqual((deep.route, deep.reasoning_effort), ("DEEP", "medium"))

    def test_action_fingerprint_normalizes_equivalent_curl(self) -> None:
        first = action_fingerprint("curl -i http://127.0.0.1:8080/")
        second = action_fingerprint("curl --silent -i 'http://127.0.0.1:8080/'")
        inline = action_fingerprint("`curl -i http://127.0.0.1:8080/`")
        self.assertEqual(first, "http:get:127.0.0.1:8080:/")
        self.assertEqual(first, second)
        self.assertEqual(first, inline)
        self.assertIsNone(
            action_fingerprint("O baseline já foi resolvido; não repita curl sem nova evidência.")
        )
        self.assertEqual(
            action_fingerprint("COMANDO: curl -i http://127.0.0.1:8080/"),
            first,
        )
        self.assertEqual(
            action_fingerprint("COMANDO curl -i http://127.0.0.1:8080/"),
            first,
        )
        self.assertEqual(
            action_fingerprint("**Comando único:** `curl -i http://127.0.0.1:8080/`"),
            first,
        )
        self.assertEqual(
            action_fingerprint("```bash curl -i http://127.0.0.1:8080/```"),
            first,
        )

    def test_retest_exception_and_invented_input_guard(self) -> None:
        context = ScenarioContext()
        context.update(OLD_CONTEXT)
        retest = validate_model_response(
            message="Repita para medir cache variável.",
            response="curl -i http://127.0.0.1:8080/",
            scenario=context,
            evidence_delta_count=0,
        )
        invented = validate_model_response(
            message="e agora?",
            response='curl -i -H "X-Original-URL: /admin" http://127.0.0.1:8080/',
            scenario=context,
            evidence_delta_count=0,
        )
        self.assertTrue(retest.valid)
        self.assertEqual(retest.loop_guard, "retest_allowed")
        self.assertFalse(invented.valid)
        self.assertIn("invented_input_not_observed", invented.reasons)

        invented_prose_endpoint = validate_model_response(
            message="e agora?",
            response="Os endpoints permitidos são / e /api/private; peça nova evidência.",
            scenario=context,
            evidence_delta_count=0,
        )
        self.assertIn("unobserved_endpoint_mentioned", invented_prose_endpoint.reasons)

        malformed_continuation = validate_model_response(
            message="e agora?",
            response="COMANDO: curl [PENDENTE]",
            scenario=context,
            evidence_delta_count=0,
        )
        self.assertIn(
            "continuation_has_no_observed_pending_action",
            malformed_continuation.reasons,
        )

    def test_next_test_with_new_current_evidence_is_not_blocked_as_stale_continuation(self) -> None:
        context = ScenarioContext()
        message = """Target http://127.0.0.1:8080
GET /api/me
HTTP/1.1 200 OK
String observada no bundle: /api/admin/users
Forneça exatamente um comando como próximo teste.
"""
        delta = context.update(message)
        self.assertGreater(delta.count, 0)
        self.assertTrue(context.action_history)
        self.assertIsNone(context.pending_question)

        validation = validate_model_response(
            message=message,
            response="curl -i http://127.0.0.1:8080/api/admin/users",
            scenario=context,
            evidence_delta_count=delta.count,
        )

        self.assertNotIn("no_observed_pending_action", validation.reasons)

    def test_observed_admin_role_may_be_explained_without_mutating_it(self) -> None:
        context = ScenarioContext()
        context.update(OLD_CONTEXT)
        delta = context.update(COMPLEX_FIXTURE)
        response = GOOD_COMPLEX_RESPONSE.replace(
            "a UI checa role admin",
            "a UI contém role: admin apenas no check visual",
        )

        validation = validate_model_response(
            message=COMPLEX_FIXTURE,
            response=response,
            scenario=context,
            evidence_delta_count=delta.count,
        )

        self.assertTrue(validation.valid, validation.reasons)

    def test_negated_role_mutation_language_is_not_treated_as_proposal(self) -> None:
        context = ScenarioContext()
        context.update(OLD_CONTEXT)
        delta = context.update(COMPLEX_FIXTURE)
        response = GOOD_COMPLEX_RESPONSE.replace(
            "HIPÓTESE: /api/admin/users pode exigir role admin no servidor.",
            "HIPÓTESE: /api/admin/users pode exigir role admin no servidor. "
            "O teste deve permanecer sem alterar a role nem o token.",
        )

        validation = validate_model_response(
            message=COMPLEX_FIXTURE,
            response=response,
            scenario=context,
            evidence_delta_count=delta.count,
        )

        self.assertTrue(validation.valid, validation.reasons)
        self.assertNotIn("invented_role_mutation", validation.reasons)

    def test_positive_unobserved_role_mutation_remains_rejected(self) -> None:
        context = ScenarioContext()
        context.update(OLD_CONTEXT)
        delta = context.update(COMPLEX_FIXTURE)
        response = GOOD_COMPLEX_RESPONSE + "\nTente alterar a role para admin antes do teste."

        validation = validate_model_response(
            message=COMPLEX_FIXTURE,
            response=response,
            scenario=context,
            evidence_delta_count=delta.count,
        )

        self.assertFalse(validation.valid)
        self.assertIn("invented_role_mutation", validation.reasons)

    def test_semantic_login_reference_counts_as_current_evidence(self) -> None:
        context = ScenarioContext()
        context.update(OLD_CONTEXT)
        delta = context.update(COMPLEX_FIXTURE)
        response = """FATOS: O login retornou role=user e a UI checa role admin;
/api/admin/users foi observado e ainda não foi testado.
INFERÊNCIA: O check client-side é visual e não prova autorização no backend.
HIPÓTESE: O servidor pode negar o usuário atual.
`curl -i -H "Authorization: Bearer TEST_TOKEN_123" http://127.0.0.1:8080/api/admin/users`
"""

        validation = validate_model_response(
            message=COMPLEX_FIXTURE,
            response=response,
            scenario=context,
            evidence_delta_count=delta.count,
        )

        self.assertTrue(validation.valid, validation.reasons)

    def test_unobserved_cookie_is_rejected(self) -> None:
        context = ScenarioContext()
        delta = context.update(COMPLEX_FIXTURE)
        response = GOOD_COMPLEX_RESPONSE + "\nTambém envie o Cookie completo."

        validation = validate_model_response(
            message=COMPLEX_FIXTURE,
            response=response,
            scenario=context,
            evidence_delta_count=delta.count,
        )

        self.assertFalse(validation.valid)
        self.assertIn("invented_input_not_observed", validation.reasons)

    def test_unobserved_method_and_request_body_are_rejected(self) -> None:
        context = ScenarioContext()
        context.update(OLD_CONTEXT)
        delta = context.update(COMPLEX_FIXTURE)
        response = GOOD_COMPLEX_RESPONSE.replace(
            'curl -i -H "Authorization: Bearer TEST_TOKEN_123"',
            'curl -i -X POST -d "method=GET" -H "Authorization: Bearer TEST_TOKEN_123"',
        )

        validation = validate_model_response(
            message=COMPLEX_FIXTURE,
            response=response,
            scenario=context,
            evidence_delta_count=delta.count,
        )

        self.assertIn("invented_request_body", validation.reasons)
        self.assertIn("unobserved_method_for_pending_endpoint", validation.reasons)

    def test_unobserved_authority_and_invalid_curl_target_are_rejected(self) -> None:
        context = ScenarioContext()
        delta = context.update(DEEP_FIXTURE)
        invented_host = validate_model_response(
            message=DEEP_FIXTURE,
            response="PRÓXIMO TESTE: `curl -i http://target/api/audit/export`",
            scenario=context,
            evidence_delta_count=delta.count,
        )
        relative_curl = validate_model_response(
            message=DEEP_FIXTURE,
            response="PRÓXIMO TESTE: `curl -i /api/audit/export`",
            scenario=context,
            evidence_delta_count=delta.count,
        )
        malformed_host = validate_model_response(
            message=DEEP_FIXTURE,
            response="PRÓXIMO TESTE: `curl -i http://[HOST]/api/audit/export`",
            scenario=context,
            evidence_delta_count=delta.count,
        )

        self.assertIn("proposed_unobserved_authority", invented_host.reasons)
        self.assertIn("invalid_curl_target", relative_curl.reasons)
        self.assertIn("invalid_curl_target", malformed_host.reasons)

    def test_dynamic_prompt_is_compact_and_marks_examples_non_factual(self) -> None:
        context = ScenarioContext()
        context.update(OLD_CONTEXT)
        prompt = _build_system_prompt(None, scenario_context=context.to_prompt_block())
        self.assertIn("Exemplos pre-carregados", prompt)
        self.assertIn("BUILD-TO-BREAK", prompt)
        self.assertIn("Quantitativo:", prompt)
        self.assertLess(len(prompt), 3_000)

    def test_replan_preserves_the_full_current_turn_contract(self) -> None:
        context = ScenarioContext()
        context.update(OLD_CONTEXT)
        delta = context.update(COMPLEX_FIXTURE)
        validation = validate_model_response(
            message=COMPLEX_FIXTURE,
            response="Resumo sem comando.",
            scenario=context,
            evidence_delta_count=delta.count,
        )

        instruction = build_replan_instruction(
            validation,
            context.to_prompt_block(500),
            COMPLEX_FIXTURE,
        )

        self.assertIn("FATOS, INFERÊNCIAS e HIPÓTESES", instruction)
        self.assertIn("client-side", instruction)
        self.assertIn("exatamente um comando", instruction)
        self.assertIn("/api/admin/users", instruction)


if __name__ == "__main__":
    unittest.main()
