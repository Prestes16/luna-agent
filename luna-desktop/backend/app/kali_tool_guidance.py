"""Compact, deterministic Kali tool guidance injected only when relevant.

The 4B model should not spend context remembering basic CLI contracts.  This
registry supplies small syntax/target invariants for common Kali tools while
leaving strategy selection to the reasoning pipeline.
"""

from __future__ import annotations

import re


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
    "whatweb": (
        "WhatWeb recebe URL/host; preserve alvo e use agressividade maior somente quando pedida."
    ),
    "subfinder": (
        "Subfinder recebe domínio raiz; não passe scheme/path. Não invente provider keys."
    ),
    "amass": (
        "Amass enumera domínios; preserve domínio raiz e não invente config/API keys."
    ),
    "dig": (
        "dig recebe nome DNS e tipo de registro; não passe URL completa nem invente resolver."
    ),
    "dnsrecon": (
        "dnsrecon recebe domínio/target conforme modo; preserve domínio e não invente wordlist."
    ),
    "enum4linux-ng": (
        "enum4linux-ng recebe host/IP. Não invente credenciais ou domínio Windows não observado."
    ),
    "smbclient": (
        "smbclient requer host/share conforme a tarefa. Não invente usuário, senha ou share."
    ),
    "netexec": (
        "NetExec requer protocolo e target; credenciais devem vir de evidência/operator input, "
        "nunca ser inventadas."
    ),
    "hydra": (
        "Hydra exige serviço/target e fontes de credenciais explícitas. Nunca invente userlist, "
        "password list ou path local."
    ),
    "hashcat": (
        "Hashcat exige hash mode coerente e arquivo/hash factual. Não invente mode, wordlist ou path."
    ),
    "john": (
        "John the Ripper opera sobre hashes/arquivos observados. Não invente formato ou wordlist."
    ),
}


def requested_kali_tool(message: str) -> str | None:
    normalized = message.casefold()
    # Longest-first prevents enum4linux matching enum4linux-ng prefixes.
    for tool in sorted(_TOOL_GUIDANCE, key=len, reverse=True):
        if re.search(rf"(?<![\w.-]){re.escape(tool)}(?![\w.-])", normalized):
            return tool
    return None


def guidance_for_message(message: str) -> str:
    tool = requested_kali_tool(message)
    if not tool:
        return ""
    return f"TOOL CONTRACT [{tool}]: {_TOOL_GUIDANCE[tool]}"
