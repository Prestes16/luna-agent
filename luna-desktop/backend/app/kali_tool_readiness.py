"""Deterministic prerequisite checks for Kali tool command generation.

When required factual inputs are missing, Luna should ask for them instead of
inventing endpoints, identities, secrets or local file paths.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from .kali_tool_dictionary import get_tool_spec
from .reasoning_quality import build_operator_contract


_SERVICE_MARKERS = (
    "ssh", "ftp", "smtp", "imap", "pop3", "rdp", "smb", "mysql", "postgres",
    "postgresql", "http-get", "http-post-form", "https-post-form", "http-head",
)
_IDENTITY_MARKERS = (
    "usuário", "usuario", "username", "login conhecido", "userlist",
    "lista de usuários", "lista de usuarios", "-l ", "-L ",
)
_SECRET_MARKERS = (
    "senha", "password", "password list", "lista de senhas", "wordlist",
    "-p ", "-P ",
)
_WEB_FORM_MARKERS = ("http-post-form", "https-post-form", "formulário", "formulario", "login form")


@dataclass(frozen=True)
class ToolReadiness:
    tool: str | None
    ready: bool
    missing: tuple[str, ...]
    target: str | None

    def prompt(self) -> str:
        if self.ready or not self.tool:
            return ""
        return (
            f"TOOL READINESS [{self.tool}]: missing factual inputs: "
            + ", ".join(self.missing)
            + ". Do not invent them. Ask the operator only for the missing facts before emitting a command."
        )


def _host_from_value(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if text.casefold().startswith(("http://", "https://")):
        try:
            return urlsplit(text).hostname
        except ValueError:
            return None
    match = re.search(r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}\b|\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
    return match.group(0) if match else None


def assess_tool_readiness(message: str, scenario=None, history_text: str = "") -> ToolReadiness:
    contract = build_operator_contract(message)
    tool = contract.requested_tool
    if not tool:
        return ToolReadiness(None, True, (), None)

    combined = f"{message}\n{history_text}".casefold()
    scenario_target = getattr(scenario, "target", None) if scenario is not None else None
    target = contract.target_hosts[0] if contract.target_hosts else _host_from_value(scenario_target)

    missing: list[str] = []
    if tool == "hydra":
        if not target:
            missing.append("target")
        if not any(marker in combined for marker in _SERVICE_MARKERS):
            missing.append("service/module")
        if not any(marker.casefold() in combined for marker in _IDENTITY_MARKERS):
            missing.append("identity source")
        if not any(marker.casefold() in combined for marker in _SECRET_MARKERS):
            missing.append("secret source")
        if any(marker in combined for marker in _WEB_FORM_MARKERS):
            if not re.search(r"(?<![\w.])/[A-Za-z0-9][A-Za-z0-9._~/%?=&+-]*", message):
                missing.append("web-form endpoint")
            if not any(marker in combined for marker in ("campo", "field", "usuário=", "usuario=", "username=")):
                missing.append("web-form field mapping")
            if not any(marker in combined for marker in ("falha", "failure", "invalid", "incorret", "erro de login")):
                missing.append("web-form failure marker")

    elif tool in {"ffuf", "gobuster"}:
        if not target and "http://" not in combined and "https://" not in combined:
            missing.append("target URL")
        if "wordlist" not in combined and " -w " not in f" {combined} ":
            missing.append("wordlist")

    spec = get_tool_spec(tool)
    if spec and spec.required_facts and tool not in {"hydra", "ffuf", "gobuster"}:
        if not target and "target" in " ".join(spec.required_facts).casefold():
            missing.append("target")

    missing = list(dict.fromkeys(missing))
    return ToolReadiness(tool, not missing, tuple(missing), target)


def response_requests_missing_facts(response: str, readiness: ToolReadiness) -> bool:
    if readiness.ready or not readiness.missing:
        return True
    normalized = response.casefold()
    marker_map = {
        "target": ("alvo", "target", "host", "domínio", "dominio"),
        "service/module": ("serviço", "servico", "service", "módulo", "modulo", "protocolo", "porta"),
        "identity source": ("usuário", "usuario", "username", "userlist", "lista de usuários", "lista de usuarios"),
        "secret source": ("senha", "password", "wordlist", "lista de senhas"),
        "web-form endpoint": ("endpoint", "rota", "path", "url do login"),
        "web-form field mapping": ("campo", "fields", "parâmetro", "parametro"),
        "web-form failure marker": ("mensagem de falha", "failure", "falha", "resposta inválida", "resposta invalida"),
        "target URL": ("url", "alvo", "target"),
        "wordlist": ("wordlist", "lista"),
    }
    return all(any(marker in normalized for marker in marker_map.get(item, (item,))) for item in readiness.missing)
