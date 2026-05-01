"""
Luna Bounty Tool — wrappers para toolkit de bug bounty web.

Integra: nuclei, dalfox, sqlmap, jwt_tool, graphql-cop, katana, waybackurls,
subfinder, httpx, feroxbuster. Todos opcionais — cada wrapper detecta
disponibilidade e retorna stub util se binario ausente.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Wordlists SecLists (path configuravel via env)
SECLISTS_BASE = os.getenv("SECLISTS_BASE", str(Path.home() / "tools" / "SecLists"))


def _which(binary: str) -> bool:
    return shutil.which(binary) is not None


def _run(cmd: list[str], timeout: int = 120, input_text: Optional[str] = None) -> dict:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            input=input_text,
        )
        return {
            "ok": r.returncode == 0,
            "rc": r.returncode,
            "stdout": r.stdout,
            "stderr": r.stderr,
            "cmd": " ".join(cmd),
        }
    except FileNotFoundError:
        return {"ok": False, "error": f"binary_not_found: {cmd[0]}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "timeout_s": timeout}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# -- Reconhecimento ------------------------------------------------------

def recon_subdomains(domain: str, sources: str = "all") -> dict:
    """subfinder -d <domain> -all. Retorna lista de subdominios."""
    if not _which("subfinder"):
        return {"ok": False, "error": "subfinder not installed", "install": "go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"}
    r = _run(["subfinder", "-d", domain, "-silent", "-all"], timeout=180)
    if r.get("ok"):
        r["subdomains"] = [s.strip() for s in r["stdout"].splitlines() if s.strip()]
        r["count"] = len(r["subdomains"])
    return r


def recon_live_hosts(targets: list[str], ports: str = "80,443,8080,8443") -> dict:
    """httpx probe sobre lista de hosts. Retorna live com status/title/tech."""
    if not _which("httpx"):
        return {"ok": False, "error": "httpx not installed", "install": "go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest"}
    inp = "\n".join(targets)
    r = _run(["httpx", "-silent", "-json", "-title", "-tech-detect", "-status-code", "-ports", ports],
             timeout=240, input_text=inp)
    if r.get("ok"):
        rows = []
        for line in r["stdout"].splitlines():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
        r["hosts"] = rows
        r["count"] = len(rows)
    return r


def recon_crawl(url: str, depth: int = 2, js: bool = True) -> dict:
    """katana crawler moderno com JS parsing."""
    if not _which("katana"):
        return {"ok": False, "error": "katana not installed", "install": "go install github.com/projectdiscovery/katana/cmd/katana@latest"}
    cmd = ["katana", "-u", url, "-d", str(depth), "-silent", "-jc"]
    if js:
        cmd.append("-jsl")
    r = _run(cmd, timeout=180)
    if r.get("ok"):
        r["urls"] = [s.strip() for s in r["stdout"].splitlines() if s.strip()]
        r["count"] = len(r["urls"])
    return r


def recon_wayback(domain: str) -> dict:
    """gau / waybackurls — URLs historicas."""
    bin_name = "gau" if _which("gau") else ("waybackurls" if _which("waybackurls") else None)
    if bin_name is None:
        return {"ok": False, "error": "gau/waybackurls not installed"}
    r = _run([bin_name, domain], timeout=120)
    if r.get("ok"):
        r["urls"] = [s.strip() for s in r["stdout"].splitlines() if s.strip()]
        r["count"] = len(r["urls"])
    return r


# -- Scanning ------------------------------------------------------------

def scan_nuclei(targets: list[str], severity: str = "medium,high,critical",
                templates: Optional[str] = None, tags: Optional[str] = None) -> dict:
    """
    nuclei scan. severity default medium+. templates/tags opcionais.
    Retorna findings JSON estruturados.
    """
    if not _which("nuclei"):
        return {"ok": False, "error": "nuclei not installed",
                "install": "go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest"}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\n".join(targets))
        targets_file = f.name
    cmd = ["nuclei", "-list", targets_file, "-jsonl", "-silent", "-severity", severity]
    if templates:
        cmd += ["-t", templates]
    if tags:
        cmd += ["-tags", tags]
    r = _run(cmd, timeout=600)
    try:
        os.unlink(targets_file)
    except Exception:
        pass
    if r.get("ok") or r.get("stdout"):
        findings = []
        for line in (r.get("stdout") or "").splitlines():
            try:
                findings.append(json.loads(line))
            except Exception:
                pass
        r["findings"] = findings
        r["count"] = len(findings)
    return r


def scan_dalfox(url: str, data: Optional[str] = None, cookies: Optional[str] = None) -> dict:
    """dalfox XSS scanner. url com parametros ou --data para POST."""
    if not _which("dalfox"):
        return {"ok": False, "error": "dalfox not installed", "install": "go install github.com/hahwul/dalfox/v2@latest"}
    cmd = ["dalfox", "url", url, "--silence", "--format", "json"]
    if data:
        cmd += ["--data", data]
    if cookies:
        cmd += ["-C", cookies]
    r = _run(cmd, timeout=300)
    if r.get("stdout"):
        try:
            r["findings"] = json.loads(r["stdout"])
        except Exception:
            r["findings_raw"] = r["stdout"][:4000]
    return r


def scan_sqlmap(url: str, data: Optional[str] = None, cookies: Optional[str] = None,
                level: int = 1, risk: int = 1, batch: bool = True) -> dict:
    """sqlmap SQL injection. Sempre --batch em Luna para evitar prompts."""
    if not _which("sqlmap"):
        return {"ok": False, "error": "sqlmap not installed", "install": "pip install sqlmap OR clone sqlmapproject/sqlmap"}
    cmd = ["sqlmap", "-u", url, f"--level={level}", f"--risk={risk}", "--random-agent"]
    if batch:
        cmd.append("--batch")
    if data:
        cmd += ["--data", data]
    if cookies:
        cmd += ["--cookie", cookies]
    return _run(cmd, timeout=600)


# -- JWT / GraphQL ------------------------------------------------------

def audit_jwt(token: str, action: str = "decode") -> dict:
    """
    Auditoria JWT local sem binarios externos.
    action: decode | check_alg_none | check_weak_secret | check_kid_injection
    """
    import base64
    parts = token.split(".")
    if len(parts) != 3:
        return {"ok": False, "error": "token must have 3 parts"}
    def _b64d(s):
        s += "=" * (-len(s) % 4)
        try:
            return base64.urlsafe_b64decode(s).decode("utf-8", errors="replace")
        except Exception as e:
            return f"<decode_error: {e}>"
    header = _b64d(parts[0])
    payload = _b64d(parts[1])
    try:
        header_json = json.loads(header)
    except Exception:
        header_json = {}
    try:
        payload_json = json.loads(payload)
    except Exception:
        payload_json = {}
    issues = []
    alg = header_json.get("alg", "")
    if alg.lower() == "none":
        issues.append({"severity": "critical", "issue": "alg=none — bypass de assinatura"})
    if alg == "HS256" and "kid" in header_json:
        issues.append({"severity": "medium", "issue": "kid presente com HS256 — testar kid injection (SQLi/LFI no kid)"})
    if header_json.get("jku") or header_json.get("x5u"):
        issues.append({"severity": "high", "issue": "jku/x5u presente — testar SSRF via URL controlada"})
    if not payload_json.get("exp"):
        issues.append({"severity": "medium", "issue": "sem claim exp — token nao expira"})
    return {
        "ok": True,
        "header": header_json,
        "payload": payload_json,
        "signature_b64": parts[2],
        "issues": issues,
        "next_tests": [
            "tentar alg=none swap",
            "tentar HS256 confusion com chave publica como secret",
            "brute-force de HS* com jwt_tool -C -d /path/to/wordlist",
            "se kid: testar payload SQLi/LFI no campo kid",
        ],
    }


def audit_graphql(endpoint: str) -> dict:
    """
    Auditoria GraphQL via queries de introspeccao + checks comuns.
    Nao requer binario externo (usa httpx python).
    """
    try:
        import httpx
    except ImportError:
        return {"ok": False, "error": "httpx required"}
    introspection_query = {"query": "query IntrospectionQuery { __schema { queryType { name } mutationType { name } subscriptionType { name } types { kind name } } }"}
    issues = []
    try:
        with httpx.Client(timeout=20, verify=False) as client:
            r = client.post(endpoint, json=introspection_query, headers={"Content-Type": "application/json"})
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        schema = data.get("data", {}).get("__schema")
        if schema:
            issues.append({"severity": "medium", "issue": "introspection ativa em producao"})
            types = schema.get("types", [])
            sensitive = [t["name"] for t in types if any(k in t.get("name", "").lower() for k in ("user", "admin", "password", "token", "secret", "key"))]
            if sensitive:
                issues.append({"severity": "info", "issue": f"tipos sensiveis expostos: {', '.join(sensitive[:10])}"})
            # testar aliasing dos / batch
            try:
                batch_q = {"query": "{ __typename __typename __typename }"}
                rb = client.post(endpoint, json=batch_q, headers={"Content-Type": "application/json"})
                if rb.status_code == 200:
                    issues.append({"severity": "info", "issue": "aliases permitidos — testar DoS via batch de aliases"})
            except Exception:
                pass
        return {"ok": True, "endpoint": endpoint, "introspection_enabled": bool(schema), "issues": issues,
                "next_tests": [
                    "baixar schema completo com clairvoyance se introspection off",
                    "testar autenticacao em mutations sensiveis",
                    "batch queries para rate limit bypass",
                    "circular queries para DoS",
                    "field suggestions error-based enum discovery",
                ]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# -- Wordlists / scope --------------------------------------------------

def wordlist_path(name: str = "raft-large-words.txt") -> dict:
    """Resolve caminho de wordlist conhecida. Aponta para SecLists instalado."""
    candidates = [
        Path(SECLISTS_BASE) / "Discovery" / "Web-Content" / name,
        Path(SECLISTS_BASE) / "Fuzzing" / name,
        Path.home() / "tools" / name,
    ]
    for c in candidates:
        if c.exists():
            return {"ok": True, "path": str(c)}
    return {"ok": False, "error": f"wordlist {name} not found",
            "install": "git clone https://github.com/danielmiessler/SecLists ~/tools/SecLists"}


def scope_check(target: str, in_scope: list[str], out_of_scope: list[str] = None) -> dict:
    """
    Valida se target esta no escopo. Guardrail critico de bounty.
    in_scope/out_of_scope podem ser dominios ou wildcards (*.example.com).
    """
    import fnmatch
    out_of_scope = out_of_scope or []
    def match(t, pattern):
        return fnmatch.fnmatch(t.lower(), pattern.lower())
    in_any = any(match(target, p) for p in in_scope)
    out_any = any(match(target, p) for p in out_of_scope)
    return {
        "target": target,
        "in_scope": in_any and not out_any,
        "matched_in": [p for p in in_scope if match(target, p)],
        "matched_out": [p for p in out_of_scope if match(target, p)],
        "decision": "PROCEED" if (in_any and not out_any) else "ABORT",
    }


# -- Tool definitions (OpenAI-compatible) -------------------------------

def get_tool_definitions() -> list[dict]:
    """Expoe as funcoes como tool definitions para o loop agentico."""
    return [
        {"type": "function", "function": {"name": "bounty_recon_subdomains",
            "description": "Lista subdominios de um dominio via subfinder",
            "parameters": {"type": "object", "properties": {"domain": {"type": "string"}}, "required": ["domain"]}}},
        {"type": "function", "function": {"name": "bounty_recon_live",
            "description": "Probe httpx em lista de hosts, retorna live com status/title/tech",
            "parameters": {"type": "object", "properties": {"targets": {"type": "array", "items": {"type": "string"}}, "ports": {"type": "string"}}, "required": ["targets"]}}},
        {"type": "function", "function": {"name": "bounty_crawl",
            "description": "Crawler moderno (katana) com JS parsing",
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "depth": {"type": "integer"}}, "required": ["url"]}}},
        {"type": "function", "function": {"name": "bounty_scan_nuclei",
            "description": "Executa nuclei sobre lista de targets, filtra severity",
            "parameters": {"type": "object", "properties": {"targets": {"type": "array", "items": {"type": "string"}}, "severity": {"type": "string"}, "tags": {"type": "string"}}, "required": ["targets"]}}},
        {"type": "function", "function": {"name": "bounty_scan_dalfox",
            "description": "Scanner XSS dalfox. URL com parametros ou data POST",
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "data": {"type": "string"}, "cookies": {"type": "string"}}, "required": ["url"]}}},
        {"type": "function", "function": {"name": "bounty_audit_jwt",
            "description": "Decoda e audita JWT sem binarios externos. Detecta alg=none, kid injection, jku SSRF",
            "parameters": {"type": "object", "properties": {"token": {"type": "string"}}, "required": ["token"]}}},
        {"type": "function", "function": {"name": "bounty_audit_graphql",
            "description": "Audita endpoint GraphQL (introspection, tipos sensiveis, batch aliases)",
            "parameters": {"type": "object", "properties": {"endpoint": {"type": "string"}}, "required": ["endpoint"]}}},
        {"type": "function", "function": {"name": "bounty_scope_check",
            "description": "GUARDRAIL: valida target contra in_scope/out_of_scope antes de atacar",
            "parameters": {"type": "object", "properties": {"target": {"type": "string"}, "in_scope": {"type": "array", "items": {"type": "string"}}, "out_of_scope": {"type": "array", "items": {"type": "string"}}}, "required": ["target", "in_scope"]}}},
    ]