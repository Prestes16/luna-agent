"""Run the V3 Golden Tests against the real local Ollama production pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.luna_engine import LunaEngine
from app.reasoning_pipeline import action_fingerprint, validate_model_response
from app.scenario_context import ScenarioContext


OLD_CONTEXT = """Estou no Kali Linux, sou iniciante e este é um CTF autorizado em
http://127.0.0.1:8080. Rodei:
curl -i http://127.0.0.1:8080/
HTTP/1.1 200 OK
Content-Type: application/json
{"name":"demo","status":"ok"}
"""

COMPLEX_FIXTURE = """GET /api/me sem Authorization:
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Content-Type: application/json
{"error":"missing token"}

POST /api/login:
HTTP/1.1 200 OK
{"token":"TEST_TOKEN_123","role":"user"}

GET /api/me com:
Authorization: Bearer TEST_TOKEN_123

retornou:
HTTP/1.1 200 OK
Content-Type: application/json
{"id":7,"username":"demo","role":"user"}

Frontend observado:
if (user.role === "admin") {
  showAdminPanel()
}

String observada no bundle:
/api/admin/users

/api/admin/users ainda NÃO foi testado.

Separe fatos, inferências e hipóteses. Explique o que o client-side prova e não
prova. Escolha somente o próximo teste de maior valor, explique para iniciante e
forneça apenas um comando. Não adultere role ou token.
"""

DEEP_FIXTURE = """Analise cuidadosamente esta cadeia autorizada de CTF e escolha o
próximo teste sem inventar evidência. Há cinco artefatos correlacionados:
1. GET /api/me sem token -> HTTP/1.1 401 Unauthorized.
2. POST /api/login -> HTTP/1.1 200 OK e role=user.
3. GET /api/me com token -> HTTP/1.1 200 OK.
4. GET /api/admin/users com user -> HTTP/1.1 403 Forbidden.
5. O frontend esconde o painel com este código:
```javascript
const canSeeAdmin = user.role === 'admin'
if (canSeeAdmin) showAdminPanel()
```
6. O bundle também referencia GET /api/audit/export, ainda não testado.
Considere modelo de ameaça, possíveis fronteiras de confiança, hipóteses alternativas
e regressões, mas entregue só a resposta final e no máximo um próximo teste.
"""


async def collect(engine: LunaEngine, prompt: str, session_id: str) -> dict[str, Any]:
    response = ""
    error = ""
    event_types: list[str] = []
    started = time.perf_counter()
    async for raw_event in engine.stream_agent(prompt, session_id=session_id):
        event = json.loads(raw_event)
        event_types.append(str(event.get("type", "")))
        if event.get("type") == "text_chunk":
            response += str(event.get("text", ""))
        elif event.get("type") == "error":
            error = str(event.get("message", "erro desconhecido"))
    return {
        "prompt": prompt,
        "response": response,
        "error": error,
        "event_types": event_types,
        "wall_elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "metadata": engine.turn_metadata[session_id],
    }


async def probe_reasoning_effort(engine: LunaEngine, effort: str) -> dict[str, Any]:
    _, model_name = await engine._auto_route_with_ollama_model("probe", "luna-cyber-fast")
    route = {"none": "FAST", "low": "ANALYZE", "medium": "DEEP"}[effort]
    telemetry: dict[str, Any] = {
        "session_id": f"v3-probe-{effort}",
        "route": route,
        "request_count": 0,
        "chunks": 0,
        "llm_called": False,
    }
    history_out: list[dict[str, Any]] = []
    response = ""
    started = time.perf_counter()
    generator = engine._stream_openai_with_tools(
        engine.ollama_client,
        model_name,
        [{"role": "user", "content": "Responda apenas: OK"}],
        "Teste local de compatibilidade. Entregue apenas OK, sem raciocínio visível.",
        "",
        [0],
        history_out,
        effort,
        telemetry,
    )
    try:
        async for raw_event in generator:
            event = json.loads(raw_event)
            if event.get("type") == "text_chunk":
                response += str(event.get("text", ""))
        error = ""
    except Exception as exc:
        error = type(exc).__name__
    return {
        "effort": effort,
        "response": response,
        "error": error,
        "wall_elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "telemetry": telemetry,
    }


async def main() -> int:
    artifact_dir = Path(__file__).resolve().parent / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    log_path = artifact_dir / "reasoning_pipeline_v3.log"
    result_path = artifact_dir / "reasoning_pipeline_v3_results.json"

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)

    engine = LunaEngine()
    results: dict[str, Any] = {}

    if "--complex-only" in sys.argv:
        scenario = ScenarioContext()
        scenario.update(OLD_CONTEXT)
        engine.scenario_contexts["v3-complex"] = scenario
        result = await collect(engine, COMPLEX_FIXTURE, "v3-complex")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if "--loop-only" in sys.argv:
        scenario = ScenarioContext()
        scenario.update(OLD_CONTEXT)
        engine.scenario_contexts["v3-loop"] = scenario
        result = await collect(engine, "e agora?", "v3-loop")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if "--deep-only" in sys.argv:
        result = await collect(engine, DEEP_FIXTURE, "v3-deep")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    results["F_FAST"] = await collect(engine, "olá", "v3-fast")

    complex_attempts: list[dict[str, Any]] = []
    complex_result: dict[str, Any] | None = None
    for attempt in range(1, 4):
        session_id = f"v3-complex-{attempt}"
        complex_scenario = ScenarioContext()
        complex_scenario.update(OLD_CONTEXT)
        engine.scenario_contexts[session_id] = complex_scenario
        candidate = await collect(engine, COMPLEX_FIXTURE, session_id)
        complex_attempts.append({
            "attempt": attempt,
            "session_id": session_id,
            "response_source": candidate["metadata"]["response_source"],
            "request_count": candidate["metadata"]["request_count"],
            "validation_reasons": candidate["metadata"].get("validation_reasons", []),
            "error": candidate["error"],
        })
        complex_result = candidate
        if candidate["metadata"]["response_source"] == "model" and candidate["response"]:
            break
    assert complex_result is not None
    complex_result["golden_attempts"] = complex_attempts
    results["B_C_G_ANALYZE_COMPLEX"] = complex_result

    loop_scenario = ScenarioContext()
    loop_scenario.update(OLD_CONTEXT)
    engine.scenario_contexts["v3-loop"] = loop_scenario
    results["D_ANTI_LOOP"] = await collect(engine, "e agora?", "v3-loop")

    results["H_DEEP"] = await collect(engine, DEEP_FIXTURE, "v3-deep")
    reasoning_probes = {
        effort: await probe_reasoning_effort(engine, effort)
        for effort in ("none", "low", "medium")
    }

    retest_scenario = ScenarioContext()
    retest_scenario.update(OLD_CONTEXT)
    retest_validation = validate_model_response(
        message="Repita o baseline porque estou medindo uma resposta variável de cache.",
        response="```bash\ncurl -i http://127.0.0.1:8080/\n```",
        scenario=retest_scenario,
        evidence_delta_count=0,
    )

    complex_result = results["B_C_G_ANALYZE_COMPLEX"]
    complex_meta = complex_result["metadata"]
    complex_text = complex_result["response"].casefold()
    loop_text = results["D_ANTI_LOOP"]["response"]
    loop_fp = action_fingerprint(loop_text)
    root_fp = action_fingerprint("curl -i http://127.0.0.1:8080/")

    log_text = log_path.read_text(encoding="utf-8")
    checks = {
        "B_llm_required": complex_meta["llm_required"] is True,
        "B_llm_called": complex_meta["llm_called"] is True,
        "B_response_source_model": complex_meta["response_source"] == "model",
        "B_provider_ollama": complex_meta["provider"] == "ollama",
        "B_no_root_regression": action_fingerprint(complex_result["response"]) != root_fp,
        "C_current_endpoint_used": "/api/admin/users" in complex_text,
        "C_observed_user_token_used": "test_token_123" in complex_text,
        "C_client_side_limit": any(
            marker in complex_text for marker in ("backend", "servidor", "server-side")
        ) and any(
            marker in complex_text
            for marker in (
                "não prova", "nao prova", "não confirma", "nao confirma",
                "não garante", "nao garante", "apenas visual", "puramente local",
                "client-side", "interface visual", "frontend", "navegador",
            )
        ),
        "D_same_action_not_repeated": (
            results["D_ANTI_LOOP"]["metadata"]["llm_called"] is True
            and loop_fp != root_fp
            and (
                bool(results["D_ANTI_LOOP"]["response"])
                or results["D_ANTI_LOOP"]["metadata"]["response_source"] == "system_error"
            )
        ),
        "E_retest_allowed": retest_validation.valid and retest_validation.loop_guard == "retest_allowed",
        "F_fast_none": results["F_FAST"]["metadata"]["route"] == "FAST"
        and results["F_FAST"]["metadata"]["reasoning_effort"] == "none",
        "G_analyze_low": complex_meta["route"] == "ANALYZE"
        and complex_meta["reasoning_effort"] == "low",
        "H_deep_medium": results["H_DEEP"]["metadata"]["route"] == "DEEP"
        and results["H_DEEP"]["metadata"]["reasoning_effort"] == "medium"
        and results["H_DEEP"]["metadata"]["llm_called"] is True,
        "I_none_accepted": not reasoning_probes["none"]["error"],
        "I_low_accepted": not reasoning_probes["low"]["error"],
        "I_medium_accepted": not reasoning_probes["medium"]["error"],
        "J_real_stream_chunks": all(
            result["metadata"]["chunks"] > 1
            for result in results.values()
        ),
        "J_no_reasoning_event": all(
            "reasoning" not in result["event_types"]
            for result in results.values()
        ),
        "B_logs_start_done": "ollama.request.start" in log_text
        and "ollama.request.done" in log_text,
        "B_secret_not_logged": "TEST_TOKEN_123" not in log_text,
    }
    output = {
        "model": engine.config["default_model"],
        "zero_cloud_mode": engine.config["zero_cloud_mode"],
        "supervised_mode": not engine.config["tool_execution_enabled"],
        "checks": checks,
        "E_REPRODUCIBILITY_EXCEPTION": {
            "valid": retest_validation.valid,
            "loop_guard": retest_validation.loop_guard,
            "fingerprint": retest_validation.proposed_action_fingerprint,
        },
        "I_REASONING_EFFORT_PROBES": reasoning_probes,
        "results": results,
    }
    result_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(asyncio.run(main()))
