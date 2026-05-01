#!/usr/bin/env python3
"""
Luna Worker — local agent that connects outbound to Luna Brain (VPS).

Usage:
    python luna_worker.py                  # reads worker_config.json
    python luna_worker.py --config path/to/config.json

The Worker:
  - registers with Brain on startup
  - sends heartbeat every 30s
  - polls for tasks every POLL_INTERVAL seconds
  - executes tasks locally according to local policy
  - posts results back to Brain
  - never requires inbound connections or SSH tunnels
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import platform
import shlex
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

try:
    import httpx
    _HTTPX = True
except ImportError:
    import urllib.request
    import urllib.error
    _HTTPX = False

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_CONFIG_PATH = Path(__file__).parent / "worker_config.json"

DEFAULT_CONFIG = {
    "worker_id": "",                        # auto-generated if empty
    "api_base": "http://localhost:8000",    # Luna Brain URL
    "api_token": "",                        # optional auth token
    "allowed_dirs": [],                     # empty = deny all; use ["D:/", "C:/Dev"] etc.
    "allowed_commands": [                   # prefix-based allowlist
        "ls", "pwd", "dir",
        "cat ", "type ",
        "python ", "python3 ", "py ",
        "node ", "npm ", "npx ",
        "git status", "git diff", "git log",
        "pytest", "pip list",
    ],
    "blocked_patterns": [                   # deny these anywhere in command
        "&&", "||", ";", "|", ">", "<", "$(", "`",
        " rm ", " del ", " rmdir ", " sudo ",
        " shutdown", " reboot",
        " curl http", " wget http",
        " format ", " mkfs",
    ],
    "require_approval_for_write": True,
    "require_approval_for_command": True,
    "poll_interval": 5,
    "heartbeat_interval": 30,
    "capture_enabled": True,
    "max_file_size_kb": 512,
}


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            cfg = {**DEFAULT_CONFIG, **data}
        except Exception as e:
            print(f"[worker] Aviso: não foi possível ler {path}: {e}. Usando padrões.")
            cfg = dict(DEFAULT_CONFIG)
    else:
        cfg = dict(DEFAULT_CONFIG)

    # Auto-generate worker_id if not set
    if not cfg.get("worker_id"):
        hostname = platform.node() or "local"
        cfg["worker_id"] = f"worker-{hostname}-{uuid4().hex[:6]}"
        # Persist it
        try:
            path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"[worker] ID gerado: {cfg['worker_id']} (salvo em {path})")
        except Exception:
            pass

    return cfg


def save_config(cfg: dict, path: Path = DEFAULT_CONFIG_PATH) -> None:
    try:
        path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[worker] Aviso: não foi possível salvar config: {e}")


# ── HTTP client ───────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _headers(token: str) -> dict:
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def http_get(url: str, token: str = "", timeout: float = 10) -> Optional[dict]:
    try:
        if _HTTPX:
            r = httpx.get(url, headers=_headers(token), timeout=timeout)
            if r.status_code == 200:
                return r.json()
            return None
        else:
            req = urllib.request.Request(url, headers=_headers(token))
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
    except Exception as e:
        return None


def http_post(url: str, body: dict, token: str = "", timeout: float = 15) -> Optional[dict]:
    try:
        data = json.dumps(body).encode("utf-8")
        if _HTTPX:
            r = httpx.post(url, content=data, headers=_headers(token), timeout=timeout)
            if r.status_code == 200:
                return r.json()
            print(f"[worker] POST {url} → {r.status_code}: {r.text[:200]}")
            return None
        else:
            req = urllib.request.Request(url, data=data, headers=_headers(token), method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
    except Exception as e:
        return None


# ── Local policy ──────────────────────────────────────────────────────────────

def is_path_allowed(path_str: str, allowed_dirs: list[str]) -> bool:
    if not allowed_dirs:
        return False
    try:
        target = Path(path_str).resolve()
        for d in allowed_dirs:
            try:
                base = Path(d).resolve()
                if target == base or str(target).startswith(str(base) + os.sep):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def is_command_allowed(cmd: str, cfg: dict) -> tuple[bool, str]:
    cmd_lower = cmd.lower().strip()

    # Check blocked patterns first
    for pat in cfg.get("blocked_patterns", []):
        if pat in cmd:
            return False, f"comando contém padrão bloqueado: '{pat}'"

    # Check allowlist
    allowed_prefixes = cfg.get("allowed_commands", [])
    for prefix in allowed_prefixes:
        if cmd_lower.startswith(prefix.lower()):
            return True, ""

    return False, f"comando não está na lista de comandos permitidos"


def ensure_path(path_str: str, cfg: dict) -> tuple[bool, Path, str]:
    try:
        p = Path(path_str).resolve()
    except Exception as e:
        return False, Path("."), f"path inválido: {e}"

    if not is_path_allowed(str(p), cfg.get("allowed_dirs", [])):
        return False, p, f"path '{p}' fora dos diretórios permitidos: {cfg.get('allowed_dirs', [])}"

    return True, p, ""


# ── Task execution ────────────────────────────────────────────────────────────

def exec_list_dir(args: dict, cfg: dict) -> tuple[bool, dict, str]:
    path_str = args.get("path", "")
    ok, p, err = ensure_path(path_str, cfg)
    if not ok:
        return False, {}, err
    if not p.exists() or not p.is_dir():
        return False, {}, f"diretório não encontrado: {p}"
    items = []
    try:
        for item in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            items.append({"name": item.name, "path": str(item), "is_dir": item.is_dir()})
        return True, {"path": str(p), "items": items}, ""
    except PermissionError as e:
        return False, {}, f"permissão negada: {e}"


def exec_read_file(args: dict, cfg: dict) -> tuple[bool, dict, str]:
    path_str = args.get("path", "")
    ok, p, err = ensure_path(path_str, cfg)
    if not ok:
        return False, {}, err
    if not p.exists() or not p.is_file():
        return False, {}, f"arquivo não encontrado: {p}"
    max_kb = cfg.get("max_file_size_kb", 512)
    size_kb = p.stat().st_size / 1024
    if size_kb > max_kb:
        return False, {}, f"arquivo muito grande: {size_kb:.1f} KB (limite: {max_kb} KB)"
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        return True, {"path": str(p), "content": content}, ""
    except Exception as e:
        return False, {}, str(e)


def exec_apply_patch(args: dict, cfg: dict) -> tuple[bool, dict, str]:
    if cfg.get("require_approval_for_write", True):
        return False, {}, "escrita requer aprovação (require_approval_for_write=true)"
    path_str = args.get("path", "")
    old = args.get("old", "")
    new = args.get("new", "")
    ok, p, err = ensure_path(path_str, cfg)
    if not ok:
        return False, {}, err
    if not p.exists() or not p.is_file():
        return False, {}, f"arquivo não encontrado: {p}"
    try:
        content = p.read_text(encoding="utf-8")
        if old not in content:
            return False, {}, "trecho 'old' não encontrado no arquivo"
        backup = Path(str(p) + ".bak")
        backup.write_text(content, encoding="utf-8")
        p.write_text(content.replace(old, new, 1), encoding="utf-8")
        return True, {"path": str(p), "backup": str(backup), "message": "patch aplicado"}, ""
    except Exception as e:
        return False, {}, str(e)


def exec_run_command(args: dict, cfg: dict) -> tuple[bool, dict, str, str, str]:
    if cfg.get("require_approval_for_command", True):
        return False, {}, "comando requer aprovação (require_approval_for_command=true)", "", ""
    cmd = args.get("cmd", "")
    cwd_str = args.get("cwd", "")
    allowed, reason = is_command_allowed(cmd, cfg)
    if not allowed:
        return False, {}, reason, "", ""
    # Validate cwd
    if cwd_str:
        ok, cwd_path, err = ensure_path(cwd_str, cfg)
        if not ok:
            return False, {}, err, "", ""
    else:
        cwd_path = None
    try:
        argv = shlex.split(cmd)
        result = subprocess.run(
            argv,
            cwd=str(cwd_path) if cwd_path else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        ok = result.returncode == 0
        return ok, {
            "ok": ok,
            "cmd": cmd,
            "cwd": str(cwd_path) if cwd_path else "",
            "returncode": result.returncode,
        }, "" if ok else result.stderr[:500], result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, {}, "timeout: comando demorou mais de 60s", "", ""
    except Exception as e:
        return False, {}, str(e), "", ""


def exec_screen_status(args: dict, cfg: dict) -> tuple[bool, dict, str]:
    if not cfg.get("capture_enabled", True):
        return False, {}, "captura de tela desabilitada na config"
    try:
        try:
            import mss
            with mss.mss() as sct:
                monitors = [{"id": i, **m} for i, m in enumerate(sct.monitors)]
            return True, {"available": True, "backend": "mss", "monitors": monitors, "ts": _ts()}, ""
        except ImportError:
            pass
        try:
            from PIL import ImageGrab
            return True, {"available": True, "backend": "pillow", "monitors": [{"id": 1}], "ts": _ts()}, ""
        except ImportError:
            pass
        return True, {"available": False, "backend": "none", "ts": _ts()}, ""
    except Exception as e:
        return False, {}, str(e)


def exec_screen_capture(args: dict, cfg: dict) -> tuple[bool, dict, str]:
    if not cfg.get("capture_enabled", True):
        return False, {}, "captura de tela desabilitada na config"
    monitor_idx = args.get("monitor", 1)
    max_width = min(args.get("max_width", 1280), 1920)
    try:
        try:
            import mss
            from PIL import Image
            with mss.mss() as sct:
                monitors = sct.monitors
                idx = monitor_idx if 0 < monitor_idx < len(monitors) else 1
                raw = sct.grab(monitors[idx])
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            backend = "mss"
        except ImportError:
            from PIL import Image, ImageGrab
            img = ImageGrab.grab()
            backend = "pillow"

        w, h = img.size
        if w > max_width:
            ratio = max_width / w
            img = img.resize((max_width, int(h * ratio)), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        size_kb = round(len(buf.getvalue()) / 1024, 1)

        return True, {
            "image_b64": b64,
            "mime": "image/jpeg",
            "width": img.size[0],
            "height": img.size[1],
            "size_kb": size_kb,
            "backend": backend,
            "monitor": monitor_idx,
            "ts": _ts(),
        }, ""
    except Exception as e:
        return False, {}, f"captura falhou: {e}"


def execute_task(task: dict, cfg: dict) -> tuple[bool, dict, str, str, str]:
    """Dispatch task to appropriate executor. Returns (ok, result, error, stdout, stderr)."""
    task_type = task.get("type", "")
    args = task.get("args", {})

    # O Brain já decide aprovação. Se a task chegou aqui despachada,
    # não devemos rebloqueá-la localmente por política genérica.
    task_cfg = dict(cfg)
    if task.get("requires_approval", False) is False:
        task_cfg["require_approval_for_write"] = False
        task_cfg["require_approval_for_command"] = False

    if task_type == "list_dir":
        ok, result, error = exec_list_dir(args, task_cfg)
        return ok, result, error, "", ""
    elif task_type in ("read_file", "read_log"):
        ok, result, error = exec_read_file(args, task_cfg)
        return ok, result, error, "", ""
    elif task_type == "apply_patch":
        ok, result, error = exec_apply_patch(args, task_cfg)
        return ok, result, error, "", ""
    elif task_type == "run_command":
        return exec_run_command(args, task_cfg)
    elif task_type == "screen_status":
        ok, result, error = exec_screen_status(args, task_cfg)
        return ok, result, error, "", ""
    elif task_type == "screen_capture":
        ok, result, error = exec_screen_capture(args, task_cfg)
        return ok, result, error, "", ""
    else:
        return False, {}, f"tipo de tarefa desconhecido: '{task_type}'", "", ""


# ── Worker core ───────────────────────────────────────────────────────────────

class LunaWorker:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.worker_id = cfg["worker_id"]
        self.api_base = cfg["api_base"].rstrip("/")
        self.token = cfg.get("api_token", "")
        self.poll_interval = int(cfg.get("poll_interval", 5))
        self.heartbeat_interval = int(cfg.get("heartbeat_interval", 30))
        self._running = False
        self._hb_thread: Optional[threading.Thread] = None
        self._active_task: Optional[str] = None

    def _url(self, path: str) -> str:
        return f"{self.api_base}{path}"

    def register(self) -> bool:
        print(f"[worker] Registrando no Brain: {self.api_base} ...")
        payload = {
            "worker_id": self.worker_id,
            "hostname": platform.node(),
            "capabilities": self._capabilities(),
            "allowed_dirs": self.cfg.get("allowed_dirs", []),
            "token": self.token,
            "version": "2.0",
        }
        resp = http_post(self._url("/worker/register"), payload, self.token)
        if resp and resp.get("success"):
            scope = resp.get("response", {}).get("scope", {})
            print(f"[worker] Registrado. Scope recebido do Brain:")
            print(f"         allowed_tools: {scope.get('allowed_tools', [])}")
            print(f"         require_write_approval: {scope.get('require_approval_for_write')}")
            print(f"         require_cmd_approval:   {scope.get('require_approval_for_command')}")
            return True
        print(f"[worker] FALHA ao registrar. Brain disponível em {self.api_base}?")
        return False

    def _capabilities(self) -> list[str]:
        caps = ["list_dir", "read_file", "apply_patch", "run_command"]
        try:
            import mss
            caps.append("screen_capture")
            caps.append("screen_status")
        except ImportError:
            try:
                from PIL import ImageGrab
                caps.append("screen_capture")
                caps.append("screen_status")
            except ImportError:
                pass
        return caps

    def heartbeat(self) -> bool:
        payload = {
            "worker_id": self.worker_id,
            "status": "online",
            "active_task": self._active_task,
        }
        resp = http_post(self._url("/worker/heartbeat"), payload, self.token, timeout=8)
        return bool(resp and resp.get("success"))

    def _heartbeat_loop(self) -> None:
        while self._running:
            try:
                ok = self.heartbeat()
                if not ok:
                    print("[worker] Heartbeat falhou — tentando re-registrar no Brain...")
                    if self.register():
                        print("[worker] Re-registro OK após falha de heartbeat.")
                    else:
                        print(f"[worker] Re-registro falhou — nova tentativa em {self.heartbeat_interval}s")
            except Exception as e:
                print(f"[worker] Erro no heartbeat: {e}")
            time.sleep(self.heartbeat_interval)

    def poll_and_execute(self) -> None:
        resp = http_get(
            self._url(f"/worker/tasks/next?worker_id={self.worker_id}"),
            self.token,
        )
        if not resp or not resp.get("success"):
            return

        task = resp.get("response")
        if not task:
            return  # No pending tasks

        task_id = task.get("task_id", "?")
        task_type = task.get("type", "?")
        self._active_task = task_id

        print(f"[worker] Tarefa recebida: {task_id} | tipo: {task_type} | risco: {task.get('risk', '?')}")

        # Execute
        ok, result, error, stdout, stderr = execute_task(task, self.cfg)

        status = "OK" if ok else "FALHA"
        print(f"[worker] {status}: {task_id} | {error or 'executado'}")

        # Post result
        result_payload = {
            "task_id": task_id,
            "ok": ok,
            "result": result,
            "error": error,
            "stdout": stdout[:2000] if stdout else "",
            "stderr": stderr[:1000] if stderr else "",
            "finished_at": _ts(),
        }
        resp2 = http_post(
            self._url(f"/worker/tasks/result/{task_id}"),
            result_payload,
            self.token,
        )
        if not (resp2 and resp2.get("success")):
            print(f"[worker] Aviso: falha ao enviar resultado de {task_id} para o Brain")

        self._active_task = None

    def run(self) -> None:
        print(f"[worker] ══════════════════════════════════════════")
        print(f"[worker] Luna Worker v2.0  |  {self.worker_id}")
        print(f"[worker] Brain: {self.api_base}")
        print(f"[worker] Dirs permitidos: {self.cfg.get('allowed_dirs', [])}")
        print(f"[worker] Polling a cada {self.poll_interval}s | Heartbeat a cada {self.heartbeat_interval}s")
        print(f"[worker] ══════════════════════════════════════════")

        if not self.cfg.get("allowed_dirs"):
            print("[worker] AVISO: allowed_dirs está vazio — nenhum path local será aceito!")
            print("[worker]        Configure allowed_dirs em worker_config.json")

        if not self.register():
            print("[worker] Tentando reconexão em 15s...")
            time.sleep(15)
            if not self.register():
                print("[worker] Não foi possível registrar. Encerrando.")
                sys.exit(1)

        self._running = True
        self._hb_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="luna-hb"
        )
        self._hb_thread.start()
        print(f"[worker] Online. Aguardando tarefas...")

        try:
            while self._running:
                try:
                    self.poll_and_execute()
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"[worker] Erro no ciclo de poll: {e}")
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
            print("[worker] Encerrando.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Luna Worker — agente local outbound")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Caminho para worker_config.json")
    parser.add_argument("--brain", help="URL do Brain (sobrescreve config)")
    parser.add_argument("--dirs", nargs="+", help="Diretórios permitidos (sobrescreve config)")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))

    if args.brain:
        cfg["api_base"] = args.brain
    if args.dirs:
        cfg["allowed_dirs"] = args.dirs

    worker = LunaWorker(cfg)
    worker.run()


if __name__ == "__main__":
    main()
