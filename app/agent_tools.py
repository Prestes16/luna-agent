from __future__ import annotations

import subprocess
from pathlib import Path

from .agent_models import AgentConfig
from .agent_policy import ensure_path_allowed, is_command_allowed


def list_dir(path: str, cfg: AgentConfig) -> dict:
    actual = ensure_path_allowed(path, cfg.target_root)
    if not actual.exists():
        return {"ok": False, "error": f"path não existe: {actual}"}
    if not actual.is_dir():
        return {"ok": False, "error": f"path não é diretório: {actual}"}

    items = []
    try:
        _entries = list(actual.iterdir())
    except OSError:
        _entries = []
    for item in sorted(_entries, key=lambda p: p.name.lower()):
        try:
            _isd = item.is_dir()
        except OSError:
            _isd = False
        items.append({"name": item.name, "path": str(item), "is_dir": _isd})

    return {"ok": True, "path": str(actual), "items": items}


def read_file(path: str, cfg: AgentConfig) -> dict:
    actual = ensure_path_allowed(path, cfg.target_root)
    if not actual.exists():
        return {"ok": False, "error": f"arquivo não existe: {actual}"}
    if not actual.is_file():
        return {"ok": False, "error": f"path não é arquivo: {actual}"}

    return {
        "ok": True,
        "path": str(actual),
        "content": actual.read_text(encoding="utf-8"),
    }


def write_patch(path: str, old: str, new: str, cfg: AgentConfig) -> dict:
    if not cfg.allow_write:
        return {"ok": False, "error": "escrita desabilitada pela política"}

    actual = ensure_path_allowed(path, cfg.target_root)
    if not actual.exists():
        return {"ok": False, "error": f"arquivo não existe: {actual}"}
    if not actual.is_file():
        return {"ok": False, "error": f"path não é arquivo: {actual}"}

    current = actual.read_text(encoding="utf-8")
    if old not in current:
        return {"ok": False, "error": "trecho antigo não encontrado no arquivo"}

    updated = current.replace(old, new, 1)
    backup = Path(str(actual) + ".bak")
    backup.write_text(current, encoding="utf-8")
    actual.write_text(updated, encoding="utf-8")

    return {
        "ok": True,
        "path": str(actual),
        "backup": str(backup),
        "message": "patch aplicado com backup simples",
    }


def run_command(cmd: str, cwd: str, cfg: AgentConfig) -> dict:
    if not is_command_allowed(cmd, cfg):
        return {"ok": False, "error": f"comando bloqueado pela política: {cmd}"}

    actual_cwd = ensure_path_allowed(cwd, cfg.target_root)
    if not actual_cwd.exists() or not actual_cwd.is_dir():
        return {"ok": False, "error": f"cwd inválido: {actual_cwd}"}

    completed = subprocess.run(
        cmd,
        cwd=str(actual_cwd),
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    return {
        "ok": completed.returncode == 0,
        "cmd": cmd,
        "cwd": str(actual_cwd),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def read_log(path: str, cfg: AgentConfig) -> dict:
    return read_file(path, cfg)