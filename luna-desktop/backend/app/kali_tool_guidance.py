"""Compact deterministic Kali guidance injected only when relevant.

Small local models should not spend context rediscovering CLI contracts. This
module combines the legacy concise guidance with a structured Linux/Kali tool
dictionary, contextual Nmap strategy and prerequisite readiness checks.
"""

from __future__ import annotations

import re
from typing import Sequence, Mapping, Any

from .kali_tool_dictionary import get_tool_spec
from .kali_tool_readiness import assess_tool_readiness
from .offensive_strategy import nmap_context_guidance


_TOOL_GUIDANCE: dict[str, str] = {
    "nmap": (
        "Nmap target=hostname/IP/CIDR, nunca URL. Em recon inicial Kali use técnica explícita "
        "(-sS com sudo para SYN/raw socket; -sT sem privilégio). -sV enumera serviços; -A e "
        "--script=vuln só quando a intenção pedir profundidade correspondente. Não crie arquivo "
        "de saída sem pedido explícito."
    ),
    "masscan": (
        "Masscan target=IP/CIDR e portas devem ser explícitas; preserve rate/cidr pedidos e não "
        "converta URL em target. Não invente interface, source IP ou arquivo de saída."
    ),
    "rustscan": (
        "RustScan recebe host/IP e pode encaminhar argumentos ao Nmap após --. Preserve o alvo e "
        "não invente ranges/ports que o operador não pediu."
    ),
    "ffuf": (
        "FFUF web fuzzing exige URL coerente e normalmente marcador FUZZ no ponto de mutação. "
        "Se -w for necessário, use somente wordlist observada/fornecida; não invente path local."
    ),
    "gobuster": (
        "Gobuster exige modo explícito (ex. dir/dns/vhost). Em dir, -u recebe URL e -w requer "
        "wordlist factual; não invente caminho de wordlist."
    ),
    "feroxbuster": (
        "Feroxbuster recebe URL com -u/posicional conforme sintaxe real. Preserve scheme/host e "
        "não invente cookies, headers ou wordlists."
    ),
    "nuclei": (
        "Nuclei recebe alvo com -u/-l. Não invente template ID, header, token ou arquivo; use "
        "templates específicos somente quando observados ou pedidos."
    ),
    "sqlmap": (
        "SQLMap deve preservar URL/parâmetros exatamente observados. Não invente parâmetro, cookie, "
        "credencial ou POST body; intensidade/risk/level deve acompanhar o pedido."
    ),
    "httpx": (
        "httpx trabalha com hosts/URLs conforme modo; preserve target e flags reais. Não confunda "
        "ProjectDiscovery httpx com biblioteca Python."
    ),
    "whatweb": "WhatWeb recebe URL/host; preserve alvo e use agressividade maior somente quando pedida.",
    "subfinder": "Subfinder recebe domínio raiz; não passe scheme/path. Não invente provider keys.",
    "amass": "Amass enumera domínios; preserve domínio raiz e não invente config/API keys.",
    "dig": "dig recebe nome DNS e tipo de registro; não passe URL completa nem invente resolver.",
    "dnsrecon": "dnsrecon recebe domínio/target conforme modo; preserve domínio e não invente wordlist.",
    "enum4linux-ng": "enum4linux-ng recebe host/IP. Não invente credenciais ou domínio Windows não observado.",
    "smbclient": "smbclient requer host/share conforme a tarefa. Não invente usuário, senha ou share.",
    "netexec": "NetExec requer protocolo e target; credenciais devem vir de evidência/operator input, nunca ser inventadas.",
    "hydra": (
        "Hydra exige serviço/módulo, target e fontes de identidade/segredo explícitas. "
        "Em formulários web também exige endpoint, nomes de campos e marcador de falha observados. "
        "Nunca invente /login, usuários, senhas, wordlists ou paths locais."
    ),
    "hashcat": "Hashcat exige hash mode coerente e arquivo/hash factual. Não invente mode, wordlist ou path.",
    "john": "John the Ripper opera sobre hashes/arquivos observados. Não invente formato ou wordlist.",
}

_FOLLOWUP_MARKERS = (
    "esse comando", "este comando", "agora", "otimize", "otimiza", "melhore",
    "continue", "próximo", "proximo", "maior valor", "principais portas",
)


def requested_kali_tool(message: str) -> str | None:
    normalized = message.casefold()
    for tool in sorted(_TOOL_GUIDANCE, key=len, reverse=True):
        if re.search(rf"(?<![\w.-]){re.escape(tool)}(?![\w.-])", normalized):
            return tool
    return None


def _history_text(history: Sequence[Mapping[str, Any]]) -> str:
    parts: list[str] = []
    for item in history[-4:]:
        content = item.get("content", "")
        if isinstance(content, str):
            parts.append(content[:600])
    return "\n".join(parts)


def guidance_for_context(message: str, *, scenario=None, history: Sequence[Mapping[str, Any]] = ()) -> str:
    """Return compact tool guidance using current turn plus recent factual context."""
    tool = requested_kali_tool(message)
    history_text = _history_text(history)
    if not tool and any(marker in message.casefold() for marker in _FOLLOWUP_MARKERS):
        tool = requested_kali_tool(history_text)
    if not tool:
        return ""

    chunks = [f"TOOL CONTRACT [{tool}]: {_TOOL_GUIDANCE[tool]}"]
    spec = get_tool_spec(tool)
    if spec:
        chunks.append("LINUX TOOL DICTIONARY: " + spec.prompt())

    scenario_prompt = scenario.to_prompt_block(650) if scenario is not None else ""
    combined_context = f"{message}\n{scenario_prompt}\n{history_text}"

    if tool == "nmap":
        strategic = nmap_context_guidance(combined_context)
        if strategic:
            chunks.append(strategic)

    readiness = assess_tool_readiness(message, scenario=scenario, history_text=history_text)
    if readiness.tool == tool and not readiness.ready:
        chunks.append(readiness.prompt())
        if tool == "hydra":
            chunks.append(
                "HYDRA RULE: enquanto os pré-requisitos estiverem ausentes, não gere comando. "
                "Peça serviço/módulo, fonte de usuário e fonte de senha; em formulário web peça "
                "também endpoint/campos/marcador de falha. Não dê exemplos com paths inventados."
            )

    return " ".join(chunks)


def guidance_for_message(message: str) -> str:
    """Backward-compatible single-turn guidance used by existing tests."""
    return guidance_for_context(message)
