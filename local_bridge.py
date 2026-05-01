from __future__ import annotations

from pathlib import Path
import base64
import io
import os
import shlex
import subprocess
import difflib
import threading
import time
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
try:
    import httpx as _httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

# ── Optional screen capture libraries ──────────────────────────
try:
    import mss
    from PIL import Image
    _MSS_AVAILABLE = True
except ImportError:
    _MSS_AVAILABLE = False

if not _MSS_AVAILABLE:
    try:
        from PIL import Image, ImageGrab
        _PIL_AVAILABLE = True
    except ImportError:
        _PIL_AVAILABLE = False
else:
    _PIL_AVAILABLE = False  # mss takes priority

BRIDGE_PORT = 8765
MAX_CAPTURE_WIDTH = 1280
_last_capture_meta: dict | None = None

_VPS_BASE = os.getenv("LUNA_VPS_URL", "http://localhost:8000")
_POLL_INTERVAL = int(os.getenv("LUNA_POLL_INTERVAL", "5"))
_poll_thread: threading.Thread | None = None
_poll_running = False

APP_ORIGINS = [
    "http://209.200.246.165:8000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

SAFE_BASE_DIRS = [
    Path("/mnt/c/Dev").resolve(),
    Path("/mnt/d").resolve(),
]

LOCAL_BLOCKED_COMMAND_PATTERNS = [
    "&&",
    "||",
    ";",
    "|",
    ">",
    "<",
    "$(",
    "`",
    " rm ",
    " del ",
    " rmdir ",
    " sudo ",
    " shutdown",
    " reboot",
    " curl http",
    " wget http",
]

LOCAL_ALLOWED_COMMAND_PREFIXES = [
    "ls",
    "pwd",
    "cat ",
    "python ",
    "python3 ",
    "node ",
    "npm ",
    "npx ",
    "git status",
    "git diff",
    "git log",
]

app = FastAPI(title="Luna Local Bridge", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=APP_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_private_network=True,
)

@app.options("/{full_path:path}")
def preflight(full_path: str, request: Request):
    origin = request.headers.get("origin", "")
    headers = {
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": request.headers.get("access-control-request-headers", "*"),
    }
    if origin in APP_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin, Access-Control-Request-Private-Network"
    if request.headers.get("access-control-request-private-network") == "true":
        headers["Access-Control-Allow-Private-Network"] = "true"
    return Response(status_code=204, headers=headers)


class ListDirRequest(BaseModel):
    path: str

class ReadFileRequest(BaseModel):
    path: str

class PatchPreviewRequest(BaseModel):
    path: str
    old: str
    new: str

class CommandRequest(BaseModel):
    cmd: str
    cwd: str

class CaptureRequest(BaseModel):
    monitor: int = 1       # 1-based monitor index (0 = all monitors combined)
    max_width: int = 1280  # cap resolution; never exceeds MAX_CAPTURE_WIDTH

def normalize_path(path: str) -> Path:
    return Path(path).expanduser().resolve()

def is_path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

def ensure_local_path_allowed(path: str) -> Path:
    actual = normalize_path(path)
    if not any(actual == base or is_path_within(actual, base) for base in SAFE_BASE_DIRS):
        raise PermissionError(f"path fora da política local: {actual}")
    return actual

def build_local_patch_preview(path: str, old: str, new: str) -> dict:
    actual = ensure_local_path_allowed(path)

    if not actual.exists():
        raise FileNotFoundError(f"arquivo não existe: {actual}")
    if not actual.is_file():
        raise ValueError(f"path não é arquivo: {actual}")

    current = actual.read_text(encoding="utf-8")
    occurrences = current.count(old)

    if occurrences == 0:
        raise ValueError("trecho antigo não encontrado no arquivo")
    if occurrences > 1:
        raise ValueError("trecho antigo ambíguo: aparece múltiplas vezes no arquivo")

    updated = current.replace(old, new, 1)
    diff = "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=str(actual),
            tofile=f"{actual}.patched",
            n=3,
        )
    )

    return {
        "path": str(actual),
        "occurrences": occurrences,
        "diff": diff,
        "updated_content": updated,
    }

def is_local_command_allowed(cmd: str) -> bool:
    text = f" {cmd.strip().lower()} "
    for blocked in LOCAL_BLOCKED_COMMAND_PATTERNS:
        if blocked in text:
            return False
    cmd_strip = cmd.strip()
    return any(cmd_strip.startswith(prefix) for prefix in LOCAL_ALLOWED_COMMAND_PREFIXES)

def build_local_command_preview(cmd: str, cwd: str) -> dict:
    if not is_local_command_allowed(cmd):
        raise ValueError(f"comando bloqueado pela política local: {cmd}")

    actual_cwd = ensure_local_path_allowed(cwd)
    if not actual_cwd.exists() or not actual_cwd.is_dir():
        raise ValueError(f"cwd inválido: {actual_cwd}")

    try:
        argv = shlex.split(cmd)
    except ValueError as e:
        raise ValueError(f"comando inválido: {e}")

    if not argv:
        raise ValueError("comando vazio após parse")

    return {
        "cmd": cmd,
        "argv": argv,
        "cwd": str(actual_cwd),
    }

@app.get("/health")
def health():
    return {
        "success": True,
        "response": {
            "status": "ok",
            "bridge": "local",
            "safe_base_dirs": [str(p) for p in SAFE_BASE_DIRS],
        },
    }

@app.post("/read_file")
def read_file(payload: ReadFileRequest):
    try:
        actual = ensure_local_path_allowed(payload.path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    if not actual.exists():
        raise HTTPException(status_code=404, detail=f"arquivo não existe: {actual}")
    if not actual.is_file():
        raise HTTPException(status_code=400, detail=f"path não é arquivo: {actual}")

    return {
        "success": True,
        "response": {
            "path": str(actual),
            "content": actual.read_text(encoding="utf-8"),
        },
    }


@app.post("/preview_patch")
def preview_patch(payload: PatchPreviewRequest):
    try:
        preview = build_local_patch_preview(payload.path, payload.old, payload.new)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "success": True,
        "response": preview,
    }


@app.post("/preview_command")
def preview_command(payload: CommandRequest):
    try:
        preview = build_local_command_preview(payload.cmd, payload.cwd)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "success": True,
        "response": preview,
    }


@app.post("/run_command")
def run_command(payload: CommandRequest):
    try:
        preview = build_local_command_preview(payload.cmd, payload.cwd)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    completed = subprocess.run(
        preview["argv"],
        cwd=preview["cwd"],
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    return {
        "success": True,
        "response": {
            "ok": completed.returncode == 0,
            "cmd": preview["cmd"],
            "argv": preview["argv"],
            "cwd": preview["cwd"],
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        },
    }


@app.post("/apply_patch")
def apply_patch(payload: PatchPreviewRequest):
    try:
        preview = build_local_patch_preview(payload.path, payload.old, payload.new)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    actual = Path(preview["path"])
    current = actual.read_text(encoding="utf-8")
    backup = Path(str(actual) + ".bak")
    backup.write_text(current, encoding="utf-8")
    actual.write_text(preview["updated_content"], encoding="utf-8")

    return {
        "success": True,
        "response": {
            "path": str(actual),
            "backup": str(backup),
            "occurrences": preview["occurrences"],
            "diff": preview["diff"],
            "message": "patch local aplicado com backup",
        },
    }


@app.get("/screen/status")
def screen_status():
    """Retorna metadados dos monitores e info da última captura."""
    available = _MSS_AVAILABLE or _PIL_AVAILABLE
    backend = "mss" if _MSS_AVAILABLE else ("pillow" if _PIL_AVAILABLE else "unavailable")
    screens = []
    if _MSS_AVAILABLE:
        try:
            with mss.mss() as sct:
                for i, mon in enumerate(sct.monitors[1:], 1):
                    screens.append({"index": i, "width": mon["width"], "height": mon["height"]})
        except Exception:
            pass
    return {
        "success": True,
        "response": {
            "available": available,
            "backend": backend,
            "screens": screens,
            "last_capture": _last_capture_meta,
        },
    }


@app.post("/list_dir")
def list_dir(payload: ListDirRequest):
    try:
        actual = ensure_local_path_allowed(payload.path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    if not actual.exists():
        raise HTTPException(status_code=404, detail=f"path não existe: {actual}")
    if not actual.is_dir():
        raise HTTPException(status_code=400, detail=f"path não é diretório: {actual}")

    items = []
    for item in sorted(actual.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        items.append({
            "name": item.name,
            "path": str(item),
            "is_dir": item.is_dir(),
        })

    return {
        "success": True,
        "response": {
            "path": str(actual),
            "items": items,
        },
    }


@app.post("/screen/capture")
def screen_capture(payload: CaptureRequest):
    """Captura screenshot local, escala para max_width, retorna base64 JPEG + metadata."""
    global _last_capture_meta

    if not _MSS_AVAILABLE and not _PIL_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="screen capture indisponível: instale mss e Pillow (pip install mss Pillow)",
        )

    max_w = min(payload.max_width, MAX_CAPTURE_WIDTH)
    ts = datetime.now(timezone.utc).isoformat()

    try:
        if _MSS_AVAILABLE:
            with mss.mss() as sct:
                monitors = sct.monitors  # monitors[0] = todos combinados, monitors[1] = monitor 1
                idx = payload.monitor if 0 < payload.monitor < len(monitors) else 1
                raw = sct.grab(monitors[idx])
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        else:
            img = ImageGrab.grab()

        # Redimensionar se necessário
        w, h = img.size
        if w > max_w:
            ratio = max_w / w
            img = img.resize((max_w, int(h * ratio)), Image.LANCZOS)

        # Codificar como JPEG base64
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        size_kb = round(len(buf.getvalue()) / 1024, 1)

        meta = {
            "ts": ts,
            "width": img.size[0],
            "height": img.size[1],
            "size_kb": size_kb,
            "backend": "mss" if _MSS_AVAILABLE else "pillow",
            "monitor": payload.monitor,
        }
        _last_capture_meta = meta

        return {
            "success": True,
            "response": {
                "image_b64": b64,
                "mime": "image/jpeg",
                **meta,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"captura falhou: {e}")


def _execute_task(task: dict) -> tuple[bool, dict, str]:
    """Execute a task dispatched from the VPS task queue."""
    tool = task.get("tool", "")
    args = task.get("args", {})
    try:
        if tool == "list_dir":
            path = args.get("path", "")
            actual = ensure_local_path_allowed(path)
            if not actual.exists() or not actual.is_dir():
                return False, {}, f"path inválido: {actual}"
            items = []
            for item in sorted(actual.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                items.append({"name": item.name, "path": str(item), "is_dir": item.is_dir()})
            return True, {"path": str(actual), "items": items}, ""

        elif tool == "read_file":
            path = args.get("path", "")
            actual = ensure_local_path_allowed(path)
            if not actual.exists() or not actual.is_file():
                return False, {}, f"arquivo não encontrado: {actual}"
            return True, {"path": str(actual), "content": actual.read_text(encoding="utf-8")}, ""

        elif tool == "run_command":
            cmd = args.get("cmd", "")
            cwd = args.get("cwd", "")
            preview = build_local_command_preview(cmd, cwd)
            completed = subprocess.run(
                preview["argv"], cwd=preview["cwd"], shell=False,
                capture_output=True, text=True, encoding="utf-8",
            )
            ok = completed.returncode == 0
            return ok, {
                "ok": ok, "cmd": cmd, "cwd": cwd,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }, "" if ok else completed.stderr[:500]

        elif tool == "apply_patch":
            path = args.get("path", "")
            old = args.get("old", "")
            new = args.get("new", "")
            preview = build_local_patch_preview(path, old, new)
            actual = Path(preview["path"])
            current = actual.read_text(encoding="utf-8")
            backup = Path(str(actual) + ".bak")
            backup.write_text(current, encoding="utf-8")
            actual.write_text(preview["updated_content"], encoding="utf-8")
            return True, {
                "path": str(actual), "backup": str(backup),
                "message": "patch local aplicado com backup",
            }, ""

        else:
            return False, {}, f"tool desconhecida: {tool}"

    except (PermissionError, FileNotFoundError, ValueError) as exc:
        return False, {}, str(exc)
    except Exception as exc:
        return False, {}, f"erro inesperado: {exc}"


def _poll_loop() -> None:
    """Background thread: poll VPS for tasks and execute them locally."""
    global _poll_running
    while _poll_running:
        try:
            if not _HTTPX_AVAILABLE:
                time.sleep(_POLL_INTERVAL)
                continue

            import httpx
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{_VPS_BASE}/local/tasks/next")
                if resp.status_code != 200:
                    time.sleep(_POLL_INTERVAL)
                    continue
                data = resp.json()

            task = data.get("response")
            if not task:
                time.sleep(_POLL_INTERVAL)
                continue

            task_id = task.get("task_id", "")
            ok, result, error = _execute_task(task)

            import httpx
            with httpx.Client(timeout=10) as client:
                client.post(
                    f"{_VPS_BASE}/local/tasks/result/{task_id}",
                    json={"ok": ok, "result": result, "error": error},
                )
        except Exception:
            pass
        time.sleep(_POLL_INTERVAL)


@app.get("/poll/status")
def poll_status():
    """Returns current poll state (no auth required)."""
    return {
        "success": True,
        "response": {
            "polling": _poll_running,
            "vps_base": _VPS_BASE,
            "interval": _POLL_INTERVAL,
        },
    }


@app.post("/poll/start")
def poll_start():
    """Start the background polling thread."""
    global _poll_thread, _poll_running
    if _poll_running:
        return {"success": True, "response": {"status": "already_running"}}
    _poll_running = True
    _poll_thread = threading.Thread(target=_poll_loop, daemon=True, name="luna-poll")
    _poll_thread.start()
    return {"success": True, "response": {"status": "started", "vps_base": _VPS_BASE, "interval": _POLL_INTERVAL}}


@app.post("/poll/stop")
def poll_stop():
    """Stop the background polling thread."""
    global _poll_running
    _poll_running = False
    return {"success": True, "response": {"status": "stopped"}}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("local_bridge:app", host="127.0.0.1", port=BRIDGE_PORT, reload=False)