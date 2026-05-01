#!/usr/bin/env python3
"""
smoke_bridge.py — Smoke tests para a bridge local (local_bridge.py).

Uso:
    python scripts/smoke_bridge.py [BRIDGE_URL]

    BRIDGE_URL default: http://127.0.0.1:8765
"""
import sys
import json
import urllib.request
import urllib.error

BRIDGE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765").rstrip("/")

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"

results = []


def req(method, path, body=None):
    url = BRIDGE_URL + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if data else {}
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
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
print(f"  Luna Agent — Smoke Bridge")
print(f"  {BRIDGE_URL}")
print(f"{'─'*56}\n")

# ── 1. HEALTH ──────────────────────────────────────────────
print("[ /health ]")
s, d = req("GET", "/health")
bridge_alive = s == 200
check("GET /health → 200", s, d, expect_status=200)
if not bridge_alive:
    print(f"\n  \033[91m! Bridge offline. Inicie com:\033[0m")
    print(f"  python local_bridge.py")
    print(f"\n{'─'*56}")
    sys.exit(1)

check("success=true", s, d, key_path="success", expect_val=True)
check("bridge=local", s, d, key_path="response.bridge", expect_val="local")
safe_dirs = d.get("response", {}).get("safe_base_dirs", [])
print(f"    safe_base_dirs = {safe_dirs}")

# ── 2. SCREEN STATUS ───────────────────────────────────────
print("\n[ /screen/status ]")
s, d = req("GET", "/screen/status")
check("GET /screen/status → 200", s, d)
check("success=true", s, d, key_path="success", expect_val=True)
if s == 200:
    r = d.get("response", {})
    print(f"    available = {r.get('available')}")
    print(f"    backend   = {r.get('backend')}")
    print(f"    screens   = {r.get('screens')}")

# ── 3. SCREEN CAPTURE ──────────────────────────────────────
print("\n[ /screen/capture ]")
s, d = req("POST", "/screen/capture", {"monitor": 1, "max_width": 640})
cap_ok, _ = check("POST /screen/capture → 200", s, d)
if cap_ok:
    r = d.get("response", {})
    b64 = r.get("image_b64", "")
    check("image_b64 presente", s, d, key_path="response.image_b64")
    print(f"    mime      = {r.get('mime')}")
    print(f"    size_kb   = {r.get('size_kb')}")
    print(f"    width     = {r.get('width')}")
    print(f"    height    = {r.get('height')}")
    print(f"    backend   = {r.get('backend')}")
    print(f"    b64_len   = {len(b64)} chars")
else:
    print(f"    detail = {d.get('detail')}")

# ── 4. LIST DIR (safe dir) ─────────────────────────────────
print("\n[ /list_dir ]")
import os
safe_dir = safe_dirs[0] if safe_dirs else "/mnt/d"
s, d = req("POST", "/list_dir", {"path": safe_dir})
ok, _ = check(f"POST /list_dir ({safe_dir}) → 200", s, d)
if ok:
    items = d.get("response", {}).get("items", [])
    print(f"    items = {len(items)}")

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
