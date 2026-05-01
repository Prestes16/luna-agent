#!/usr/bin/env python3
"""
smoke_backend.py — Smoke tests para o backend FastAPI da Luna Agent.

Uso:
    python scripts/smoke_backend.py [BASE_URL]

    BASE_URL default: http://localhost:8000
    Para VPS via tunel: http://localhost:8000
    Para VPS direto:    http://209.200.246.165:8000
"""
import sys
import json
import time
import urllib.request
import urllib.error

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
SKIP = "\033[93m~ SKIP\033[0m"

results = []


def req(method, path, body=None, expect_status=200):
    url = BASE_URL + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if data else {}
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read()
            status = resp.status
            return status, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"detail": raw.decode(errors="replace")}
    except Exception as e:
        return 0, {"detail": str(e)}


def check(name, status, data, expect_status=200, key_path=None, expect_val=None):
    ok = status == expect_status
    val_ok = True
    actual_val = None

    if ok and key_path:
        parts = key_path.split(".")
        node = data
        try:
            for p in parts:
                node = node[p]
            actual_val = node
        except (KeyError, TypeError):
            actual_val = None
            val_ok = False

        if expect_val is not None:
            val_ok = actual_val == expect_val

    passed = ok and val_ok
    icon = PASS if passed else FAIL
    detail = f"  HTTP {status}"
    if key_path:
        detail += f"  {key_path}={actual_val!r}"
    if not ok:
        detail += f"  (esperado {expect_status})"
    print(f"  {icon}  {name}{detail}")
    results.append((name, passed))
    return passed, data


print(f"\n{'─'*56}")
print(f"  Luna Agent — Smoke Backend")
print(f"  {BASE_URL}")
print(f"{'─'*56}\n")

# ── 1. HEALTH ──────────────────────────────────────────────
print("[ /health ]")
s, d = req("GET", "/health")
check("GET /health → 200", s, d, expect_status=200)
check("success=true", s, d, expect_status=200, key_path="success", expect_val=True)
check("status=ok", s, d, expect_status=200, key_path="response.status", expect_val="ok")

# ── 2. CHAT ────────────────────────────────────────────────
print("\n[ /chat ]")
s, d = req("POST", "/chat", {"message": "ping — teste de smoke"})
ok, _ = check("POST /chat → 200", s, d, expect_status=200)
check("success=true", s, d, expect_status=200, key_path="success", expect_val=True)
if ok:
    check("response.text existe", s, d, expect_status=200, key_path="response.text")
    check("session_id existe", s, d, expect_status=200, key_path="response.session_id")

# ── 3. AGENT STATE ─────────────────────────────────────────
print("\n[ /agent/state ]")
s, d = req("GET", "/agent/state")
check("GET /agent/state → 200", s, d, expect_status=200)
check("success=true", s, d, expect_status=200, key_path="success", expect_val=True)
check("response.config existe", s, d, expect_status=200, key_path="response.config")

# ── 4. AGENT PLAN ─────────────────────────────────────────
print("\n[ /agent/plan ]")
s, d = req("POST", "/agent/plan", {"objective": "listar arquivos do workspace", "mode": "propose"})
plan_ok, _ = check("POST /agent/plan → 200", s, d, expect_status=200)
check("success=true", s, d, expect_status=200, key_path="success", expect_val=True)
if plan_ok:
    plan = d.get("response", {})
    stop = plan.get("stop_reason", "")
    actions = plan.get("proposed_actions", [])
    print(f"    stop_reason = {stop!r}")
    print(f"    proposed_actions = {len(actions)}")
    if stop == "invalid_target_root":
        print(f"    \033[91m! target_root inválido — atualize agent_config.json\033[0m")

action_id = None
if plan_ok and d.get("response", {}).get("proposed_actions"):
    action_id = d["response"]["proposed_actions"][0]["action_id"]

# ── 5. AGENT QUEUE ─────────────────────────────────────────
print("\n[ /agent/queue ]")
s, d = req("GET", "/agent/queue")
check("GET /agent/queue → 200", s, d, expect_status=200)
check("success=true", s, d, expect_status=200, key_path="success", expect_val=True)

# ── 6. AGENT PREVIEW ──────────────────────────────────────
if action_id:
    print(f"\n[ /agent/preview/{action_id} ]")
    s, d = req("GET", f"/agent/preview/{action_id}")
    check(f"GET /agent/preview/{action_id} → 200", s, d, expect_status=200)
    check("success=true", s, d, expect_status=200, key_path="success", expect_val=True)

# ── 7. AGENT APPROVE ──────────────────────────────────────
if action_id:
    print(f"\n[ /agent/approve ]")
    s, d = req("POST", "/agent/approve", {"action_id": action_id, "approved": True, "session_id": ""})
    # Pode retornar 400 se ação não requer aprovação
    check("POST /agent/approve → 200 ou 400", s, d, expect_status=200 if s == 200 else 400)
    if s == 400:
        detail = d.get("detail", "")
        print(f"    → ação não requer aprovação ({detail}) — OK esperado")

# ── 8. AGENT AUDIT ─────────────────────────────────────────
print("\n[ /agent/audit ]")
s, d = req("GET", "/agent/audit?limit=10")
check("GET /agent/audit → 200", s, d, expect_status=200)
check("success=true", s, d, expect_status=200, key_path="success", expect_val=True)
if s == 200:
    entries = d.get("response", {}).get("entries", [])
    print(f"    entries = {len(entries)}")

# ── 9. WORKSPACES ──────────────────────────────────────────
print("\n[ /workspaces ]")
s, d = req("GET", "/workspaces")
check("GET /workspaces → 200", s, d, expect_status=200)
check("success=true", s, d, expect_status=200, key_path="success", expect_val=True)

# ── RESUMO ─────────────────────────────────────────────────
passed = sum(1 for _, ok in results if ok)
total  = len(results)
print(f"\n{'─'*56}")
print(f"  Resultado: {passed}/{total} checks passaram")
if passed < total:
    failed = [n for n, ok in results if not ok]
    print(f"  Falhas: {', '.join(failed)}")
print(f"{'─'*56}\n")
sys.exit(0 if passed == total else 1)
