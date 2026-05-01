"""
local_proxy.py — VPS-side HTTP client for the local bridge.
Bridge reaches VPS via: ssh -L 8000:localhost:8000 -R 8765:localhost:8765 <vps>

The local bridge runs on the user's PC at port 8765.
The reverse SSH tunnel makes it reachable from VPS at http://127.0.0.1:8765.
"""
from __future__ import annotations

import httpx
from fastapi import HTTPException

BRIDGE_BASE = "http://127.0.0.1:8765"
_DEFAULT_TIMEOUT = 12


def _bridge_call(
    method: str,
    path: str,
    body: dict | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict:
    """Make an HTTP call to the local bridge. Raises HTTPException(503) if unreachable."""
    url = f"{BRIDGE_BASE}{path}"
    try:
        with httpx.Client(timeout=timeout) as client:
            if method.upper() == "GET":
                resp = client.get(url)
            else:
                resp = client.post(url, json=body or {})
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Bridge local indisponível: verifique túnel SSH (ssh -R 8765:localhost:8765 <vps>)",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=503,
            detail="Bridge local timeout: conexão estabelecida mas sem resposta",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Bridge retornou erro {exc.response.status_code}: {exc.response.text[:300]}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Erro ao contatar bridge: {exc}",
        )


def bridge_is_available() -> bool:
    """Calls /health with short timeout. Returns True/False, never raises."""
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{BRIDGE_BASE}/health")
        return resp.status_code == 200
    except Exception:
        return False


def bridge_health() -> dict:
    """Raw /health response from the bridge."""
    return _bridge_call("GET", "/health")


def bridge_screen_status() -> dict:
    """GET /screen/status from bridge."""
    return _bridge_call("GET", "/screen/status")


def bridge_screen_capture(monitor: int = 1, max_width: int = 1280) -> dict:
    """POST /screen/capture with monitor + max_width."""
    return _bridge_call("POST", "/screen/capture", {"monitor": monitor, "max_width": max_width})


def bridge_list_dir(path: str) -> dict:
    """List directory on local machine. Returns {ok, path, items}."""
    raw = _bridge_call("POST", "/list_dir", {"path": path})
    r = raw.get("response", {})
    return {
        "ok": raw.get("success", False),
        "path": r.get("path", path),
        "items": r.get("items", []),
    }


def bridge_read_file(path: str) -> dict:
    """Read file on local machine. Returns {ok, path, content}."""
    raw = _bridge_call("POST", "/read_file", {"path": path})
    r = raw.get("response", {})
    return {
        "ok": raw.get("success", False),
        "path": r.get("path", path),
        "content": r.get("content", ""),
    }


def bridge_preview_command(cmd: str, cwd: str) -> dict:
    """POST /preview_command. Returns raw bridge response."""
    return _bridge_call("POST", "/preview_command", {"cmd": cmd, "cwd": cwd})


def bridge_run_command(cmd: str, cwd: str) -> dict:
    """Run command on local machine. Returns {ok, cmd, cwd, returncode, stdout, stderr}."""
    raw = _bridge_call("POST", "/run_command", {"cmd": cmd, "cwd": cwd})
    r = raw.get("response", {})
    return {
        "ok": r.get("ok", raw.get("success", False)),
        "cmd": r.get("cmd", cmd),
        "cwd": r.get("cwd", cwd),
        "returncode": r.get("returncode", -1),
        "stdout": r.get("stdout", ""),
        "stderr": r.get("stderr", ""),
    }


def bridge_preview_patch(path: str, old: str, new: str) -> dict:
    """POST /preview_patch. Returns raw bridge response."""
    return _bridge_call("POST", "/preview_patch", {"path": path, "old": old, "new": new})


def bridge_apply_patch(path: str, old: str, new: str) -> dict:
    """Apply patch on local machine. Returns {ok, path, backup, message}."""
    raw = _bridge_call("POST", "/apply_patch", {"path": path, "old": old, "new": new})
    r = raw.get("response", {})
    return {
        "ok": raw.get("success", False),
        "path": r.get("path", path),
        "backup": r.get("backup", ""),
        "message": r.get("message", ""),
    }
