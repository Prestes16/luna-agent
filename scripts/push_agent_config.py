#!/usr/bin/env python3
"""
push_agent_config.py — Empurra o agent_config correto para o backend via API.

Uso:
    python scripts/push_agent_config.py [BASE_URL]

    BASE_URL default: http://localhost:8000
    Para VPS via tunel SSH: http://localhost:8000
"""
import sys
import json
import urllib.request
import urllib.error

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")

NEW_CONFIG = {
    "enabled": True,
    "mode": "propose",
    "target_root": "/app",
    "safe_base_dirs": ["/app"],
    "allow_write": True,
    "allow_run_command": True,
    "max_actions_per_cycle": 1,
    "max_commands_per_cycle": 1,
    "require_approval_for_write": True,
    "require_approval_for_command": True,
}


def req(method, path, body=None):
    url = BASE_URL + path
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


print(f"\nPush agent config → {BASE_URL}\n")

# 1. Read current config
s, d = req("GET", "/agent/config")
if s != 200:
    print(f"✗ Não consegui ler config atual: HTTP {s}")
    print(f"  Verifique se o backend está rodando e o tunel SSH está ativo.")
    sys.exit(1)

current = d.get("response", {})
print(f"Config atual:")
print(f"  target_root   = {current.get('target_root')!r}")
print(f"  safe_base_dirs = {current.get('safe_base_dirs')}")

# 2. Push new config
s, d = req("POST", "/agent/config", NEW_CONFIG)
if s != 200:
    print(f"\n✗ Falha ao salvar config: HTTP {s}")
    print(f"  {d.get('detail', d)}")
    sys.exit(1)

saved = d.get("response", {})
print(f"\nConfig atualizada:")
print(f"  target_root   = {saved.get('target_root')!r}")
print(f"  safe_base_dirs = {saved.get('safe_base_dirs')}")
print(f"\n✓ Configuração salva com sucesso!")
print(f"  Agora /agent/plan deve funcionar corretamente.\n")
