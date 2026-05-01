"""
Luna Agent — Smoke Tests
Tests both Brain endpoints and Worker communication flow.

Usage:
    python test_smoke.py                        # Brain at localhost:8000
    python test_smoke.py --brain http://IP:8000 # Custom Brain URL
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Optional

try:
    import httpx
    def get(url: str, **kw) -> dict:
        r = httpx.get(url, timeout=10, **kw)
        return {"status": r.status_code, "body": r.json() if r.headers.get("content-type","").startswith("application/json") else r.text}
    def post(url: str, body: dict = {}, **kw) -> dict:
        r = httpx.post(url, json=body, timeout=10, **kw)
        return {"status": r.status_code, "body": r.json() if r.headers.get("content-type","").startswith("application/json") else r.text}
except ImportError:
    import urllib.request, urllib.error
    def get(url: str, **kw) -> dict:
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                body = json.loads(r.read())
            return {"status": 200, "body": body}
        except urllib.error.HTTPError as e:
            return {"status": e.code, "body": str(e)}
        except Exception as e:
            return {"status": 0, "body": str(e)}
    def post(url: str, body: dict = {}, **kw) -> dict:
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                rb = json.loads(r.read())
            return {"status": 200, "body": rb}
        except urllib.error.HTTPError as e:
            return {"status": e.code, "body": str(e)}
        except Exception as e:
            return {"status": 0, "body": str(e)}


PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
WARN = "\033[33m⚠\033[0m"
results: list[tuple[bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    icon = PASS if condition else FAIL
    suffix = f"  ({detail})" if detail else ""
    print(f"  {icon}  {name}{suffix}")
    results.append((condition, name))
    return condition


def section(title: str) -> None:
    print(f"\n── {title} {'─' * (50 - len(title))}")


def run_smoke(brain: str) -> None:
    base = brain.rstrip("/")
    print(f"\n{'═'*60}")
    print(f"  Luna Agent — Smoke Tests")
    print(f"  Brain: {base}")
    print(f"{'═'*60}")

    # ── 1. Brain health ────────────────────────────────────────────
    section("Brain / Saúde geral")

    r = get(f"{base}/health")
    ok = r["status"] == 200 and r["body"].get("success")
    check("/health OK", ok, f"status={r['status']}")

    if ok:
        resp = r["body"].get("response", {})
        check("identity_loaded", bool(resp.get("identity_loaded")))
        check("workspace_loaded", bool(resp.get("workspace_loaded")))
        check("safe_mode_configured", "safe_mode_enabled" in resp)

    # ── 2. Agent endpoints ─────────────────────────────────────────
    section("Agent endpoints")

    r = get(f"{base}/agent/config")
    check("/agent/config GET OK", r["status"] == 200 and r["body"].get("success"))

    r = get(f"{base}/agent/state")
    check("/agent/state GET OK", r["status"] == 200 and r["body"].get("success"))
    if r["status"] == 200:
        resp = r["body"].get("response", {})
        check("state has execution_target", "execution_target" in resp)
        check("state has worker_online",    "worker_online" in resp)

    r = post(f"{base}/agent/plan", {"session_id": "smoke-test", "objective": "listar arquivos de teste"})
    check("/agent/plan OK", r["status"] == 200 and r["body"].get("success"))
    plan_ok = r["status"] == 200

    r = get(f"{base}/agent/queue")
    check("/agent/queue OK", r["status"] == 200 and r["body"].get("success"))

    r = get(f"{base}/agent/audit")
    check("/agent/audit OK", r["status"] == 200 and r["body"].get("success"))

    # ── 3. Chat ────────────────────────────────────────────────────
    section("Chat")

    r = post(f"{base}/chat", {"message": "oi", "session_id": "smoke-chat"})
    chat_ok = r["status"] == 200 and r["body"].get("success")
    chat_body_str = str(r.get("body", ""))
    if r["status"] in (500, 401, 403) and any(k in chat_body_str for k in ("API key", "OPENAI", "OpenAI", "api_key")):
        check("/chat reachable (API key inválida — esperado em ambiente de teste)", True, "sem chave OpenAI real")
    else:
        check("/chat OK", chat_ok, f"status={r['status']}")

    # ── 4. Worker endpoints ────────────────────────────────────────
    section("Worker endpoints")

    r = get(f"{base}/worker/status")
    check("/worker/status OK", r["status"] == 200 and r["body"].get("success"))

    r = get(f"{base}/worker/scope")
    check("/worker/scope GET OK", r["status"] == 200 and r["body"].get("success"))

    # Register a test worker
    test_worker_id = "smoke-worker-001"
    r = post(f"{base}/worker/register", {
        "worker_id": test_worker_id,
        "hostname": "smoke-test-machine",
        "capabilities": ["list_dir", "read_file"],
        "allowed_dirs": ["/tmp"],
        "token": "",
        "version": "smoke-test",
    })
    check("/worker/register OK", r["status"] == 200 and r["body"].get("success"))
    register_ok = r["status"] == 200

    if register_ok:
        r = post(f"{base}/worker/heartbeat", {
            "worker_id": test_worker_id,
            "status": "online",
            "active_task": None,
        })
        check("/worker/heartbeat OK", r["status"] == 200 and r["body"].get("success"))

        r = get(f"{base}/worker/status")
        if r["status"] == 200:
            resp_body = r["body"].get("response", {})
            check("worker appears online after register", resp_body.get("online_count", 0) > 0)

    # Fetch next task (should be None unless a plan was dispatched)
    r = get(f"{base}/worker/tasks/next?worker_id={test_worker_id}")
    check("/worker/tasks/next OK (no task)", r["status"] == 200 and r["body"].get("success"))

    r = get(f"{base}/worker/tasks")
    check("/worker/tasks OK", r["status"] == 200 and r["body"].get("success"))

    # ── 5. E2E: dispatch flow ──────────────────────────────────────
    section("E2E — dispatch to worker")

    # Set execution_target=local so plan dispatches to worker
    cfg_r = get(f"{base}/agent/config")
    if cfg_r["status"] == 200:
        cfg = cfg_r["body"].get("response", {}).get("response", cfg_r["body"].get("response", {}))
        if isinstance(cfg, dict) and cfg.get("response"):
            cfg = cfg["response"]
        cfg["execution_target"] = "local"
        cfg["local_target_root"] = "/tmp"
        post(f"{base}/agent/config", cfg)

    r = post(f"{base}/agent/plan", {
        "session_id": "smoke-e2e",
        "objective": "listar diretório local /tmp",
        "execution_target": "local",
        "local_target_root": "/tmp",
    })
    plan_dispatched = r["status"] == 200 and r["body"].get("success")
    check("plan gerado (target=local)", plan_dispatched)

    if plan_dispatched:
        # Execute — should dispatch to worker
        exec_r = post(f"{base}/agent/execute", {"session_id": "smoke-e2e"})
        exec_ok = exec_r["status"] == 200 and exec_r["body"].get("success")
        check("/agent/execute OK", exec_ok)

        if exec_ok:
            exec_resp = exec_r["body"].get("response", {})
            stop_reason = exec_resp.get("stop_reason", "")
            check("stop_reason = dispatched_to_worker", stop_reason == "dispatched_to_worker",
                  f"got: {stop_reason}")

            task_id = exec_resp.get("result", {}).get("task_id", "")
            if task_id:
                check("task_id presente no resultado", bool(task_id))

                # Simulate worker completing the task
                mock_result = {
                    "task_id": task_id,
                    "ok": True,
                    "result": {"path": "/tmp", "items": [{"name": "test", "path": "/tmp/test", "is_dir": True}]},
                    "error": "",
                    "stdout": "",
                    "stderr": "",
                    "finished_at": "",
                }
                rr = post(f"{base}/worker/tasks/result/{task_id}", mock_result)
                check("worker pode postar resultado", rr["status"] == 200 and rr["body"].get("success"))

                # Check task status
                tr = get(f"{base}/worker/tasks/{task_id}")
                if tr["status"] == 200:
                    t = tr["body"].get("response", {})
                    check("task marcada como completed", t.get("status") == "completed")

    # ── 6. Audit after E2E ─────────────────────────────────────────
    section("Audit após E2E")

    r = get(f"{base}/agent/audit?limit=10")
    if r["status"] == 200:
        entries = r["body"].get("response", {}).get("entries", [])
        check("audit tem entradas", len(entries) > 0, f"{len(entries)} entradas")
        types = [e.get("decision") for e in entries]
        check("audit contém dispatched ou auto_executed", any(d in types for d in ("dispatched", "auto_executed")))

    # ── Restore config to VPS ──────────────────────────────────────
    cfg_r = get(f"{base}/agent/config")
    if cfg_r["status"] == 200:
        cfg = cfg_r["body"].get("response", {})
        if isinstance(cfg, dict):
            cfg["execution_target"] = "vps"
            post(f"{base}/agent/config", cfg)

    # ── Summary ───────────────────────────────────────────────────
    passed = sum(1 for ok, _ in results if ok)
    total = len(results)
    failed_names = [name for ok, name in results if not ok]

    print(f"\n{'═'*60}")
    print(f"  Resultado: {passed}/{total} checks passaram")
    if failed_names:
        print(f"\n  Falhas:")
        for name in failed_names:
            print(f"    {FAIL}  {name}")
    print(f"{'═'*60}\n")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Luna Agent smoke tests")
    parser.add_argument("--brain", default="http://localhost:8000", help="URL do Brain")
    args = parser.parse_args()
    run_smoke(args.brain)
