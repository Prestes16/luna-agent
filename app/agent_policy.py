from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .agent_models import AgentConfig


DEFAULT_SAFE_BASE_DIRS = [
    str(Path.cwd().resolve()),
]

BLOCKED_COMMAND_PATTERNS = [
    " rm ",
    " del ",
    " rmdir ",
    " sudo ",
    " shutdown",
    " reboot",
    " mkfs",
    " format ",
    " useradd ",
    " usermod ",
    " passwd ",
    " net user ",
    " sc delete ",
    " reg delete ",
    " git push",
    " curl http",
    " wget http",
]

ALLOWED_COMMAND_PREFIXES = [
    "python ",
    "python3 ",
    "py ",
    "pip ",
    "pytest",
    "node ",
    "npm ",
    "npx ",
    "git status",
    "git diff",
    "git log",
    "dir",
    "ls",
    "type ",
    "cat ",
    "Get-ChildItem",
    "Get-Content",
]


_SAFE_BASE_DIRS: list[Path] = [Path(p).resolve() for p in DEFAULT_SAFE_BASE_DIRS]


def set_safe_base_dirs(paths: Iterable[str]) -> None:
    global _SAFE_BASE_DIRS
    resolved: list[Path] = []

    for p in paths:
        if not p:
            continue
        try:
            resolved.append(Path(p).resolve())
        except Exception:
            continue

    _SAFE_BASE_DIRS = resolved or [Path.cwd().resolve()]


def get_safe_base_dirs() -> list[str]:
    return [str(p) for p in _SAFE_BASE_DIRS]


def normalize_path(path: str) -> Path:
    return Path(path).expanduser().resolve()


def is_path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_target_root_allowed(target_root: str) -> bool:
    if not target_root:
        return False

    try:
        target = normalize_path(target_root)
    except Exception:
        return False

    return any(is_path_within(target, base) or target == base for base in _SAFE_BASE_DIRS)


def ensure_path_allowed(path: str, target_root: str) -> Path:
    target = normalize_path(target_root)
    actual = normalize_path(path)

    if not is_target_root_allowed(str(target)):
        raise PermissionError(f"target_root fora da política: {target}")

    if not (actual == target or is_path_within(actual, target)):
        raise PermissionError(f"path fora do target_root permitido: {actual}")

    return actual


def is_command_allowed(cmd: str, cfg: AgentConfig) -> bool:
    if not cfg.allow_run_command:
        return False

    text = f" {cmd.strip().lower()} "

    for blocked in BLOCKED_COMMAND_PATTERNS:
        if blocked in text:
            return False

    cmd_strip = cmd.strip()
    return any(cmd_strip.startswith(prefix) for prefix in ALLOWED_COMMAND_PREFIXES)


RISK_MAP: dict = {
    "list_dir":   "low",
    "read_file":  "low",
    "read_log":   "low",
    "write_patch": "medium",
    "run_command": "high",
    "deploy":      "high",
}


def classify_tool_risk(tool: str, args: dict, cfg: "AgentConfig") -> "RiskLevel":
    return RISK_MAP.get(tool, "high")


def requires_approval_for_tool(tool: str, cfg: AgentConfig) -> bool:
    if tool == "deploy":
        return True
    if tool == "write_patch":
        return cfg.require_approval_for_write
    if tool == "run_command":
        return cfg.require_approval_for_command
    return False