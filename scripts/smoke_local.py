#!/usr/bin/env python3
"""
smoke_local.py — Smoke test for the full local execution chain via VPS proxy.

Tests:
  1. VPS /local/health         → bridge health via tunnel
  2. VPS /local/screen/status  → screen info via tunnel
  3. VPS /local/list_dir       → list /mnt/d via tunnel
  4. VPS /agent/plan (local)   → plan with execution_target=local
  5. VPS /agent/execute        → execute via bridge

Usage:
  python scripts/smoke_local.py [BASE_URL]
  python scripts/smoke_local.py http://localhost:8000
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
TIMEOUT = 15


def _ok(label: str, data: dict) -> bool:
    success = data.get("success", False)
    status = "PASS" if success else "FAIL"
    print(f"  [{status}] {label}")
    if not success:
        print(f"         detail: {data.get('detail', data.get('response', data))!r}")
    return success


def run() -> int:
    print(f"\n=== Luna Agent Local Chain Smoke Test ===")
    print(f"VPS base: {BASE_URL}")
    print(f"Started:  {datetime.now(timezone.utc).isoformat()}")
    print()

    failed = 0

    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:

        # 1. Bridge health via VPS proxy
        print("1. VPS /local/health — bridge health via tunnel")
        try:
            r = client.get("/local/health")
            data = r.json() if r.status_code != 503 else {"success": False, "detail": r.text[:200]}
            if not _ok("/local/health", data):
                failed += 1
                print("     (Is the SSH tunnel active and bridge running?)")
        except Exception as e:
            print(f"  [FAIL] /local/health — exception: {e}")
            failed += 1

        # 2. Screen status via VPS proxy
        print("\n2. VPS /local/screen/status — screen info via tunnel")
        try:
            r = client.get("/local/screen/status")
            data = r.json() if r.status_code != 503 else {"success": False, "detail": r.text[:200]}
            if _ok("/local/screen/status", data):
                resp = data.get("response", {})
                print(f"         backend={resp.get('backend')} screens={len(resp.get('screens', []))}")
            else:
                failed += 1
        except Exception as e:
            print(f"  [FAIL] /local/screen/status — exception: {e}")
            failed += 1

        # 3. List /mnt/d via VPS proxy
        print("\n3. VPS /local/list_dir — list /mnt/d via tunnel")
        try:
            r = client.post("/local/list_dir", json={"path": "/mnt/d"})
            data = r.json() if r.status_code not in (503, 403, 404) else {"success": False, "detail": r.text[:200]}
            if _ok("/local/list_dir {/mnt/d}", data):
                resp = data.get("response", {})
                items = resp.get("items", [])
                print(f"         {len(items)} items in /mnt/d")
            else:
                failed += 1
        except Exception as e:
            print(f"  [FAIL] /local/list_dir — exception: {e}")
            failed += 1

        # 4. Agent plan with execution_target=local
        print("\n4. VPS /agent/plan — plan with execution_target=local")
        try:
            r = client.post("/agent/plan", json={
                "objective": "Listar arquivos raiz local para inspeção",
                "mode": "propose",
                "execution_target": "local",
                "local_target_root": "/mnt/d",
            })
            data = r.json()
            if _ok("/agent/plan (local)", data):
                plan = data.get("response", {})
                actions = plan.get("proposed_actions", [])
                print(f"         session_id={plan.get('session_id')} actions={len(actions)}")
                if actions:
                    a = actions[0]
                    print(f"         first_action: tool={a.get('tool')} path={a.get('args',{}).get('path')}")
            else:
                failed += 1
        except Exception as e:
            print(f"  [FAIL] /agent/plan — exception: {e}")
            failed += 1

        # 5. Agent execute via bridge
        print("\n5. VPS /agent/execute — execute via bridge")
        try:
            r = client.post("/agent/execute", json={})
            data = r.json()
            if _ok("/agent/execute (local)", data):
                res = data.get("response", {})
                print(f"         ok={res.get('ok')} tool={res.get('tool')} stop={res.get('stop_reason')}")
                if res.get("result"):
                    items = res["result"].get("items", [])
                    print(f"         items_returned={len(items)}")
            else:
                failed += 1
                res = data.get("response", {})
                if res.get("stop_reason") == "bridge_unavailable":
                    print("         Bridge unreachable from VPS — check reverse tunnel")
        except Exception as e:
            print(f"  [FAIL] /agent/execute — exception: {e}")
            failed += 1

    print()
    print("=" * 42)
    total = 5
    passed = total - failed
    print(f"Results: {passed}/{total} passed", "✓" if failed == 0 else f"({failed} failed)")
    if failed == 0:
        print("Full local chain is operational.")
    else:
        print("Some checks failed. See above for details.")
        print("\nTroubleshooting:")
        print("  1. Start bridge:  python -m uvicorn local_bridge:app --host 127.0.0.1 --port 8765")
        print(f"  2. Open tunnel:   ./scripts/start_tunnel.sh user@{BASE_URL.split('//')[-1].split(':')[0]}")
        print("  3. Verify:        curl http://localhost:8000/local/health")
    print()
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(run())
