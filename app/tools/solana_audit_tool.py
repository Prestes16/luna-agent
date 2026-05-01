"""
Luna Solana Audit Tool - IDL parser, tx decoder, CPI graph, static checks avançados.

Complementa app/hunter/audit_toolkit.py com analises nao-binary-dependent:
- Parse de IDL Anchor (JSON) para mapear instrucoes, contas, discriminators
- Decode de transacao raw via RPC Helius/Solana
- Checks estaticos Rust sem binario externo (regex patterns refinados)
- CPI graph builder (quais programas chamam quem)
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# -- IDL parser ---------------------------------------------------------

@dataclass
class IxAccount:
    name: str
    is_mut: bool
    is_signer: bool
    is_optional: bool = False
    pda: Optional[dict] = None   # {seeds: [...]}

@dataclass
class Instruction:
    name: str
    discriminator: Optional[list[int]]
    accounts: list[IxAccount]
    args: list[dict]


def parse_idl(idl_path_or_json: str) -> dict:
    """
    Le IDL Anchor (arquivo .json ou string JSON) e retorna estrutura navegavel.
    """
    try:
        if os.path.isfile(idl_path_or_json):
            data = json.loads(Path(idl_path_or_json).read_text(encoding="utf-8"))
        else:
            data = json.loads(idl_path_or_json)
    except Exception as e:
        return {"ok": False, "error": f"parse failed: {e}"}

    instructions = []
    for ix in data.get("instructions", []):
        accs = []
        for a in ix.get("accounts", []):
            accs.append({
                "name": a.get("name"),
                "is_mut": a.get("isMut") or a.get("writable", False),
                "is_signer": a.get("isSigner") or a.get("signer", False),
                "is_optional": a.get("isOptional") or a.get("optional", False),
                "pda": a.get("pda"),
            })
        instructions.append({
            "name": ix.get("name"),
            "discriminator": ix.get("discriminator"),
            "accounts": accs,
            "args": ix.get("args", []),
        })

    accounts = [{"name": a.get("name"), "type": a.get("type")} for a in data.get("accounts", [])]
    errors = [{"code": e.get("code"), "name": e.get("name"), "msg": e.get("msg")} for e in data.get("errors", [])]

    # Red flags automaticos
    red_flags = []
    for ix in instructions:
        has_signer = any(a["is_signer"] for a in ix["accounts"])
        mutates = any(a["is_mut"] for a in ix["accounts"])
        if mutates and not has_signer:
            red_flags.append({
                "severity": "high",
                "instruction": ix["name"],
                "issue": "Instrucao muta contas mas nao exige signer - potencial missing_signer_check",
            })
        sensitive_names = ("admin", "authority", "owner", "withdraw", "transfer", "close")
        if any(s in ix["name"].lower() for s in sensitive_names) and not has_signer:
            red_flags.append({
                "severity": "critical",
                "instruction": ix["name"],
                "issue": f"Instrucao sensivel '{ix['name']}' sem signer",
            })

    return {
        "ok": True,
        "name": data.get("name") or data.get("metadata", {}).get("name"),
        "version": data.get("version") or data.get("metadata", {}).get("version"),
        "address": data.get("address") or data.get("metadata", {}).get("address"),
        "instructions": instructions,
        "accounts": accounts,
        "errors": errors,
        "red_flags": red_flags,
        "stats": {
            "ix_count": len(instructions),
            "account_count": len(accounts),
            "error_count": len(errors),
            "flags": len(red_flags),
        },
    }


# -- Rust static checks (refinados) -------------------------------------

RUST_CHECKS = [
    {
        "id": "missing_checked_math",
        "severity": "high",
        "pattern": re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*\s*[+\-*/]=?\s*[a-zA-Z0-9_]"),
        "description": "Operacao aritmetica sem checked_/saturating_/wrapping_ - possivel overflow",
        "filter": lambda line: (
            "checked_" not in line
            and "saturating_" not in line
            and "wrapping_" not in line
            and not line.lstrip().startswith(("//", "/*", "*"))
            and not any(t in line for t in ("fn ", "//", "-> ", "struct ", "enum ", "impl ", "use "))
            and any(op in line for op in (" + ", " - ", " * ", " / ", "+=", "-=", "*=", "/="))
        ),
    },
    {
        "id": "unchecked_account",
        "severity": "high",
        "pattern": re.compile(r"UncheckedAccount|AccountInfo<"),
        "description": "AccountInfo/UncheckedAccount - validacao manual obrigatoria",
    },
    {
        "id": "unsafe_cpi_signer",
        "severity": "critical",
        "pattern": re.compile(r"invoke_signed\s*\("),
        "description": "invoke_signed usado - validar que seeds nao permitem forjar autoridade",
    },
    {
        "id": "realloc_without_zero_init",
        "severity": "medium",
        "pattern": re.compile(r"\.realloc\s*\([^)]+,\s*false\s*\)"),
        "description": "realloc com zero_init=false - vazamento de memoria/state antigo",
    },
    {
        "id": "close_without_zero",
        "severity": "high",
        "pattern": re.compile(r"close\s*=\s*\w+"),
        "description": "constraint close= presente - verificar zeroizacao para evitar revival",
    },
    {
        "id": "missing_has_one",
        "severity": "medium",
        "pattern": re.compile(r"#\[account\([^)]*\)\]"),
        "description": "Verificar se contas relacionadas tem has_one ou constraint adequado",
    },
    {
        "id": "sysvar_clock_manipulation",
        "severity": "medium",
        "pattern": re.compile(r"Clock::get\(\)|sysvar::clock"),
        "description": "Uso de Clock - atento a manipulacao de timestamp/slot em validators custom",
    },
    {
        "id": "token2022_hooks",
        "severity": "high",
        "pattern": re.compile(r"spl_token_2022|Token2022"),
        "description": "Token-2022 - revisar Transfer Hooks, Permanent Delegate, Confidential Transfer",
    },
]


def rust_static_scan(project_path: str, max_files: int = 200) -> dict:
    """
    Scan estatico refinado em arquivos .rs. Retorna findings por arquivo.
    """
    p = Path(project_path)
    if not p.exists():
        return {"ok": False, "error": f"path not found: {project_path}"}
    rs_files = list(p.rglob("*.rs"))[:max_files]
    findings = []
    for rf in rs_files:
        try:
            content = rf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(content.splitlines(), start=1):
            for check in RUST_CHECKS:
                if check["pattern"].search(line):
                    filt = check.get("filter")
                    if filt and not filt(line):
                        continue
                    findings.append({
                        "file": str(rf.relative_to(p)),
                        "line": i,
                        "rule_id": check["id"],
                        "severity": check["severity"],
                        "description": check["description"],
                        "snippet": line.strip()[:200],
                    })
    # Aggregate
    by_severity = {}
    for f in findings:
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1
    return {
        "ok": True,
        "project": str(p),
        "files_scanned": len(rs_files),
        "findings": findings,
        "count": len(findings),
        "by_severity": by_severity,
    }


# -- Tx decoder (via RPC) ------------------------------------------------

def decode_transaction(signature: str, rpc_url: Optional[str] = None) -> dict:
    """
    Busca e decoda transacao. Usa RPC publico ou HELIUS se configurado.
    Retorna instrucoes, logs Anchor, CPI tree.
    """
    try:
        import httpx
    except ImportError:
        return {"ok": False, "error": "httpx required"}
    rpc_url = rpc_url or os.getenv("HELIUS_RPC_URL") or "https://api.mainnet-beta.solana.com"
    body = {
        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
    }
    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(rpc_url, json=body)
            data = r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    if "error" in data:
        return {"ok": False, "error": data["error"]}
    tx = data.get("result")
    if not tx:
        return {"ok": False, "error": "tx not found or not finalized"}

    msg = tx.get("transaction", {}).get("message", {})
    meta = tx.get("meta", {}) or {}

    # Logs Anchor emitidos
    logs = meta.get("logMessages") or []
    anchor_events = [l for l in logs if "Program log: Instruction:" in l or "Program data:" in l]

    # Instructions top-level
    ixs = []
    for ix in msg.get("instructions", []):
        ixs.append({
            "program": ix.get("program") or ix.get("programId"),
            "parsed": ix.get("parsed"),
            "accounts": ix.get("accounts", []),
        })

    # Inner instructions (CPI tree)
    inner = []
    for entry in meta.get("innerInstructions", []) or []:
        for ix in entry.get("instructions", []):
            inner.append({
                "index": entry.get("index"),
                "program": ix.get("program") or ix.get("programId"),
                "parsed": ix.get("parsed"),
            })

    # Balance changes
    pre = meta.get("preBalances") or []
    post = meta.get("postBalances") or []
    accounts = msg.get("accountKeys", [])
    changes = []
    for i, acc in enumerate(accounts):
        if i < len(pre) and i < len(post):
            delta = post[i] - pre[i]
            if delta != 0:
                pubkey = acc.get("pubkey") if isinstance(acc, dict) else acc
                changes.append({"pubkey": pubkey, "delta_lamports": delta, "delta_sol": delta / 1e9})

    return {
        "ok": True,
        "signature": signature,
        "slot": tx.get("slot"),
        "block_time": tx.get("blockTime"),
        "success": (meta.get("err") is None),
        "err": meta.get("err"),
        "fee": meta.get("fee"),
        "instructions": ixs,
        "inner_instructions": inner,
        "balance_changes": changes,
        "anchor_logs": anchor_events,
        "compute_units": meta.get("computeUnitsConsumed"),
    }


# -- CPI graph ----------------------------------------------------------

def build_cpi_graph(project_path: str) -> dict:
    """Extrai grafo de CPI (qual programa chama qual) a partir de .rs."""
    p = Path(project_path)
    if not p.exists():
        return {"ok": False, "error": "path not found"}
    edges = []
    pattern = re.compile(r'invoke(?:_signed)?\s*\(\s*&\s*(?:spl_token|solana_program::system_instruction|([a-zA-Z_:]+))', re.MULTILINE)
    for rf in p.rglob("*.rs"):
        try:
            content = rf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in pattern.finditer(content):
            edges.append({"file": str(rf.relative_to(p)), "target": m.group(1) or "system_or_token"})
    return {"ok": True, "edges": edges, "count": len(edges)}


# -- Tool definitions ---------------------------------------------------

def get_tool_definitions() -> list[dict]:
    return [
        {"type": "function", "function": {"name": "solana_parse_idl",
            "description": "Parse IDL Anchor e retorna ixs, contas, red flags automaticos",
            "parameters": {"type": "object", "properties": {"idl_path_or_json": {"type": "string"}}, "required": ["idl_path_or_json"]}}},
        {"type": "function", "function": {"name": "solana_rust_scan",
            "description": "Scan estatico refinado de .rs (overflow, CPI unsafe, Token-2022, close exploits)",
            "parameters": {"type": "object", "properties": {"project_path": {"type": "string"}}, "required": ["project_path"]}}},
        {"type": "function", "function": {"name": "solana_decode_tx",
            "description": "Decoda transacao on-chain via RPC. Retorna ixs, CPI tree, balance changes, logs Anchor",
            "parameters": {"type": "object", "properties": {"signature": {"type": "string"}, "rpc_url": {"type": "string"}}, "required": ["signature"]}}},
        {"type": "function", "function": {"name": "solana_cpi_graph",
            "description": "Constroi grafo de CPI do projeto (quem chama quem)",
            "parameters": {"type": "object", "properties": {"project_path": {"type": "string"}}, "required": ["project_path"]}}},
    ]