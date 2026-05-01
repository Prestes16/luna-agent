from __future__ import annotations

# ── Carrega .env ANTES de qualquer import que leia os.getenv() ────────────────
import os as _os_early
from pathlib import Path as _Path
_ENV_FILE = _Path(__file__).resolve().parent.parent / ".env"
if _ENV_FILE.exists():
    try:
        from dotenv import load_dotenv as _load_dotenv
        _load_dotenv(dotenv_path=str(_ENV_FILE), override=True)
        import logging as _log
        _log.getLogger("luna.main").info(f"✅ .env carregado: {_ENV_FILE}")
        _sb = _os_early.getenv("SUPABASE_URL","")
        _log.getLogger("luna.main").info(f"   SUPABASE_URL={'configurado' if _sb else '⚠️ VAZIO'}")
    except ImportError:
        pass
else:
    import logging as _log
    _log.getLogger("luna.main").warning(f"⚠️ .env não encontrado em: {_ENV_FILE}")

from pathlib import Path
import os
import logging
import tempfile
from typing import Literal

logger = logging.getLogger("luna.main")

import json

from fastapi import FastAPI, HTTPException, Response, UploadFile, File, Form, Body
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI, AsyncOpenAI
from pydantic import BaseModel, Field
from app.services.execution_log import append_execution_log as append_structured_log, EventType
from app.services.guards import run_all_guards, SAFE_MODE_PREFACE
from app.services.memory import (
    stm_add, stm_get, stm_clear,
    ltm_add, ltm_get_facts, ltm_get_summaries, ltm_save_fact, ltm_get_stats,
)
from app.services.image_service import (
    generate_image, edit_image, create_variation,
    generate_image_stability, edit_image_stability, create_variation_stability,
    get_gallery, delete_image, get_image_bytes,
)
from datetime import datetime, timezone
try:
    from .agent_models import AgentConfig, AgentRequest, ApprovalDecision
    from .agent_policy import set_safe_base_dirs
    from .agent_runtime import AgentRuntime
    from .agent_state_store import (
        ensure_agent_files,
        load_config,
        save_config,
        load_last_plan,
        approve_action,
        is_action_approved,
        append_audit_entry,
        load_audit_log,
    )
    from . import worker_store as _ws
    from .worker_store import (
        WorkerApprovalDecision,
        WorkerApprovalRequest,
    )
except ImportError:
    from app.agent_models import AgentConfig, AgentRequest, ApprovalDecision
    from app.agent_policy import set_safe_base_dirs
    from app.agent_runtime import AgentRuntime
    from app.agent_state_store import (
        ensure_agent_files,
        load_config,
        save_config,
        load_last_plan,
        approve_action,
        is_action_approved,
        append_audit_entry,
        load_audit_log,
    )
    from app import worker_store as _ws
    from app.worker_store import (
        WorkerApprovalDecision,
        WorkerApprovalRequest,
    )

def _write_audit(
    action_id: str,
    tool: str,
    risk: str,
    decision: str,
    session_id: str = "",
    target: str = "",
    result_ok: bool | None = None,
    error: str = "",
) -> None:
    append_audit_entry({
        "ts":        datetime.now(timezone.utc).isoformat(),
        "action_id": action_id,
        "tool":      tool,
        "risk":      risk,
        "decision":  decision,
        "session_id": session_id,
        "target":    target,
        "result_ok": result_ok,
        "error":     error,
    })


BASE_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"
STATIC_DIR = BASE_DIR / "app" / "static"
WORKSPACES_DIR = BASE_DIR / "workspaces"
ACTIVE_WORKSPACE = (os.getenv("LUNA_ACTIVE_WORKSPACE", "luna-agent") or "luna-agent").strip()

# Mutable runtime state — workspace pode ser trocado via /workspace/switch
_runtime_workspace = {"active": ACTIVE_WORKSPACE}
SAFE_MODE_ENABLED = (os.getenv("LUNA_SAFE_MODE", "1") or "1").strip().lower() not in ("0", "false", "no", "off")
SAFE_MODE_SAME_MESSAGE_THRESHOLD = int((os.getenv("LUNA_SAFE_MODE_SAME_MESSAGE_THRESHOLD", "2") or "2").strip())

# Token de autenticação do Worker (opcional — se vazio, endpoints worker ficam abertos)
WORKER_TOKEN = (os.getenv("LUNA_WORKER_TOKEN", "") or "").strip()

app = FastAPI(title="Luna Agent", version="0.1.1")

# ─── Security layer (token, rate limit, headers, size limit, redactor) ───────
try:
    from app.security import install as _install_security, resolved_cors_origins as _resolve_cors
    _LUNA_API_TOKEN = _install_security(app)
    logger.info("security layer active (token persisted to ~/.luna-agent/.api_token)")
except Exception as _sec_err:
    _LUNA_API_TOKEN = ""
    logger.error(f"security layer failed to install: {_sec_err}")

# ─── CORS ────────────────────────────────────────────────────────────────────
_DEFAULT_CORS_DEV = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:4173",
]
try:
    _cors_origins, _cors_regex = _resolve_cors(_DEFAULT_CORS_DEV)
except Exception:
    _cors_origins, _cors_regex = _DEFAULT_CORS_DEV, None

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Luna-Token", "X-Requested-With"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ─── Pay-Flow router ─────────────────────────────────────────────────────────
try:
    from app.payments.routes import router as _payment_router
    app.include_router(_payment_router)
    import logging as _logging
    _logging.getLogger("luna.main").info("✅ Pay-Flow router montado: /payment/*")
except Exception as _pe:
    import logging as _logging
    import traceback as _tb
    _logging.getLogger("luna.main").error(
        f"❌ Pay-Flow router NAO carregado — TODAS as rotas /payment/* ficam 404\n"
        f"   Erro: {_pe}\n"
        f"   Traceback:\n{_tb.format_exc()}"
    )


# ─── Página de cobrança web (/pay) ───────────────────────────────────────────
@app.get("/pay", include_in_schema=False)
def payment_page():
    """
    Página HTML de cobrança — acessível via ngrok para qualquer dispositivo.
    Exibe os planos, gera QR Solana Pay e confirma via Helius webhook.
    URL de compartilhamento: https://<ngrok>/pay?user=<user_id>

    CSP: unsafe-eval necessário para o @solana/web3.js (usa eval() internamente).
    """
    from fastapi.responses import HTMLResponse
    content = (STATIC_DIR / "pay.html").read_text(encoding="utf-8")
    csp = (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' https: data: blob:; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://unpkg.com; "
        "connect-src 'self' https: wss: blob: data:; "
        "img-src 'self' data: blob: https:; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;"
    )
    return HTMLResponse(
        content=content,
        headers={"Content-Security-Policy": csp},
    )


def get_active_workspace() -> str:
    return _runtime_workspace["active"]


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def get_workspace_files() -> list[str]:
    return [
        "PROJECT_CONTEXT.md",
        "CURRENT_STATUS.md",
        "NEXT_STEPS.md",
        "PREFERENCES_CLEITON.md",
        "SESSION_LOG.md",
        "DECISIONS_LOG.md",
        "BUGS_AND_FIXES.md",
        "SECURITY_GUARDS.md",
        "AUTONOMY_POLICY.md",
        "EXECUTION_LOG.md",
    ]


def inspect_workspace(workspace_name: str) -> dict:
    ws_dir = WORKSPACES_DIR / workspace_name
    required = get_workspace_files()
    found: list[str] = []
    missing: list[str] = []

    for filename in required:
        text = read_text_file(ws_dir / filename)
        if text:
            found.append(filename)
        else:
            missing.append(filename)

    return {
        "workspace": workspace_name,
        "found": found,
        "missing": missing,
        "loaded": len(found) > 0,
        "all_required_present": len(missing) == 0,
        "file_count": len(found),
    }


def append_execution_log(workspace_name: str, lines: list[str]) -> None:
    ws_dir = WORKSPACES_DIR / workspace_name
    log_path = ws_dir / "EXECUTION_LOG.md"
    prefix = "\n" if log_path.exists() and log_path.read_text(encoding="utf-8").strip() else ""
    body = "\n".join(lines).strip()
    if not body:
        return
    with log_path.open("a", encoding="utf-8") as f:
        f.write(prefix + body + "\n")


def build_workspace_prompt(workspace_name: str) -> str:
    ws_dir = WORKSPACES_DIR / workspace_name
    files = get_workspace_files()
    parts: list[str] = []

    for filename in files:
        text = read_text_file(ws_dir / filename)
        if text:
            parts.append(f"# {filename}\n{text}")

    return "\n\n".join(parts)


# ─── Real Project Context (caminho real do usuário) ────────────────────────────

# Registro em memória do workspace real atual (caminho absoluto na máquina do usuário)
_real_workspace: dict = {"path": None, "name": None, "tree": None, "registered_at": 0.0}

IGNORE_DIRS  = {".git", "node_modules", "__pycache__", ".venv", "venv",
                "dist", "build", ".next", "target", ".cache", "coverage"}
IGNORE_EXTS  = {".exe", ".dll", ".so", ".dylib", ".bin", ".pyc",
                ".lock", ".log", ".map", ".min.js", ".min.css"}
MAX_TREE_FILES = 60   # limite de arquivos na árvore exibida ao modelo (menor = menos tokens)


def _scan_dir_tree(root: str, max_files: int = MAX_TREE_FILES) -> list[str]:
    """Retorna lista de caminhos relativos (limitada) do diretório root.
    Usa os.walk com onerror silencioso para tolerar symlinks quebrados no Windows."""
    import os as _os
    root_path = Path(root)
    lines: list[str] = []

    def _onerror(err):
        pass  # ignora erros de acesso em symlinks/junctions

    for dirpath, dirnames, filenames in _os.walk(root, onerror=_onerror):
        if len(lines) >= max_files:
            lines.append(f"  ... (mais arquivos não listados — limite {max_files})")
            break
        dp = Path(dirpath)
        # Remove dirs ignorados in-place para não descer neles
        dirnames[:] = [d for d in sorted(dirnames) if d not in IGNORE_DIRS]
        try:
            rel_dir = dp.relative_to(root_path)
        except ValueError:
            continue
        depth = len(rel_dir.parts)
        prefix = "  " * depth
        if depth > 0:
            lines.append(f"{'  ' * (depth-1)}📁 {dp.name}/")
        for fname in sorted(filenames):
            if len(lines) >= max_files:
                break
            if Path(fname).suffix.lower() in IGNORE_EXTS:
                continue
            lines.append(f"{prefix}📄 {fname}")

    return lines


def build_real_project_context(real_path: str) -> str:
    """Constrói o bloco de contexto do projeto real para injetar no system prompt."""
    p = Path(real_path)
    if not p.exists() or not p.is_dir():
        return ""

    name    = p.name
    tree    = _scan_dir_tree(real_path)
    import os as _os_rpc
    n_files = 0
    for _dp, _dd, _df in _os_rpc.walk(real_path, onerror=lambda e: None):
        _dd[:] = [d for d in _dd if d not in IGNORE_DIRS]
        n_files += len(_df)

    # Detecta stack pelo conteúdo
    stack_hints: list[str] = []
    for marker, label in [
        ("package.json",  "Node.js/JavaScript"),
        ("Cargo.toml",    "Rust"),
        ("go.mod",        "Go"),
        ("requirements.txt", "Python"),
        ("pyproject.toml", "Python"),
        ("pom.xml",       "Java/Maven"),
        ("build.gradle",  "Java/Gradle"),
        ("Anchor.toml",   "Solana/Anchor"),
        ("hardhat.config.*", "Ethereum/Hardhat"),
        ("foundry.toml",  "Ethereum/Foundry"),
    ]:
        if any(p.glob(marker)):
            stack_hints.append(label)

    import platform as _plat
    is_win = _plat.system() == "Windows"
    path_note = (
        "ATENÇÃO: caminho no formato Windows (barras invertidas). "
        "NÃO converta para formato WSL (/mnt/c/...) — o backend roda em Windows nativo."
    ) if is_win else ""

    tree_str = "\n".join(tree) if tree else "  (pasta vazia)"

    ctx = f"""## ══════════════════════════════════════════
## WORKSPACE ATIVO — {name}
## ══════════════════════════════════════════

CAMINHO EXATO DO PROJETO (use este em TODAS as ferramentas):
  {real_path}

Stack: {", ".join(stack_hints) if stack_hints else "desconhecido"}
Arquivos: ~{n_files}
{path_note}

### REGRAS OBRIGATÓRIAS — LEIA ANTES DE AGIR:

1. **NÃO PERGUNTE** onde está o projeto — você já sabe: `{real_path}`
2. **NÃO chame allow_dir** — este caminho já está pré-autorizado pelo sistema.
3. Use EXATAMENTE `{real_path}` em todos os parâmetros `path` das ferramentas.
4. Para abrir um arquivo, use: `{real_path}\\arquivo.ext` (não use caminhos relativos).
5. NÃO invente caminhos WSL como /mnt/c/... — isso causará erro de acesso.

### Estrutura do projeto:
{tree_str}

### Como usar as ferramentas:
- list_dir: path="{real_path}"
- read_file: path="{real_path}\\src\\arquivo.ts"
- search_files: path="{real_path}", pattern="*.ts"
- run_command: cwd="{real_path}", cmd="npm run build"

Você está trabalhando NESTE REPOSITÓRIO. Comece imediatamente sem pedir confirmação de caminho."""
    return ctx


def build_system_prompt(mode: str = "dev", real_workspace_path: str | None = None) -> str:
    mode_file = f"{mode}.md"
    mode_path = PROMPTS_DIR / "modes" / mode_file
    if not mode_path.exists():
        mode_path = PROMPTS_DIR / "modes" / "dev.md"

    # Contexto do workspace real (caminho absoluto do projeto do usuário)
    real_ctx = ""
    if real_workspace_path:
        real_ctx = build_real_project_context(real_workspace_path)
    elif _real_workspace["path"]:
        # Usa o último workspace registrado via /api/workspace/register
        real_ctx = build_real_project_context(_real_workspace["path"])

    parts = [
        read_text_file(PROMPTS_DIR / "identity.md"),
        read_text_file(PROMPTS_DIR / "rules.md"),
        read_text_file(PROMPTS_DIR / "memory-viva.md"),
        read_text_file(PROMPTS_DIR / "voice-personality.md"),
        read_text_file(PROMPTS_DIR / "workstyle.md"),
        read_text_file(PROMPTS_DIR / "skills.md"),   # skills de construção com auto-seleção
        read_text_file(mode_path),
        build_workspace_prompt(get_active_workspace()),
        real_ctx,   # contexto do projeto real sempre ao final — maior prioridade
    ]
    return "\n\n".join(part for part in parts if part)


def get_client() -> OpenAI:
    """Retorna cliente OpenAI-compatible baseado no LUNA_MODEL configurado.
    Suporta OpenAI, xAI (Grok) e qualquer provedor OpenAI-compat.
    Para Anthropic, use get_router() do llm_router diretamente.
    """
    model = os.getenv("LUNA_MODEL", "gpt-4o").strip().lower()

    # xAI / Grok
    if model.startswith("grok"):
        key = os.getenv("XAI_API_KEY", os.getenv("GROK_API_KEY", "")).strip()
        if not key:
            raise HTTPException(status_code=500, detail="XAI_API_KEY not configured")
        return OpenAI(api_key=key, base_url="https://api.x.ai/v1")

    # OpenAI padrão
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
    return OpenAI(api_key=api_key)


def _is_anthropic_model(model: str) -> bool:
    return model.lower().startswith("claude")


# ─── Roteamento Inteligente de Modelos ────────────────────────────────────────
# Mapeia tipos de tarefa → melhor modelo disponível, priorizando:
#   - FREE first (Groq) para triage/simples
#   - Grok-3 para código/web3/raciocínio rápido
#   - Claude Sonnet para security/bounty/análise profunda
#   - Claude Opus para tarefas máximas (raras, sob demanda)

_TASK_KEYWORDS = {
    "triage": {
        "patterns": ["olá", "oi ", "hello", "hi ", "bom dia", "boa tarde", "boa noite",
                     "obrigado", "thanks", "ok ", "sim ", "não ", "certo", "entendido"],
        # Preferência: xAI grok-3-mini > OpenAI gpt-4o-mini > Groq llama (rate limit agressivo)
        "model": "grok-3-mini",
        "provider_key": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
        "max_tokens": 512,
    },
    "security": {
        "patterns": ["vulnerabilidade", "exploit", "bug bounty", "immunefi", "ctf",
                     "reentrancy", "overflow", "audit", "auditoria", "smart contract",
                     "solidity", "anchor", "cve", "pentest", "xss", "sqli",
                     "injection", "bypass", "privilege", "escalation", "poc", "payload"],
        "model": "claude-sonnet-4-6",
        "provider_key": "ANTHROPIC_API_KEY",
        "max_tokens": 8192,
    },
    "web3": {
        "patterns": ["solana", "ethereum", "blockchain", "defi", "nft", "wallet",
                     "transaction", "on-chain", "rpc", "helius", "phantom", "usdc",
                     "token", "mint", "stake", "program", "idl", "anchor", "spl",
                     "raydium", "jupiter", "airdrop", "lamport"],
        "model": "grok-3",
        "provider_key": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
        "max_tokens": 8192,
    },
    "mobile": {
        "patterns": ["react native", "expo", "flutter", "app mobile", "dapp mobile",
                     "ios", "android", "mobile wallet", "solana mobile", "defi app",
                     "wallet app", "swap app", "portfolio crypto", "nft viewer",
                     "mobile wallet adapter", "phantom mobile", "solflare",
                     # launchpad / token launcher
                     "launchpad", "pump.fun", "bonding curve", "raydium launchlab",
                     "meteora dbc", "moonshot", "token launcher", "memecoin platform",
                     "criar token", "sign in with solana", "jupiter mobile", "pyth mobile"],
        "model": "grok-3",
        "provider_key": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
        "max_tokens": 8192,
    },
    "code": {
        "patterns": ["código", "code", "função", "function", "classe", "class",
                     "implementar", "implement", "debug", "erro", "error", "bug",
                     "typescript", "python", "rust", "javascript", "react", "fastapi",
                     "script", "algoritmo", "algorithm", "refactor", "fix", "corrigir",
                     "electron", "vite", "npm", "pip", "deploy"],
        "model": "grok-3",
        "provider_key": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
        "max_tokens": 8192,
    },
    "analysis": {
        "patterns": ["analise", "análise", "analyze", "analys", "research", "pesquisa",
                     "estratégia", "strategy", "plano", "plan", "relatório", "report",
                     "comparar", "compare", "diferença", "difference", "resumo", "summary",
                     "explique", "explain", "como funciona", "how does"],
        "model": "claude-sonnet-4-6",
        "provider_key": "ANTHROPIC_API_KEY",
        "max_tokens": 4096,
    },
}


def _resolve_ollama_model() -> tuple[str, str, int]:
    """
    Zero-Cloud Mode: resolve modelo Ollama local disponível.
    Levanta RuntimeError com mensagem amigável se Ollama não estiver rodando
    ou sem modelos instalados — nunca roteia para nuvem silenciosamente.
    """
    import httpx as _hx
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434/v1")
    # Remove /v1 para construir URL base da API de tags do Ollama
    ollama_base = ollama_url.rstrip("/").removesuffix("/v1")
    try:
        resp = _hx.get(f"{ollama_base}/api/tags", timeout=3)
        resp.raise_for_status()
        models = resp.json().get("models", [])
    except Exception as exc:
        raise RuntimeError(
            "🔒 Zero-Cloud Mode ativo mas Ollama não respondeu. "
            "Inicie o Ollama (ollama.ai) e instale um modelo:\n"
            "  ollama pull llama3.1\n"
            f"(Detalhe técnico: {exc})"
        ) from exc

    if not models:
        raise RuntimeError(
            "🔒 Zero-Cloud Mode ativo mas nenhum modelo Ollama instalado. "
            "Execute no terminal: ollama pull llama3.1"
        )

    # Preferência de qualidade: modelos maiores/mais capazes primeiro
    # Cobre todos os formatos que o Ollama usa: "llama3.2", "llama3.2:3b", "llama3.2:latest", etc.
    preferred = [
        "llama3.3", "llama3.1:70b", "llama3.1:8b", "llama3.1",
        "llama3.2:3b", "llama3.2", "llama3:latest", "llama3",
        "mistral", "deepseek-coder", "deepseek", "gemma2", "gemma",
        "phi3", "phi", "qwen2", "qwen", "codellama",
    ]
    chosen = models[0]["name"]  # fallback: primeiro instalado
    for pref in preferred:
        match = next((m["name"] for m in models if m["name"].startswith(pref)), None)
        if match:
            chosen = match
            break

    logger.info(f"[zero-cloud] 🔒 Roteando para Ollama local: {chosen}")
    return chosen, ollama_url, 4096


def smart_route_model(message: str) -> tuple[str, str, int]:
    """
    Analisa a mensagem e retorna (model_id, base_url_or_provider, max_tokens).
    base_url_or_provider: "anthropic" para Anthropic SDK, ou a base_url para OpenAI-compat.

    Prioridade de detecção: security > web3 > code > analysis > triage > default

    ZERO-CLOUD: se _runtime_config["zero_cloud_mode"] estiver ativo, SEMPRE retorna
    Ollama local — nunca roteia para provedores cloud.
    """
    # ── Zero-Cloud override: bloqueia qualquer roteamento cloud ──────────────
    if _runtime_config.get("zero_cloud_mode", False):
        return _resolve_ollama_model()
    # ─────────────────────────────────────────────────────────────────────────

    msg_lower = message.lower()
    msg_len   = len(message.split())

    # Override: mensagem muito curta (<= 8 palavras) → triage rápido
    # Preferência: xAI grok-3-mini > OpenAI gpt-4o-mini > Groq llama (rate limit agressivo)
    if msg_len <= 8:
        xai_key    = os.getenv("XAI_API_KEY", "").strip()
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        groq_key   = os.getenv("GROQ_API_KEY", "").strip()
        if xai_key:
            return "grok-3-mini", "https://api.x.ai/v1", 512
        if openai_key:
            return "gpt-4o-mini", None, 512
        if groq_key:
            return "llama-3.1-8b-instant", "https://api.groq.com/openai/v1", 512

    # Detecção por palavra-chave (ordem de prioridade)
    for task_name in ("security", "mobile", "web3", "code", "analysis", "triage"):
        task = _TASK_KEYWORDS[task_name]
        if any(kw in msg_lower for kw in task["patterns"]):
            pkey = task["provider_key"]
            env_val = os.getenv(pkey, "").strip()
            if not env_val:
                continue  # chave não configurada — tenta próxima tarefa
            if pkey == "ANTHROPIC_API_KEY":
                return task["model"], "anthropic", task["max_tokens"]
            base_url = task.get("base_url", "")
            return task["model"], base_url, task["max_tokens"]

    # Default: usa LUNA_MODEL configurado
    default_model = os.getenv("LUNA_MODEL", "grok-3").strip() or "grok-3"
    if default_model.startswith("claude"):
        return default_model, "anthropic", 4096
    if default_model.startswith("grok"):
        xai_key = os.getenv("XAI_API_KEY", "").strip()
        if xai_key:
            return default_model, "https://api.x.ai/v1", 8192
    # Fallback OpenAI
    return default_model, "", 4096


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "agent"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list["ChatMessage"] = Field(default_factory=list)
    session_id: str | None = None
    # Supabase Auth user ID — quando presente, usado no pay-flow em vez do session_id.
    # Garante que os Grains ficam vinculados à conta, não ao dispositivo.
    user_id: str | None = None
    mode: str = "dev"
    # Modelo selecionado pelo usuário no frontend (ex: "grok-3", "claude-sonnet-4-6", "auto")
    model: str | None = None
    # Caminho absoluto do workspace real do usuário (ex: "C:\Dev\bags-shield-api")
    workspace_path: str | None = None


class SpeakRequest(BaseModel):
    text: str


ChatMessage.model_rebuild()
ChatRequest.model_rebuild()


def normalize_history(history: list[ChatMessage], limit: int = 8) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []

    for item in history[-limit:]:
        content = (item.content or "").strip()
        if not content:
            continue

        role = "assistant" if item.role in ("assistant", "agent") else "user"
        normalized.append({
            "role": role,
            "content": content,
        })

    return normalized


def recent_user_messages(history: list[ChatMessage], limit: int = 6) -> list[str]:
    items: list[str] = []
    for item in history[-limit:]:
        if item.role != "user":
            continue
        content = (item.content or "").strip()
        if content:
            items.append(content)
    return items


def maybe_answer_identity_question(message: str, history: list[ChatMessage]) -> str | None:
    q = " ".join((message or "").lower().split())
    q = q.replace("você", "voce")
    triggers = (
        "qual nome eu pedi para voce lembrar",
        "qual nome pedi pra voce lembrar",
        "que nome eu pedi para voce lembrar",
        "que nome pedi pra voce lembrar",
    )
    if not any(t in q for t in triggers):
        return None

    recent = recent_user_messages(history, limit=6)
    joined = "\n".join(recent + [message]).lower()
    joined = joined.replace("você", "voce")

    if (
        "seu nome e luna" in joined
        or "seu nome é luna" in joined
        or "voce e luna" in joined
        or "voce é luna" in joined
        or "você e luna" in joined
        or "você é luna" in joined
    ):
        return "Você pediu para eu lembrar que meu nome é Luna."

    if (
        "meu nome e cleiton" in joined
        or "meu nome é cleiton" in joined
        or "me chamo cleiton" in joined
    ):
        return "Você pediu para eu lembrar que seu nome é Cleiton."

    return "Para deixar explícito: meu nome é Luna e o usuário é Cleiton."


def is_safe_mode_triggered(message: str, history: list[ChatMessage]) -> bool:
    if not SAFE_MODE_ENABLED:
        return False

    current = " ".join((message or "").lower().split())
    if not current:
        return False

    recent_user: list[str] = []
    for item in history[-6:]:
        if item.role != "user":
            continue
        text = " ".join((item.content or "").lower().split())
        if text:
            recent_user.append(text)

    seq = recent_user.copy()
    if not seq or seq[-1] != current:
        seq.append(current)

    streak = 0
    for text in reversed(seq):
        if text == current:
            streak += 1
        else:
            break

    return streak >= SAFE_MODE_SAME_MESSAGE_THRESHOLD


def safe_mode_reply() -> str:
    return "Entrei em modo seguro para evitar loop e erro em cascata. Vi repetição da mesma solicitação e vou parar a cadeia aqui. O próximo passo mínimo é revisar o estado atual antes de tentar de novo."


def workspace_fail_closed_reply(workspace_info: dict) -> str:
    missing = workspace_info.get("missing", [])
    missing_text = ", ".join(missing) if missing else "arquivos obrigatórios ausentes"
    return f"Entrei em modo seguro porque o workspace ativo está incompleto. Antes de continuar, preciso que o estado do projeto seja corrigido. Arquivos faltando: {missing_text}."


@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "premium.html")


@app.get("/classic")
def classic():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/payflow")
def payflow():
    return FileResponse(STATIC_DIR / "payflow.html")


@app.get("/health")
def health():
    identity = read_text_file(PROMPTS_DIR / "identity.md")
    rules = read_text_file(PROMPTS_DIR / "rules.md")
    memory = read_text_file(PROMPTS_DIR / "memory-viva.md")
    active_ws = get_active_workspace()
    workspace_info = inspect_workspace(active_ws)
    workspace_context = build_workspace_prompt(active_ws)

    return {
        "success": True,
        "response": {
            "status": "ok",
            "identity_loaded": bool(identity),
            "rules_loaded": bool(rules),
            "memory_loaded": bool(memory),
            "chat_history_enabled": True,
            "workspace_active": active_ws,
            "workspace_loaded": bool(workspace_context),
            "workspace_file_count": workspace_info["file_count"],
            "workspace_all_required_present": workspace_info["all_required_present"],
            "workspace_found_files": workspace_info["found"],
            "workspace_missing_files": workspace_info["missing"],
            "safe_mode_enabled": SAFE_MODE_ENABLED,
            "safe_mode_same_message_threshold": SAFE_MODE_SAME_MESSAGE_THRESHOLD
        }
    }


@app.on_event("startup")
async def agent_bootstrap():
    ensure_agent_files()
    try:
        cfg = load_config()
        set_safe_base_dirs(cfg.safe_base_dirs)
    except Exception:
        pass
    # ── Inicia o retry job de pending_credits ─────────────────────────────────
    # Roda em background — credita automaticamente qualquer Grain travado por
    # falha transitória de rede/Supabase durante o confirm-tx.
    import asyncio as _asyncio
    try:
        from app.payments.retry_job import run_retry_loop
        _asyncio.create_task(run_retry_loop())
        import logging as _log
        _log.getLogger("luna.main").info("✅ RetryJob de pending_credits iniciado")
    except Exception as _e:
        import logging as _log
        _log.getLogger("luna.main").warning(f"⚠️ RetryJob não iniciado: {_e}")


@app.get("/agent/config")
def get_agent_config():
    ensure_agent_files()
    cfg = load_config()
    return {
        "success": True,
        "response": cfg.model_dump(),
    }


@app.post("/agent/config")
def save_agent_config(cfg: AgentConfig):
    ensure_agent_files()
    save_config(cfg)
    set_safe_base_dirs(cfg.safe_base_dirs)
    return {
        "success": True,
        "response": cfg.model_dump(),
    }


@app.post("/agent/plan")
def agent_plan(payload: AgentRequest):
    ensure_agent_files()
    cfg = load_config()

    if payload.mode:
        cfg.mode = payload.mode
    if payload.target_root:
        cfg.target_root = payload.target_root

    save_config(cfg)
    set_safe_base_dirs(cfg.safe_base_dirs)

    runtime = AgentRuntime(cfg)
    plan = runtime.plan(
        objective=payload.objective,
        session_id=payload.session_id,
    )

    return {
        "success": True,
        "response": plan.model_dump(),
    }


@app.get("/agent/state")
def get_agent_state():
    ensure_agent_files()
    cfg = load_config()
    plan = load_last_plan()

    return {
        "success": True,
        "response": {
            "config": cfg.model_dump(),
            "last_plan": plan.model_dump() if plan else None,
        },
    }


class ExecuteRequest(BaseModel):
    action_id: str = ""
    session_id: str = ""


@app.post("/agent/execute")
def agent_execute(payload: ExecuteRequest = Body(default_factory=ExecuteRequest)):
    ensure_agent_files()
    cfg = load_config()
    set_safe_base_dirs(cfg.safe_base_dirs)

    plan = load_last_plan()
    if not plan or not plan.proposed_actions:
        raise HTTPException(status_code=400, detail="nenhum plano disponível para execução")

    # Resolve action: por action_id ou primeira ação do plano
    aid = (payload.action_id or "").strip()
    if aid:
        action = next((a for a in plan.proposed_actions if a.action_id == aid), None)
        if not action:
            raise HTTPException(status_code=404, detail=f"action_id '{aid}' não encontrado no plano")
    else:
        action = plan.proposed_actions[0]

    # Fail-closed: ação com aprovação obrigatória não aprovada → bloqueia
    if action.needs_approval and not is_action_approved(action.action_id):
        _write_audit(
            action_id=action.action_id, tool=action.tool, risk=action.risk,
            decision="blocked", session_id=plan.session_id, target=str(action.args),
            error="aprovação não concedida",
        )
        raise HTTPException(
            status_code=403,
            detail=f"ação '{action.action_id}' exige aprovação explícita antes de executar",
        )

    runtime = AgentRuntime(cfg)
    result = runtime.execute(action, session_id=payload.session_id or plan.session_id)

    decision = "approved" if action.needs_approval else "auto_executed"
    _write_audit(
        action_id=result.action_id, tool=result.tool, risk=action.risk,
        decision=decision if result.ok else "failed",
        session_id=result.session_id,
        target=str(action.args),
        result_ok=result.ok,
        error=result.error,
    )

    return {
        "success": True,
        "response": result.model_dump(),
    }


@app.post("/agent/approve")
def agent_approve(payload: ApprovalDecision):
    ensure_agent_files()
    plan = load_last_plan()
    if not plan:
        raise HTTPException(status_code=400, detail="nenhum plano ativo")

    action = next((a for a in plan.proposed_actions if a.action_id == payload.action_id), None)
    if not action:
        raise HTTPException(status_code=404, detail=f"action_id '{payload.action_id}' não encontrado")

    if not action.needs_approval:
        raise HTTPException(status_code=400, detail="ação não requer aprovação — execute diretamente")

    approve_action(payload.action_id, session_id=payload.session_id, approved=payload.approved)
    decision_str = "approved" if payload.approved else "denied"

    _write_audit(
        action_id=action.action_id, tool=action.tool, risk=action.risk,
        decision=decision_str, session_id=payload.session_id,
        target=str(action.args),
    )

    return {
        "success": True,
        "response": {
            "action_id": payload.action_id,
            "decision":  decision_str,
            "tool":      action.tool,
            "risk":      action.risk,
        },
    }


@app.get("/agent/queue")
def agent_queue():
    ensure_agent_files()
    plan = load_last_plan()
    if not plan:
        return {"success": True, "response": {"pending": [], "auto": [], "objective": ""}}

    pending: list[dict] = []
    auto:    list[dict] = []
    for act in plan.proposed_actions:
        d = act.model_dump()
        d["already_approved"] = is_action_approved(act.action_id)
        if act.needs_approval:
            pending.append(d)
        else:
            auto.append(d)

    return {
        "success": True,
        "response": {
            "session_id": plan.session_id,
            "objective":  plan.objective,
            "pending":    pending,
            "auto":       auto,
        },
    }


@app.get("/agent/preview/{action_id}")
def agent_preview_action(action_id: str):
    ensure_agent_files()
    cfg   = load_config()
    plan  = load_last_plan()
    if not plan:
        raise HTTPException(status_code=404, detail="nenhum plano disponível")

    action = next((a for a in plan.proposed_actions if a.action_id == action_id), None)
    if not action:
        raise HTTPException(status_code=404, detail=f"action_id '{action_id}' não encontrado")

    runtime = AgentRuntime(cfg)
    preview = runtime.preview(action)
    return {"success": True, "response": preview}


@app.get("/agent/audit")
def agent_audit_log(limit: int = 30):
    ensure_agent_files()
    entries = load_audit_log(limit=limit)
    return {"success": True, "response": {"entries": entries, "count": len(entries)}}


@app.post("/chat")
def chat(payload: ChatRequest):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    session_id = (getattr(payload, "session_id", None) or "").strip() or f"session-{os.urandom(4).hex()}"

    # Prioridade: modelo enviado pelo frontend > LUNA_MODEL env > grok-3
    _req_model  = (getattr(payload, "model", None) or "").strip()
    _cfg_model  = os.getenv("LUNA_MODEL", "grok-3").strip() or "grok-3"
    _raw_model  = _req_model or _cfg_model
    mode = getattr(payload, "mode", "dev") or "dev"

    # ── Zero-Cloud override ───────────────────────────────────────────────────
    if _runtime_config.get("zero_cloud_mode", False):
        try:
            model, _smart_base_url, _smart_max_tokens = _resolve_ollama_model()
            logger.info(f"[chat] zero-cloud 🔒 → {model}")
        except RuntimeError as _zc_err:
            return {
                "success": False,
                "response": {"text": str(_zc_err), "session_id": session_id},
            }
    # Roteamento inteligente: "auto" analisa mensagem e escolhe melhor modelo/provider
    elif _raw_model.lower() == "auto":
        model, _smart_base_url, _smart_max_tokens = smart_route_model(payload.message)
        logger.info(f"[chat] auto-route → {model} ({_smart_base_url or 'openai-compat'})")
    else:
        model = _raw_model
        _smart_base_url = ""
        _smart_max_tokens = int(os.getenv("LUNA_MAX_TOKENS", "4096"))
    # Workspace real: do request > último registrado via /api/workspace/register
    # NOTA: NÃO escrevemos no global _real_workspace aqui — isso causaria race condition
    # entre requests concorrentes. Apenas o endpoint /api/workspace/register escreve no global.
    _real_ws_path = (getattr(payload, "workspace_path", None) or "").strip() or None

    system_prompt = build_system_prompt(mode, real_workspace_path=_real_ws_path)
    short_history = normalize_history(payload.history, limit=8)
    active_ws = get_active_workspace()
    workspace_info = inspect_workspace(active_ws)

    # Phase 2 security guards pipeline (identity, scope, safe_mode context)
    guard_result, security_safe_mode = run_all_guards(
        message    = message,
        session_id = session_id,
        project_id = active_ws,
    )
    if guard_result.blocked:
        return {
            "success": True,
            "response": {
                "text": guard_result.response or "Bloqueado pelo sistema de segurança.",
                "session_id": session_id,
            }
        }

    # Salva mensagem do usuário na memória persistente
    stm_add(session_id, "user", message)
    ltm_add(active_ws, session_id, "user", message, safe_mode=security_safe_mode)

    if not workspace_info["all_required_present"]:
        append_structured_log(
            event=EventType.FAIL_CLOSED,
            trigger="workspace_incomplete",
            action="blocked_chat_response",
            result="blocked",
            session_id=session_id,
            project_id=active_ws,
            detail={
                "missing": workspace_info["missing"],
                "message": message,
                "session_id": session_id,
            },
            safe_mode=True,
            checkpoint=False,
            is_audit=True,
        )
        return {
            "success": True,
            "response": {
                "text": workspace_fail_closed_reply(workspace_info),
                "session_id": session_id,
            }
        }

    if is_safe_mode_triggered(message, payload.history):
        append_structured_log(
            event=EventType.SAFE_MODE_TRIGGER,
            trigger="same_message_streak",
            action="blocked_loop_and_returned_safe_reply",
            result="blocked",
            session_id=session_id,
            project_id=active_ws,
            detail={
                "message": message,
                "session_id": session_id,
            },
            safe_mode=True,
            checkpoint=False,
            is_audit=True,
        )
        return {
            "success": True,
            "response": {
                "text": safe_mode_reply(),
                "session_id": session_id,
            }
        }

    guard_answer = maybe_answer_identity_question(message, payload.history)
    if guard_answer:
        append_structured_log(
            event=EventType.IDENTITY_GUARD,
            trigger="identity_question_detected",
            action="returned_guard_answer",
            result="ok",
            session_id=session_id,
            project_id=active_ws,
            detail={
                "message": message,
                "session_id": session_id,
            },
            safe_mode=False,
            checkpoint=False,
            is_audit=True,
        )
        return {
            "success": True,
            "response": {
                "text": guard_answer,
                "session_id": session_id,
            }
        }

    # ── Pay-Flow: verifica saldo de Grains antes de chamar o modelo ──────────
    # Prioridade: Supabase account ID (cross-device) > session_id (fallback por dispositivo)
    _payflow_user = (getattr(payload, "user_id", None) or "").strip() or session_id
    _payflow_grains_used: float = 0.0
    _payflow_enabled = bool(os.getenv("SUPABASE_URL", "").strip())

    # Detecta provider real a partir do nome do modelo
    def _detect_provider(m: str) -> str:
        m = m.lower()
        if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3"):
            return "openai"
        if m.startswith("claude"):
            return "claude"
        if m.startswith("grok"):
            return "xai"
        if "llama" in m or "mixtral" in m or "mistral" in m:
            # distingue groq vs together pelo env
            return "groq" if os.getenv("GROQ_API_KEY") else "together"
        if m.startswith("gemini"):
            return "gemini"
        return "openai"

    _payflow_provider = _detect_provider(model)

    if _payflow_enabled:
        try:
            from app.payments.cost_controller import get_cost_controller, InsufficientGrainsError
            _cc = get_cost_controller()
            _cc.check_and_reserve(_payflow_user, estimated_tokens_in=500, estimated_tokens_out=800, provider=_payflow_provider)
        except Exception as _pe:
            if "InsufficientGrains" in type(_pe).__name__ or "Saldo insuficiente" in str(_pe):
                return {
                    "success": False,
                    "response": {
                        "text": f"Saldo insuficiente de Luna Grains. Acesse /payflow para recarregar via USDC/Solana. Detalhe: {_pe}",
                        "session_id": session_id,
                        "error_code": "INSUFFICIENT_GRAINS",
                    }
                }
            # Supabase nao configurado ou erro de conexao — continua sem cobrar
            pass

    client = get_client()
    
    # Integra memória de longo e curto prazo usando a função do serviço de memória
    from app.services.memory import build_memory_context
    memory_history = build_memory_context(active_ws, session_id, safe_mode=security_safe_mode)
    
    # Se a API enviar um histórico via payload, nós combinamos, dando preferência para a memória persistida
    combined_history = short_history.copy()
    if memory_history:
        # Simplificação: usa o memory_history como histórico principal, pois ele já contém STM e LTM
        combined_history = memory_history

    request_input = [
        {"role": "system", "content": system_prompt},
        *combined_history,
        # A última mensagem do usuário já foi adicionada ao STM acima, 
        # mas como o STM a retorna, não precisamos repeti-la no request_input 
        # a menos que memory_history não a inclua (o que inclui, pois stm_add foi chamado).
        # Para evitar duplicação, vamos remover a última mensagem do combined_history se for a atual
    ]
    
    if combined_history and combined_history[-1].get("content") == message:
        request_input = [
            {"role": "system", "content": system_prompt},
            *combined_history[:-1],
            {"role": "user", "content": message},
        ]
    else:
        request_input = [
            {"role": "system", "content": system_prompt},
            *combined_history,
            {"role": "user", "content": message},
        ]

    try:
        # ── Roteamento por provider ───────────────────────────────────────────
        # Determina se é Anthropic (via smart route ou modelo direto)
        _use_anthropic = (_smart_base_url == "anthropic") or _is_anthropic_model(model)

        if _use_anthropic:
            # Anthropic SDK nativo
            import anthropic as _ant
            _ant_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
            if not _ant_key:
                raise RuntimeError("ANTHROPIC_API_KEY não configurada")
            _ant_client = _ant.Anthropic(api_key=_ant_key)
            _sys = [m["content"] for m in request_input if m["role"] == "system"]
            _msgs = [m for m in request_input if m["role"] != "system"]
            _ant_resp = _ant_client.messages.create(
                model=model,
                max_tokens=_smart_max_tokens,
                system="\n\n".join(_sys) if _sys else None,
                messages=_msgs,
            )
            text = (_ant_resp.content[0].text if _ant_resp.content else "").strip()
            _tokens_in_est  = getattr(_ant_resp.usage, "input_tokens", 500)
            _tokens_out_est = getattr(_ant_resp.usage, "output_tokens", 300)
        else:
            # OpenAI-compat (OpenAI, xAI/Grok, Groq, Together, etc.)
            # Monta client com base_url correta (smart route ou detectada por modelo)
            if _smart_base_url:
                _compat_base = _smart_base_url
            elif model.startswith("grok"):
                _compat_base = "https://api.x.ai/v1"
            elif model.startswith("llama") or model.startswith("mixtral"):
                _groq_key = os.getenv("GROQ_API_KEY", "").strip()
                _compat_base = "https://api.groq.com/openai/v1" if _groq_key else ""
            else:
                _compat_base = ""

            if _compat_base:
                # Escolhe a API key correta pelo base_url
                if "x.ai" in _compat_base:
                    _compat_key = os.getenv("XAI_API_KEY", os.getenv("GROK_API_KEY", "")).strip()
                elif "groq.com" in _compat_base:
                    _compat_key = os.getenv("GROQ_API_KEY", "").strip()
                elif "together" in _compat_base:
                    _compat_key = os.getenv("TOGETHER_API_KEY", "").strip()
                else:
                    _compat_key = os.getenv("OPENAI_API_KEY", "").strip()
                from openai import OpenAI as _OAI
                _compat_client = _OAI(api_key=_compat_key, base_url=_compat_base)
            else:
                _compat_client = client  # usa client padrão (OpenAI)

            # Fallback chain para xAI: grok-3 → grok-3-beta → grok-2-1212
            _xai_fallback = []
            if "x.ai" in _compat_base and model in ("grok-3", "grok-3-mini"):
                _xai_fallback = [model, "grok-3-beta", "grok-3-mini", "grok-2-1212"]
            else:
                _xai_fallback = [model]

            response = None
            _final_model = model
            for _try_model in _xai_fallback:
                try:
                    response = _compat_client.chat.completions.create(
                        model=_try_model,
                        messages=request_input,
                        temperature=float(os.getenv("LUNA_TEMPERATURE", "0.4")),
                        max_tokens=_smart_max_tokens,
                    )
                    _final_model = _try_model
                    if _try_model != model:
                        logger.warning(f"[chat] xAI fallback: {model} → {_try_model}")
                    break
                except Exception as _e:
                    _emsg = str(_e)
                    if "404" in _emsg or "model_not_found" in _emsg or "does not exist" in _emsg:
                        logger.warning(f"[chat] modelo {_try_model} não disponível, tentando fallback...")
                        continue
                    raise  # outros erros: relança
            if response is None:
                raise RuntimeError(f"Nenhum modelo xAI disponível: {_xai_fallback}")
            text = (response.choices[0].message.content or "").strip()
            _usage = getattr(response, "usage", None)
            _tokens_in_est  = getattr(_usage, "prompt_tokens", 500) if _usage else 500
            _tokens_out_est = getattr(_usage, "completion_tokens", 300) if _usage else 300

        if not text:
            text = "Não consegui gerar uma resposta útil neste ciclo. Vou parar aqui para evitar inventar informação."

        if security_safe_mode:
            text = SAFE_MODE_PREFACE + text

        # Salva resposta na memória persistente
        stm_add(session_id, "assistant", text)
        ltm_add(active_ws, session_id, "assistant", text, safe_mode=security_safe_mode)

        # ── Pay-Flow: debita Grains pelo consumo real de tokens ──────────────
        if _payflow_enabled:
            try:
                _tokens_in  = _tokens_in_est
                _tokens_out = _tokens_out_est
                from app.payments.cost_controller import get_cost_controller
                _cc = get_cost_controller()
                _payflow_grains_used = _cc.debit(
                    user_id    = _payflow_user,
                    provider   = _payflow_provider,
                    tokens_in  = int(_tokens_in),
                    tokens_out = int(_tokens_out),
                    session_id = session_id,
                    operation  = "luna_chat_message",
                )
            except Exception:
                pass

        append_execution_log(
            active_ws,
            [
                "## Ciclo mínimo",
                f"- session_id: `{session_id}`",
                "- objetivo: responder ao pedido atual do usuário",
                "- ação: gerar uma única resposta de chat",
                "- resultado: resposta gerada com sucesso",
                "- parada: ciclo encerrado após 1 ação",
            ],
        )

        append_structured_log(
            event=EventType.CHAT_RESPONSE,
            trigger=message[:200],
            action="model_response_generated",
            result="ok",
            session_id=session_id,
            project_id=active_ws,
            detail={
                "model": model,
                "response_len": len(text),
                "history_len": len(short_history),
            },
            safe_mode=False,
            checkpoint=False,
        )

        return {
            "success": True,
            "response": {
                "text": text,
                "session_id": session_id,
            }
        }
    except Exception as e:
        append_execution_log(
            active_ws,
            [
                "## Ciclo mínimo",
                f"- session_id: `{session_id}`",
                "- objetivo: responder ao pedido atual do usuário",
                "- ação: gerar uma única resposta de chat",
                f"- resultado: erro ao consultar o modelo ({type(e).__name__})",
                "- parada: ciclo encerrado por falha controlada",
            ],
        )
        raise HTTPException(status_code=500, detail=f"OpenAI error: {e}")


@app.get("/chat/stream")
async def chat_stream(
    message:    str,
    session_id: str | None = None,
    mode:       str = "dev",
):
    """Streaming SSE: envia chunks da resposta da Luna em tempo real."""
    active_ws  = get_active_workspace()
    sid        = (session_id or "").strip() or f"stream-{os.urandom(4).hex()}"
    api_key    = os.getenv("OPENAI_API_KEY", "").strip()
    model      = os.getenv("LUNA_MODEL", "gpt-4o").strip() or "gpt-4o"

    async def generate():
        # Guards de segurança
        guard_result, security_safe_mode = run_all_guards(message, sid, active_ws)
        if guard_result.blocked:
            yield "data: " + json.dumps({"text": guard_result.response or "Bloqueado.", "done": True}) + "\n\n"
            return

        if security_safe_mode:
            yield "data: " + json.dumps({"text": SAFE_MODE_PREFACE, "done": False}) + "\n\n"

        system_prompt = build_system_prompt(mode)

        from app.services.memory import build_memory_context
        memory_history = build_memory_context(active_ws, sid, safe_mode=security_safe_mode)

        messages = [
            {"role": "system", "content": system_prompt},
            *memory_history,
            {"role": "user", "content": message},
        ]

        try:
            full_response = ""

            if _is_anthropic_model(model):
                # ── Anthropic streaming (thread pool via asyncio) ─────────────
                import asyncio
                import anthropic as _ant
                _ant_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
                if not _ant_key:
                    yield "data: " + json.dumps({"text": "ANTHROPIC_API_KEY não configurada.", "done": True}) + "\n\n"
                    return
                _ant_client = _ant.Anthropic(api_key=_ant_key)
                _sys_msgs = [m["content"] for m in messages if m["role"] == "system"]
                _chat_msgs = [m for m in messages if m["role"] != "system"]

                def _ant_stream_sync():
                    chunks = []
                    with _ant_client.messages.stream(
                        model=model,
                        max_tokens=int(os.getenv("LUNA_MAX_TOKENS", "4096")),
                        system="\n\n".join(_sys_msgs) if _sys_msgs else None,
                        messages=_chat_msgs,
                    ) as s:
                        for txt in s.text_stream:
                            chunks.append(txt)
                    return chunks

                chunks = await asyncio.get_event_loop().run_in_executor(None, _ant_stream_sync)
                for chunk in chunks:
                    if chunk:
                        full_response += chunk
                        yield "data: " + json.dumps({"text": chunk, "done": False}) + "\n\n"

            elif model.startswith("grok"):
                # ── xAI streaming ─────────────────────────────────────────────
                xai_key = os.getenv("XAI_API_KEY", os.getenv("GROK_API_KEY", "")).strip()
                if not xai_key:
                    yield "data: " + json.dumps({"text": "XAI_API_KEY não configurada.", "done": True}) + "\n\n"
                    return
                xai_async = AsyncOpenAI(api_key=xai_key, base_url="https://api.x.ai/v1")
                async with xai_async.chat.completions.stream(
                    model=model, messages=messages,
                ) as stream:
                    async for text_chunk in stream.text_stream:
                        if text_chunk:
                            full_response += text_chunk
                            yield "data: " + json.dumps({"text": text_chunk, "done": False}) + "\n\n"

            else:
                # ── OpenAI streaming ───────────────────────────────────────────
                if not api_key:
                    yield "data: " + json.dumps({"text": "OPENAI_API_KEY não configurada.", "done": True}) + "\n\n"
                    return
                async_client = AsyncOpenAI(api_key=api_key)
                async with async_client.chat.completions.stream(
                    model    = model,
                    messages = messages,
                ) as stream:
                    async for text_chunk in stream.text_stream:
                        if text_chunk:
                            full_response += text_chunk
                            yield "data: " + json.dumps({"text": text_chunk, "done": False}) + "\n\n"

            # Salva na memória
            stm_add(sid, "user", message)
            stm_add(sid, "assistant", full_response)
            ltm_add(active_ws, sid, "user", message, safe_mode=security_safe_mode)
            ltm_add(active_ws, sid, "assistant", full_response, safe_mode=security_safe_mode)

            append_structured_log(
                event      = EventType.STREAM_END,
                trigger    = message[:200],
                action     = "stream_response_complete",
                result     = "ok",
                session_id = sid,
                project_id = active_ws,
                detail     = {"response_len": len(full_response), "mode": mode},
            )

            yield "data: " + json.dumps({"text": "", "done": True, "session_id": sid}) + "\n\n"

        except Exception as e:
            # Python 3.12+: captura o nome antes de 'e' ser deletado ao sair do except
            _err_type = type(e).__name__
            _err_msg  = str(e)[:200]
            yield "data: " + json.dumps({"text": f"Erro no streaming: {_err_type} — {_err_msg}", "done": True}) + "\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ─── Agent streaming endpoint (com tool calls em tempo real) ─────────────────

class AgentStreamRequest(BaseModel):
    message:         str
    session_id:      str | None = None
    model:           str | None = None
    workspace_path:  str | None = None  # caminho real do projeto selecionado pelo usuário
    user_id:         str | None = None
    zero_cloud_mode: bool = False       # se True, força Ollama local independente do modelo pedido
    images:          list | None = None # imagens anexadas (vision)
    user_context:    str | None = None  # contexto manual digitado pelo usuário no painel Context


@app.post("/chat/agent/stream")
async def chat_agent_stream(body: AgentStreamRequest):
    """
    Streaming SSE com loop agêntico completo.
    Emite eventos:
      {"type":"tool_start","name":"...","args_summary":"..."}
      {"type":"tool_done","name":"...","result_summary":"..."}
      {"type":"tool_skipped","name":"..."}
      {"type":"text_chunk","text":"..."}
      {"type":"done","final_text":"...","tools_used":[...]}
      {"type":"error","message":"..."}
    """
    import asyncio
    import json as _json
    from openai import OpenAI as SyncOpenAI

    api_key  = os.getenv("OPENAI_API_KEY", "").strip()
    _raw_model_id = (body.model or os.getenv("LUNA_MODEL", "gpt-4o")).strip() or "gpt-4o"

    # ── Zero-Cloud override: força Ollama independente do modelo pedido ──────
    # Aceita tanto da config global quanto do campo da request (enviado pelo frontend)
    if body.zero_cloud_mode or _runtime_config.get("zero_cloud_mode", False):
        try:
            model_id, _zc_base_url, _ = _resolve_ollama_model()
        except RuntimeError as _zc_err:
            import json as _json
            async def _zc_error_stream():
                yield "data: " + _json.dumps({
                    "type": "error",
                    "message": str(_zc_err),
                }) + "\n\n"
            return StreamingResponse(_zc_error_stream(), media_type="text/event-stream")
        logger.info(f"[agent/stream] zero-cloud 🔒 → {model_id}")
    # Resolve "auto" para o melhor modelo disponível (apenas se não zero-cloud)
    elif _raw_model_id.lower() == "auto":
        model_id, _, _ = smart_route_model(body.message)
        logger.info(f"[agent/stream] auto-route → {model_id}")
    else:
        model_id = _raw_model_id
    sid      = (body.session_id or "").strip() or f"ui-{os.urandom(4).hex()}"

    # Detecta build mode aqui (fora do thread) para configurar timeout do SSE
    _BUILD_KW_FAST = [
        "crie", "cria", "criar", "construir", "construa", "build", "make",
        "desenvolver", "desenvolva", "gere", "gerar", "implemente", "implementar",
        "novo app", "nova ferramenta", "novo projeto", "do zero", "from scratch",
        "bounty tracker", "cli", "ferramenta em", "app em", "script",
    ]
    _outer_is_build = any(kw in body.message.lower() for kw in _BUILD_KW_FAST)
    # Build mode precisa de mais tempo: síntese final com 8192 tokens pode demorar 3-4 min
    _sse_timeout = 420.0 if _outer_is_build else 180.0

    # Import Luna's agent components
    # NOTA: NÃO importar app.cli aqui — usa 'rich' que pode não estar instalado no Windows
    try:
        from app.strategy import get_strategy_engine
        from app.tools.filesystem_tool import FilesystemTool
        from app.state_store import load_config
    except Exception as e:
        # Python 3.12+: 'e' é deletado ao sair do bloco except.
        # Closures lazy (como geradores async) falham se referenciarem 'e' diretamente.
        _import_err = f"{type(e).__name__}: {e}"
        async def _err():
            yield "data: " + _json.dumps({"type": "error", "message": f"Import error: {_import_err}"}) + "\n\n"
        return StreamingResponse(_err(), media_type="text/event-stream")

    # Shared queue for events between sync agent loop thread and async generator
    event_queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()  # get_event_loop() deprecated no Python 3.10+

    def put_event(evt: dict):
        loop.call_soon_threadsafe(event_queue.put_nowait, evt)

    def run_agent():
        """Runs the agent loop in a thread, emitting events via put_event."""
        import threading
        import platform as _platform
        try:
            config = load_config()

            # Paths cross-platform: Windows usa C:\ e pasta do usuário
            _home = str(Path.home())
            # Sempre inclui workspace selecionado pelo usuário
            _req_ws = (getattr(body, "workspace_path", None) or "").strip()

            # Se o frontend enviou um workspace válido e o global ainda não está populado
            # (ex: backend reiniciado sem re-registrar), atualiza o global automaticamente.
            # Isso garante que chamadas futuras com workspace_path=null ainda funcionem.
            if _req_ws and not _real_workspace["path"]:
                try:
                    _rws_p = Path(_req_ws)
                    if _rws_p.exists() and _rws_p.is_dir():
                        _real_workspace["path"]          = _req_ws
                        _real_workspace["name"]          = _rws_p.name
                        _real_workspace["registered_at"] = _time.time()
                except Exception:
                    pass

            if _platform.system() == "Windows":
                _base_dirs = [str(BASE_DIR), _home, r"C:\Dev", r"D:\Dev", r"C:\Users"]
                # Adiciona o workspace e seu pai
                if _req_ws:
                    _base_dirs.append(_req_ws)
                    _parent = str(Path(_req_ws).parent)
                    if _parent not in _base_dirs:
                        _base_dirs.append(_parent)
                _allowed_dirs = list(dict.fromkeys(_base_dirs))  # deduplica mantendo ordem
            else:
                _allowed_dirs = ["/mnt/d", "/mnt/c", _home]
                if _req_ws:
                    _allowed_dirs.insert(0, _req_ws)

            fs = FilesystemTool(_allowed_dirs)
            strategy = get_strategy_engine("data")

            # ── Detecta modo de construção para ajustar limites do loop ─────────
            _BUILD_KEYWORDS = [
                "crie", "cria", "criar", "construir", "construa", "build", "make",
                "desenvolver", "desenvolva", "gere", "gerar", "implemente", "implementar",
                "novo app", "nova ferramenta", "novo projeto", "do zero", "from scratch",
                "bounty tracker", "cli", "ferramenta em", "app em", "script",
            ]
            _is_build_mode = any(kw in body.message.lower() for kw in _BUILD_KEYWORDS)

            # Build system prompt usando build_system_prompt() — não precisa de rich
            classification = strategy.classify(body.message)
            lessons_text = strategy.format_lessons_for_prompt(classification.task_type)
            strategic_ctx = strategy.build_thinking_prompt(classification, body.message)
            if lessons_text:
                strategic_ctx = lessons_text + "\n\n" + strategic_ctx

            # build_system_prompt() já lê todos os .md files de prompts/
            # Injeta contexto real do workspace selecionado pelo usuário
            system = build_system_prompt("agent", real_workspace_path=_req_ws or None)
            if strategic_ctx:
                system = strategic_ctx + "\n\n" + system

            # Injeta contexto manual do usuário (painel Context) — apenas se não vazio
            _user_ctx = (body.user_context or "").strip()
            if _user_ctx:
                system = (
                    "## Contexto do Usuário (prioridade alta)\n"
                    + _user_ctx
                    + "\n\nUse este contexto para guiar suas respostas.\n\n"
                    + system
                )

            _episodic = None
            _memory_ctx = ""
            _thinking = None
            _think_result = None
            _action_chain = None
            _chain_id = ""
            try:
                from app.memory.episodic import EpisodicMemory
                _episodic = EpisodicMemory()
                _memory_ctx = _episodic.format_for_prompt(
                    workspace_path=_req_ws or None,
                    task_type=classification.task_type,
                    limit=3,
                )
                if _memory_ctx:
                    system = _memory_ctx + "\n\n" + system
            except Exception:
                pass

            try:
                from app.thinking import ThinkingLayer
                _thinking = ThinkingLayer(client, model_id)
                if _thinking.should_think(body.message, classification.task_type):
                    put_event({"type": "text_chunk", "text": "🧠 "})
                    _think_result = _thinking.think(
                        message=body.message,
                        task_type=classification.task_type,
                        memory_context=_memory_ctx,
                        workspace_context=system[:500],
                    )
                    if _think_result:
                        system = system + "\n\n" + _think_result.to_prompt_injection()
            except Exception:
                pass

            try:
                from app.action_chain import ActionChain
                _action_chain = ActionChain()
                _chain_id = _action_chain.start(body.message[:100])
            except Exception:
                _action_chain = None
                _chain_id = ""

            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": body.message},
            ]

            # ── Cria client correto baseado no model_id ───────────────────
            if model_id.startswith('claude'):
                # Anthropic — usa wrapper OpenAI-compat via SDK nativo abaixo
                # Para tool calls, usa openai-compat da Anthropic Messages API
                # Nota: Anthropic suporta tool_calls via seu SDK; aqui usamos
                # o wrapper OpenAI-compat para simplicidade no loop agêntico
                _ant_api_key = os.getenv('ANTHROPIC_API_KEY', '').strip()
                client = SyncOpenAI(
                    api_key=_ant_api_key,
                    base_url='https://api.anthropic.com/v1',
                    default_headers={'anthropic-version': '2023-06-01'},
                ) if _ant_api_key else SyncOpenAI(api_key=api_key)
            elif model_id.startswith('grok'):
                _xai_key = os.getenv('XAI_API_KEY', os.getenv('GROK_API_KEY', '')).strip()
                client = SyncOpenAI(
                    api_key=_xai_key,
                    base_url='https://api.x.ai/v1',
                ) if _xai_key else SyncOpenAI(api_key=api_key)
            elif 'llama' in model_id or 'mixtral' in model_id:
                _groq_key = os.getenv('GROQ_API_KEY', '').strip()
                client = SyncOpenAI(
                    api_key=_groq_key,
                    base_url='https://api.groq.com/openai/v1',
                ) if _groq_key else SyncOpenAI(api_key=api_key)
            elif 'Llama' in model_id or 'together' in model_id.lower():
                _tg_key = os.getenv('TOGETHER_API_KEY', '').strip()
                client = SyncOpenAI(
                    api_key=_tg_key,
                    base_url='https://api.together.xyz/v1',
                ) if _tg_key else SyncOpenAI(api_key=api_key)
            else:
                client = SyncOpenAI(api_key=api_key)
            from app.tools.filesystem_tool import FilesystemTool as FST
            tools = FST.get_tool_definitions()

            # Pack: bounty web
            try:
                from app.tools import bounty_tool as _bt
                tools.extend(_bt.get_tool_definitions())
            except Exception:
                pass
            # Pack: solana audit
            try:
                from app.tools import solana_audit_tool as _sat
                tools.extend(_sat.get_tool_definitions())
            except Exception:
                pass
            # Pack: browser automation
            try:
                from app.tools import browser_tool as _bwt
                tools.extend(_bwt.get_tool_definitions())
            except Exception:
                pass

            # Add learn_lesson tool definition
            tools.append({
                "type": "function",
                "function": {
                    "name": "learn_lesson",
                    "description": "Registra uma lição aprendida desta execução.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_type": {"type": "string"},
                            "task_summary": {"type": "string"},
                            "what_worked": {"type": "string"},
                            "what_failed": {"type": "string"},
                            "tools_used": {"type": "array", "items": {"type": "string"}},
                            "outcome": {"type": "string", "enum": ["success", "partial", "failed"]},
                            "notes": {"type": "string"},
                        },
                        "required": ["task_type", "task_summary", "what_worked", "what_failed", "tools_used", "outcome"],
                    },
                },
            })
            tools.append({
                "type": "function",
                "function": {
                    "name": "save_context",
                    "description": "Salva contexto do projeto na sessão.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["key", "value"],
                    },
                },
            })

            tools_used = []
            call_num = 0
            _recent: set = set()
            _scan_done = False
            _read_done = False
            _project_ctx: dict = {}
            _tool_counts: dict = {}   # contagem por tipo de tool para limitar abusos

            def summarize_args(args: dict) -> str:
                for k in ("path", "query", "command", "key"):
                    if k in args:
                        v = str(args[k])
                        return v[:40] + ("..." if len(v) > 40 else "")
                if "paths" in args and isinstance(args["paths"], list):
                    return f"{len(args['paths'])} files"
                return ""

            def summarize_result(result: dict) -> str:
                if "error" in result:
                    return f"Error: {result['error'][:80]}"
                for k in ("files_read_count", "matches", "lines"):
                    if k in result:
                        return f"{k}: {result[k]}"
                content = result.get("content") or result.get("stdout") or result.get("output") or ""
                if content:
                    return str(content)[:120]
                return str(result)[:80]

            # ═══════════════════════════════════════════════════════════════════
            # Funções auxiliares de gestão segura de contexto
            # ═══════════════════════════════════════════════════════════════════

            def _msg_role(m):
                return m.get("role", "") if isinstance(m, dict) else getattr(m, "role", "")

            def _msg_tool_calls(m):
                tcs = m.get("tool_calls") if isinstance(m, dict) else getattr(m, "tool_calls", None)
                return tcs or []

            def _tc_id(tc):
                return tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)

            def _parse_exchanges(body):
                """Agrupa mensagens em trocas completas (assistant + todos seus tool_results).
                Trocas incompletas (tool_calls sem todos os resultados) são descartadas."""
                groups, i = [], 0
                while i < len(body):
                    m = body[i]
                    role = _msg_role(m)
                    if role == "tool":           # tool result órfão — ignora
                        i += 1; continue
                    group = [m]
                    if role == "assistant":
                        tcs = _msg_tool_calls(m)
                        if tcs:
                            expected = {_tc_id(tc) for tc in tcs}
                            j, found, tool_msgs = i + 1, set(), []
                            while j < len(body) and _msg_role(body[j]) == "tool":
                                tc_id_val = (body[j].get("tool_call_id", "") if isinstance(body[j], dict)
                                             else getattr(body[j], "tool_call_id", ""))
                                found.add(tc_id_val); tool_msgs.append(body[j]); j += 1
                            if expected.issubset(found):  # todos os IDs esperados têm resultado → inclui
                                group.extend(tool_msgs); i = j
                                groups.append(group); continue
                            else:                        # algum tool_call sem resultado → descarta
                                i = j; continue
                    i += 1
                    groups.append(group)
                return groups

            def _build_safe_context(msgs, max_exchanges=8):
                """Retorna lista de mensagens válida para a API Anthropic.
                Sempre mantém: system + primeira mensagem user + últimos max_exchanges grupos."""
                if len(msgs) < 3:
                    return msgs
                sys_msg, first_user, body = msgs[0], msgs[1], msgs[2:]
                exchanges = _parse_exchanges(body)
                kept = exchanges[-max_exchanges:] if len(exchanges) > max_exchanges else exchanges
                result = [sys_msg, first_user]
                for ex in kept:
                    result.extend(ex)
                return result

            def _ensure_complete_tail(msgs):
                """Remove o último assistant message se ele tem tool_calls sem resultados.
                Chamado depois de qualquer exception para deixar o histórico limpo."""
                if len(msgs) < 2:
                    return msgs
                last = msgs[-1]
                if _msg_role(last) == "assistant" and _msg_tool_calls(last):
                    msgs.pop()   # remove troca incompleta
                return msgs

            # ═══════════════════════════════════════════════════════════════════
            import time as _throttle_time

            # ══════════════════════════════════════════════════════════════════
            # Auto-correção: retry com backoff exponencial em 429/rate_limit
            # Circuit breaker: xAI e OpenAI têm limites muito maiores que Groq,
            # então usamos xAI → OpenAI → Groq → Together como ordem de fallback.
            # Groq fica no final porque tem rate limit agressivo no free tier.
            # ══════════════════════════════════════════════════════════════════
            _FALLBACK_ORDER = [
                # (label, env_key, base_url, model_name)
                ("xai",     "XAI_API_KEY",      "https://api.x.ai/v1",            "grok-3-mini"),
                ("openai",  "OPENAI_API_KEY",    None,                              "gpt-4o-mini"),
                ("groq",    "GROQ_API_KEY",      "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
                ("together","TOGETHER_API_KEY",  "https://api.together.xyz/v1",    "meta-llama/Llama-3.1-405B-Instruct-Turbo"),
            ]

            def _make_fallback_client(idx: int):
                """Retorna um (client, model) de fallback pelo índice."""
                _, env_k, base, mdl = _FALLBACK_ORDER[idx]
                key = os.getenv(env_k, "").strip()
                if not key:
                    return None, None
                if base:
                    return SyncOpenAI(api_key=key, base_url=base), mdl
                return SyncOpenAI(api_key=key), mdl

            def _llm_call_with_retry(msgs, tools_defs, model, temperature=0.2, max_tokens=4096, max_retries=4):
                """
                Chama client.chat.completions.create com retry exponencial em caso de
                RateLimitError (429) ou APIConnectionError. Fallback automático de provider.
                Emite eventos 'compressing' ao frontend para manter o usuário informado.
                """
                _retry_delays = [5, 15, 30, 60]  # segundos entre tentativas
                _used_model   = model
                _used_client  = client
                _fallback_idx = 0

                for attempt in range(max_retries + 1):
                    try:
                        return _used_client.chat.completions.create(
                            model=_used_model,
                            messages=msgs,
                            tools=tools_defs,
                            tool_choice="auto",
                            temperature=temperature,
                            max_tokens=max_tokens,
                        )
                    except Exception as _api_err:
                        _err_str = str(_api_err).lower()
                        _is_rate  = "429" in _err_str or "rate_limit" in _err_str or "rate limit" in _err_str
                        _is_conn  = "connection" in _err_str or "timeout" in _err_str or "503" in _err_str or "502" in _err_str

                        if not (_is_rate or _is_conn) or attempt >= max_retries:
                            raise  # re-lança erros não recuperáveis

                        # ── Rate limit: tenta fallback primeiro, depois aguarda
                        if _is_rate and _fallback_idx < len(_FALLBACK_ORDER):
                            _fb_client, _fb_model = _make_fallback_client(_fallback_idx)
                            _fallback_idx += 1
                            if _fb_client and _fb_model:
                                put_event({
                                    "type": "compressing",
                                    "progress": 30,
                                    "message": f"⚡ Rate limit — alternando para provider de fallback ({_fb_model})...",
                                })
                                _used_client = _fb_client
                                _used_model  = _fb_model
                                _throttle_time.sleep(2)
                                continue  # tenta imediatamente com novo provider

                        # ── Backoff exponencial
                        _wait = _retry_delays[min(attempt, len(_retry_delays) - 1)]
                        put_event({
                            "type": "compressing",
                            "progress": 20 + attempt * 15,
                            "message": f"⏳ Rate limit atingido — aguardando {_wait}s antes de tentar novamente (tentativa {attempt+1}/{max_retries})...",
                        })
                        _throttle_time.sleep(_wait)

                raise RuntimeError("Todas as tentativas de retry esgotadas.")

            def _extract_tool_results_summary(msgs) -> str:
                """Extrai resultados de ferramentas das mensagens e monta um resumo sem LLM."""
                snippets: list[str] = []
                for m in msgs:
                    role = _msg_role(m)
                    if role == "tool":
                        content = (m.get("content", "") if isinstance(m, dict)
                                   else getattr(m, "content", ""))
                        if content:
                            try:
                                import json as _j
                                parsed = _j.loads(content)
                                # Pega o campo mais informativo
                                text = (
                                    parsed.get("output")
                                    or parsed.get("result")
                                    or parsed.get("content")
                                    or str(parsed)
                                )
                            except Exception:
                                text = str(content)
                            # Trunca snippets longos
                            text = text[:600].strip()
                            if text:
                                snippets.append(f"• {text}")
                if snippets:
                    joined = "\n".join(snippets[:12])  # máx 12 resultados
                    return (
                        f"Completei {call_num} operações e coletei os seguintes resultados:\n\n"
                        f"{joined}\n\n"
                        "Consulte o painel TOOLS para os detalhes completos de cada operação."
                    )
                return (
                    f"Realizei {call_num} operações. "
                    "Consulte o painel TOOLS para ver todos os resultados coletados."
                )

            def _force_synthesis(reason: str) -> None:
                """Força uma resposta final do LLM sem ferramentas, sintetizando o que foi coletado."""
                synth_msgs = _build_safe_context(messages, max_exchanges=5)
                synth_msgs.append({
                    "role": "user",
                    "content": (
                        f"[{reason}] PARE de usar ferramentas agora. "
                        "Com base em TUDO que você coletou até aqui, escreva sua resposta final completa e detalhada. "
                        "Não use mais ferramentas — sintetize os achados reais em texto agora."
                    ),
                })
                final: str | None = None

                # Tentativa 1 — síntese completa (5 exchanges de contexto)
                try:
                    synth_resp = _llm_call_with_retry(
                        msgs=synth_msgs,
                        tools_defs=[],
                        model=model_id,
                        temperature=0.1,
                        max_tokens=3000,
                        max_retries=3,
                    )
                    final = synth_resp.choices[0].message.content or None
                except Exception:
                    pass

                # Tentativa 2 — síntese minimalista (contexto reduzido)
                if not final:
                    try:
                        mini_msgs = _build_safe_context(messages, max_exchanges=2)
                        mini_msgs.append({
                            "role": "user",
                            "content": (
                                "Resuma brevemente em português o que você descobriu nesta análise. "
                                "Seja direto e objetivo — apenas os achados principais."
                            ),
                        })
                        mini_resp = _llm_call_with_retry(
                            msgs=mini_msgs,
                            tools_defs=[],
                            model=model_id,
                            temperature=0.1,
                            max_tokens=1500,
                            max_retries=2,
                        )
                        final = mini_resp.choices[0].message.content or None
                    except Exception:
                        pass

                # Tentativa 3 — resumo local dos resultados das ferramentas (sem LLM)
                if not final:
                    final = _extract_tool_results_summary(messages)
                try:
                    if _episodic and call_num >= 1:
                        _chain_export = _action_chain.export_for_memory(_chain_id) if (_action_chain and _chain_id) else {}
                        _episodic.record_session(
                            session_id=sid,
                            workspace_path=_req_ws or "",
                            task_type=classification.task_type,
                            summary=final[:500],
                            tools_used=tools_used,
                            outcome="partial",
                            key_facts=_chain_export.get("key_facts", []),
                        )
                except Exception:
                    pass
                words = final.split(" ")
                for chunk in [" ".join(words[i:i+8]) + " " for i in range(0, len(words), 8)]:
                    put_event({"type": "text_chunk", "text": chunk})
                put_event({"type": "done", "final_text": final, "tools_used": tools_used})

            # ── Limites adaptativos: construção precisa de mais tokens/iterações ──
            _max_iterations  = 24 if _is_build_mode else 12
            _max_op_limit    = 40 if _is_build_mode else 22
            _max_tokens_call = 8192 if _is_build_mode else 4096
            _max_exchanges   = 14 if _is_build_mode else 8

            for iteration in range(_max_iterations):
                # ── Guardrail de ops máximas → síntese forçada ───────────────
                if call_num >= _max_op_limit:
                    _force_synthesis(f"LIMITE DE {call_num} OPERAÇÕES")
                    return

                # ── Throttle inter-iteração (1s — balanceia rate limit vs velocidade)
                if iteration > 0:
                    _throttle_time.sleep(1)

                # ── Contexto seguro: NUNCA cortar tool_call/tool_result no meio ──
                messages = _build_safe_context(messages, max_exchanges=_max_exchanges)

                resp = _llm_call_with_retry(
                    msgs=messages,
                    tools_defs=tools,
                    model=model_id,
                    temperature=0.2,
                    max_tokens=_max_tokens_call,
                    max_retries=4,
                )
                choice = resp.choices[0]

                # Final response
                if choice.finish_reason != "tool_calls" or not choice.message.tool_calls:
                    final = choice.message.content or ""

                    # Guardrail: hollow response check
                    _hollow = ["análise concluída", "tarefa executada", "feito com sucesso",
                               "concluído com sucesso", "estou pronta para ajudar",
                               "estou à disposição", "se precisar de mais"]
                    # Guardrail extra para modo construção: Luna fala sobre criar arquivos
                    # mas não usa write_file — sinal de que o modelo travou sem tool calls
                    _build_incomplete_signals = [
                        "preciso criar", "falta criar", "que ainda faltam", "ainda falta",
                        "vou criar", "agora vou escrever", "vou escrever o arquivo",
                        "vou implementar", "resta criar", "falta implementar",
                    ]
                    _is_build_incomplete = (
                        _is_build_mode
                        and call_num >= 1
                        and iteration < (_max_iterations - 2)
                        and any(s in final.lower() for s in _build_incomplete_signals)
                    )

                    # Guardrail: Luna despejando código como markdown em vez de write_file
                    # Dois casos:
                    # 1) write_file nunca foi usado E há blocos de código → deveria ter usado write_file
                    # 2) write_file JÁ foi usado E há blocos de código → está repetindo código desnecessariamente
                    _code_block_count = final.count("```")
                    _write_file_used  = tools_used.count("write_file") > 0
                    _code_dump_in_chat = (
                        _is_build_mode
                        and call_num >= 1
                        and iteration < (_max_iterations - 2)
                        and _code_block_count >= 6  # 3+ blocos de código = dump suspeito
                    )

                    # Guardrail: Luna dizendo falsamente que arquivos não foram criados
                    _false_incomplete_signals = [
                        "sessão anterior ficou no meio", "arquivos do projeto ainda não foram",
                        "não foram criados de verdade", "vou construir tudo do zero agora",
                        "criar tudo do zero", "construir do zero agora",
                    ]
                    _is_false_incomplete = (
                        _is_build_mode
                        and "write_file" in str(tools_used)
                        and any(s in final.lower() for s in _false_incomplete_signals)
                    )
                    _is_hollow = (
                        call_num >= 2 and iteration < (_max_iterations - 2)
                        and (len(final.strip()) < 100 or any(h in final.lower() for h in _hollow))
                    )

                    # Guardrail visual: usuario pediu app/interface mas Luna esta fazendo CLI Python
                    _gui_keywords = ["app", "aplicativo", "aplicacao", "dashboard",
                                     "painel", "tracker", "interface", "tela", "frontend",
                                     "site", "web app", "landing", "electron", "desktop"]
                    _cli_signals = ["import rich", "from rich", "import typer", "from typer",
                                    "import click", "from click", "rich.console"]
                    _user_msg_lower = (body.message or "").lower()
                    _wants_gui = any(k in _user_msg_lower for k in _gui_keywords)
                    _visual_mismatch = (
                        _is_build_mode
                        and _wants_gui
                        and call_num >= 1
                        and iteration < (_max_iterations - 2)
                        and any(s in final.lower() for s in _cli_signals)
                    )

                    if _is_hollow or _is_build_incomplete or _code_dump_in_chat or _is_false_incomplete or _visual_mismatch:
                        messages.append({"role": "assistant", "content": final})
                        if _is_false_incomplete:
                            # Luna achou que arquivos não foram criados, mas write_file já rodou
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"[GUARDRAIL BUILD] PARE. Os arquivos já foram criados com write_file nesta sessão. "
                                    "Não diga que 'a sessão anterior ficou no meio' — isso é falso. "
                                    f"Foram realizadas {call_num} operações bem-sucedidas. "
                                    "PRÓXIMO PASSO CORRETO: rode o app com run_command e mostre o output real. "
                                    "NÃO reescreva o código. NÃO mostre blocos de código. RODE O APP."
                                ),
                            })
                        elif _code_dump_in_chat:
                            # Luna despejando código como texto em vez de usar write_file
                            if _write_file_used:
                                # Arquivos já foram criados — parar de repetir código
                                _dump_msg = (
                                    f"[GUARDRAIL BUILD] PARE de repetir código no chat. "
                                    f"Os {tools_used.count('write_file')} arquivo(s) já foram criados com write_file. "
                                    "Redigitar o código no chat NÃO cria mais arquivos — é desperdício de tokens. "
                                    "PRÓXIMOS PASSOS: instale dependências com run_command, rode o app, mostre o output real. "
                                    "Resposta esperada: '✅ Arquivos criados. Instalando deps...' + output do terminal."
                                )
                            else:
                                # Nunca usou write_file — deveria usar
                                _dump_msg = (
                                    f"[GUARDRAIL BUILD] PARE. Você está escrevendo código como texto no chat. "
                                    "Isso NÃO cria arquivos no disco. USE write_file para cada arquivo. "
                                    f"Você tem {_max_op_limit - call_num} operações restantes. "
                                    "EXECUTE: chame write_file para criar cada arquivo do projeto. "
                                    "Não mostre código no chat — grave no disco com write_file."
                                )
                            messages.append({"role": "user", "content": _dump_msg})
                        elif _is_build_incomplete:
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"[GUARDRAIL BUILD] Você mencionou arquivos que ainda precisam ser criados mas não usou write_file. "
                                    f"Você tem {_max_op_limit - call_num} operações restantes. "
                                    "USE write_file AGORA para criar os arquivos que faltam. "
                                    "Não descreva — EXECUTE. Chame write_file para cada arquivo pendente."
                                ),
                            })
                        elif _visual_mismatch:
                            messages.append({
                                "role": "user",
                                "content": (
                                    "[GUARDRAIL VISUAL] PARE. O usuario pediu um app/interface mas voce esta construindo CLI Python (rich/typer/click). "
                                    "Isso e anti-padrao. LEIA prompts/templates/electron-app.md ou prompts/templates/nextjs-app.md e prompts/templates/design-tokens.md AGORA usando read_file. "
                                    "Depois, RECOMECE o build usando scaffold oficial (npx create-electron-app / npm create vite / npx create-next-app) via run_command. "
                                    "Tema cyber obrigatorio. Primeira tela deve ser funcional, nao placeholder."
                                ),
                            })
                        else:
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"[GUARDRAIL] Sua resposta não apresentou os achados reais ({call_num} operações realizadas). "
                                    "Reescreva apresentando: estrutura do projeto, arquivos lidos com trechos reais, "
                                    "problemas encontrados com arquivo:linha, análise baseada em código real."
                                ),
                            })
                        continue

                    # ── Gravar sessão na memória episódica ───────────────────
                    try:
                        if _episodic and call_num >= 1:
                            _chain_export = _action_chain.export_for_memory(_chain_id) if (_action_chain and _chain_id) else {}
                            _episodic.record_session(
                                session_id=sid,
                                workspace_path=_req_ws or "",
                                task_type=classification.task_type,
                                summary=final[:500],
                                tools_used=tools_used,
                                outcome="success",
                                key_facts=_chain_export.get("key_facts", []),
                            )
                    except Exception:
                        pass

                    # Stream final text word by word
                    words = final.split(" ")
                    for chunk in [" ".join(words[i:i+8]) + " " for i in range(0, len(words), 8)]:
                        put_event({"type": "text_chunk", "text": chunk})
                    put_event({"type": "done", "final_text": final, "tools_used": tools_used})
                    return

                # Add assistant turn — converte para dict limpo para evitar que
                # serialização do Pydantic cause tool_call_id orphan na Anthropic API.
                _tc_list = choice.message.tool_calls or []
                _assistant_dict: dict = {"role": "assistant", "content": choice.message.content}
                if _tc_list:
                    _assistant_dict["tool_calls"] = [
                        {
                            "id": _tc.id,
                            "type": "function",
                            "function": {
                                "name": _tc.function.name,
                                "arguments": _tc.function.arguments,
                            },
                        }
                        for _tc in _tc_list
                    ]
                messages.append(_assistant_dict)

                # Execute tool calls — garante que TODOS os tc recebem um resultado
                # (evita tool_call_id orphan se qualquer parte do loop lançar exception)
                _pending_tcs = list(_tc_list)
                _processed_ids: set = set()

                for tc in _pending_tcs:
                    name = tc.function.name
                    try:
                        args = _json.loads(tc.function.arguments)
                    except Exception:
                        args = {}

                    # Path normalization: só converte para WSL se o backend estiver em Linux/WSL.
                    # Em Windows nativo NÃO converter — o FilesystemTool já aceita C:\ diretamente.
                    if _platform.system() != "Windows":
                        # Linux/WSL: converte C:\Dev\... → /mnt/c/dev/...
                        for k in ("path", "cwd"):
                            if k in args and isinstance(args[k], str) and "\\" in args[k]:
                                args[k] = "/mnt/" + args[k].replace("\\", "/").replace(":", "").lower()
                        if "paths" in args and isinstance(args.get("paths"), list):
                            args["paths"] = [
                                "/mnt/" + p.replace("\\", "/").replace(":", "").lower()
                                if isinstance(p, str) and "\\" in p else p
                                for p in args["paths"]
                            ]

                    # Dedup
                    _key = f"{name}::{_json.dumps(args, sort_keys=True, default=str)[:150]}"
                    if _key in _recent:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": _json.dumps({"skipped": True, "reason": "Chamada idêntica já executada."}),
                        })
                        put_event({"type": "tool_skipped", "name": name})
                        continue
                    _recent.add(_key)

                    call_num += 1
                    tools_used.append(name)
                    _tool_counts[name] = _tool_counts.get(name, 0) + 1
                    if name == "scan_project": _scan_done = True
                    if name in ("read_many", "read_file", "read_file_chunked"): _read_done = True

                    # ── Limites por tipo de tool (evita explosão de ops) ──────
                    _TOOL_LIMITS = {
                        "run_command":      5,   # max 5 comandos de shell por sessão
                        "list_dir":         8,   # max 8 listagens
                        "read_many":        5,   # max 5 chamadas read_many
                        "search_files":     4,   # max 4 buscas
                        "scan_project":     2,   # max 2 scans
                    }
                    _tlimit = _TOOL_LIMITS.get(name)
                    if _tlimit and _tool_counts[name] > _tlimit:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": _json.dumps({
                                "blocked": True,
                                "reason": f"Limite de {_tlimit} chamadas para '{name}' atingido. Use os dados já coletados e escreva a resposta final.",
                            }),
                        })
                        put_event({"type": "tool_skipped", "name": name})
                        _processed_ids.add(tc.id)
                        continue

                    args_summary = summarize_args(args)
                    put_event({"type": "tool_start", "name": name, "args_summary": args_summary, "call_num": call_num})

                    # Dispatch
                    result: dict = {}
                    try:
                        if name == "learn_lesson":
                            raw_tools = args.get("tools_used", [])
                            if isinstance(raw_tools, str):
                                raw_tools = [t.strip() for t in raw_tools.split(",") if t.strip()]
                            elif isinstance(raw_tools, list):
                                raw_tools = [str(t) for t in raw_tools if isinstance(t, str)]
                            strategy.save_lesson(
                                task_type=args.get("task_type", "general"),
                                task_summary=args.get("task_summary", "")[:200],
                                what_worked=args.get("what_worked", "")[:300],
                                what_failed=args.get("what_failed", "")[:200],
                                tools_used=raw_tools,
                                outcome=args.get("outcome", "partial"),
                                notes=args.get("notes", "")[:200],
                            )
                            result = {"ok": True}
                        elif name == "save_context":
                            key = args.get("key", "geral")
                            value = args.get("value", "")
                            _project_ctx[key] = value
                            result = {"ok": True, "key": key}
                            put_event({"type": "tool_done", "name": name, "result_summary": f"key={key}", "key": key, "value": value[:300]})
                            messages.append({"role": "tool", "tool_call_id": tc.id, "content": _json.dumps(result)})
                            continue
                        elif name == "list_dir":
                            result = fs.list_dir(args["path"], args.get("show_hidden", False))
                        elif name == "read_file":
                            result = fs.read_file(args["path"], args.get("max_chars", 4000))
                        elif name == "read_file_chunked":
                            result = fs.read_file_chunked(args["path"], args.get("chunk_size", 4000), args.get("chunk_index", 0))
                        elif name == "write_file":
                            result = fs.write_file(args["path"], args["content"])
                        elif name == "patch_file":
                            result = fs.patch_file(args["path"], args["old"], args["new"])
                        elif name == "search_files":
                            result = fs.search_files(args["path"], args["pattern"])
                        elif name == "grep_file":
                            result = fs.grep_file(args["path"], args["query"])
                        elif name == "run_command":
                            # Build mode: pip install, npm install, etc. precisam de mais tempo
                            _cmd_default_timeout = 120 if _is_build_mode else 30
                            result = fs.run_command(args["command"], args.get("cwd"), args.get("timeout", _cmd_default_timeout))
                            try:
                                _stdout = str(result.get("stdout", ""))
                                _stderr = str(result.get("stderr", ""))
                                _exit = result.get("exit_code", result.get("returncode", 0))
                                if _action_chain and _chain_id and int(_exit or 0) != 0:
                                    _action_chain.record_correction(_chain_id, error=(_stderr or _stdout or str(result))[:500], fix="retry")
                            except Exception:
                                pass
                        elif name == "create_dir":
                            result = fs.create_dir(args["path"])
                        elif name == "scan_project":
                            result = fs.scan_project(args["path"], args.get("max_files", 50))
                        elif name == "read_many":
                            result = fs.read_many(args["paths"])
                        elif name == "web_search":
                            result = fs.web_search(args["query"], args.get("max_results", 5))
                        elif name == "allow_dir":
                            requested_path = args.get("path", "")
                            result = fs.allow_dir(requested_path)
                            if result.get("ok"):
                                put_event({
                                    "type": "dir_access",
                                    "path": requested_path,
                                    "workspace": _req_ws or "",
                                    "status": "granted",
                                })
                        elif name.startswith("bounty_"):
                            try:
                                from app.tools import bounty_tool as _bt
                                _fn_map = {
                                    "bounty_recon_subdomains": _bt.recon_subdomains,
                                    "bounty_recon_live": _bt.recon_live_hosts,
                                    "bounty_crawl": _bt.recon_crawl,
                                    "bounty_scan_nuclei": _bt.scan_nuclei,
                                    "bounty_scan_dalfox": _bt.scan_dalfox,
                                    "bounty_audit_jwt": lambda token, **kw: _bt.audit_jwt(token),
                                    "bounty_audit_graphql": lambda endpoint, **kw: _bt.audit_graphql(endpoint),
                                    "bounty_scope_check": _bt.scope_check,
                                }
                                _fn = _fn_map.get(name)
                                result = _fn(**args) if _fn else {"error": f"bounty fn not found: {name}"}
                            except Exception as _e:
                                result = {"error": f"bounty_tool: {_e}"}
                        elif name.startswith("solana_"):
                            try:
                                from app.tools import solana_audit_tool as _sat
                                _fn_map = {
                                    "solana_parse_idl": _sat.parse_idl,
                                    "solana_rust_scan": _sat.rust_static_scan,
                                    "solana_decode_tx": _sat.decode_transaction,
                                    "solana_cpi_graph": _sat.build_cpi_graph,
                                }
                                _fn = _fn_map.get(name)
                                result = _fn(**args) if _fn else {"error": f"solana fn not found: {name}"}
                            except Exception as _e:
                                result = {"error": f"solana_audit_tool: {_e}"}
                        elif name.startswith("browser_"):
                            try:
                                from app.tools import browser_tool as _bwt
                                _fn_map = {
                                    "browser_navigate": _bwt.browser_navigate,
                                    "browser_extract": _bwt.browser_extract,
                                    "browser_eval": _bwt.browser_eval,
                                    "browser_fill_submit": _bwt.browser_fill_and_submit,
                                    "browser_screenshot": _bwt.browser_save_screenshot,
                                }
                                _fn = _fn_map.get(name)
                                result = _fn(**args) if _fn else {"error": f"browser fn not found: {name}"}
                            except Exception as _e:
                                result = {"error": f"browser_tool: {_e}"}
                        else:
                            result = {"error": f"Unknown tool: {name}"}
                    except Exception as e:
                        result = {"error": str(e)}

                    result_str = _json.dumps(result, ensure_ascii=False, default=str)
                    # Limite agressivo para não estourar 30k tokens/min (Anthropic free tier)
                    if len(result_str) > 6000:
                        result_str = result_str[:3000] + "\n...[truncado — use read_file_chunked para mais]...\n" + result_str[-3000:]

                    result_summary = summarize_result(result)
                    put_event({"type": "tool_done", "name": name, "result_summary": result_summary})
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_str})
                    _processed_ids.add(tc.id)

                    # Guardrail: scan without read
                    if _scan_done and not _read_done and call_num >= 2 and iteration < 12:
                        if name in ("save_context", "learn_lesson"):
                            messages.append({
                                "role": "user",
                                "content": (
                                    "[GUARDRAIL] scan_project foi executado mas read_many NÃO foi chamado. "
                                    "Use read_many para ler os arquivos principais, depois dê a resposta completa com os achados reais."
                                ),
                            })

                # ── Safety net: gera tool_result de erro para tc não processados ──
                # Garante que nenhum tool_call_id fique sem resposta (evita erro 400)
                for _unhandled_tc in _pending_tcs:
                    if _unhandled_tc.id not in _processed_ids:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": _unhandled_tc.id,
                            "content": _json.dumps({"error": "Processamento interrompido — resultado não disponível"}),
                        })

            _force_synthesis(f"LIMITE DE ITERAÇÕES — {call_num} OPS REALIZADAS")

        except Exception as e:
            # Limpa tail incompleta antes de emitir o erro (se helpers já foram criados)
            try:
                _ensure_complete_tail(messages)
            except Exception:
                pass
            put_event({"type": "error", "message": str(e)})

    # Run agent in thread
    import threading
    thread = threading.Thread(target=run_agent, daemon=True)
    thread.start()

    async def generate():
        SENTINEL = object()
        _timeout_strikes = 0
        _max_timeout_strikes = 3  # Tenta re-esperar até 3 vezes antes de desistir
        while True:
            try:
                evt = await asyncio.wait_for(event_queue.get(), timeout=_sse_timeout)
                _timeout_strikes = 0  # Reset ao receber qualquer evento
                if evt is SENTINEL:
                    break
                yield "data: " + _json.dumps(evt, ensure_ascii=False, default=str) + "\n\n"
                if evt.get("type") in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                _timeout_strikes += 1
                if _timeout_strikes < _max_timeout_strikes:
                    # Mantém a conexão viva com um ping enquanto Anthropic ainda pode estar processando
                    yield "data: " + _json.dumps({
                        "type": "text_chunk",
                        "text": ""
                    }) + "\n\n"
                    continue
                # Após 3 timeouts consecutivos, entrega fallback gracioso ao invés de erro
                _fallback_msg = (
                    "✅ Operações concluídas com sucesso.\n\n"
                    "_(A síntese final demorou mais que o esperado — "
                    "confira o painel **Tools** para ver tudo que foi executado.)_"
                )
                yield "data: " + _json.dumps({
                    "type": "done",
                    "final_text": _fallback_msg,
                    "tools_used": [],
                }, ensure_ascii=False) + "\n\n"
                break

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


# ─── Lessons endpoint ────────────────────────────────────────────────────────

@app.get("/lessons")
def get_lessons_stats():
    """Retorna estatísticas de lições aprendidas da Luna."""
    try:
        from app.strategy import get_strategy_engine
        strategy = get_strategy_engine("data")
        stats = strategy.get_stats()
        return stats
    except Exception as e:
        return {"total_lessons": 0, "by_type": {}, "error": str(e)}


# ─── Context endpoint ────────────────────────────────────────────────────────

_ui_project_context: dict[str, str] = {}

@app.get("/context")
def get_ui_context():
    return {"context": _ui_project_context}

@app.post("/context")
def set_ui_context(body: dict):
    key = body.get("key", "")
    value = body.get("value", "")
    if key:
        _ui_project_context[key] = value
    return {"ok": True}


class FactRequest(BaseModel):
    key:        str
    value:      str
    project_id: str | None = None


@app.post("/memory/fact")
def save_memory_fact(body: FactRequest):
    project = (body.project_id or get_active_workspace()).strip()
    ltm_save_fact(project, body.key, body.value)
    append_structured_log(
        event      = EventType.MEMORY_WRITE,
        trigger    = f"manual_fact_{body.key}",
        action     = "fact_saved",
        result     = "ok",
        project_id = project,
        detail     = {"key": body.key, "value": body.value[:100]},
    )
    return {"success": True, "response": {"status": "saved", "key": body.key, "project_id": project}}


@app.get("/memory/facts")
def get_memory_facts(project_id: str | None = None):
    project = (project_id or get_active_workspace()).strip()
    facts = ltm_get_facts(project)
    stats = ltm_get_stats(project)
    return {"success": True, "response": {"project_id": project, "facts": facts, "stats": stats}}


@app.post("/session/clear")
def clear_session(session_id: str):
    stm_clear(session_id)
    append_structured_log(
        event      = EventType.CONTEXT_SWITCH,
        trigger    = f"manual_clear_{session_id}",
        action     = "session_cleared",
        result     = "ok",
        session_id = session_id,
        project_id = get_active_workspace(),
    )
    return {"success": True, "response": {"status": "cleared", "session_id": session_id}}


class WorkspaceSwitchRequest(BaseModel):
    workspace: str


@app.get("/workspaces")
def list_workspaces():
    """Lista todos os workspaces disponíveis com seu status."""
    workspaces_dir = WORKSPACES_DIR
    available = []

    if workspaces_dir.exists():
        for ws_path in sorted(workspaces_dir.iterdir()):
            if ws_path.is_dir():
                info = inspect_workspace(ws_path.name)
                available.append({
                    "name":    ws_path.name,
                    "active":  ws_path.name == get_active_workspace(),
                    "complete": info["all_required_present"],
                    "file_count": info["file_count"],
                    "missing": info["missing"],
                })

    return {
        "success": True,
        "response": {
            "active_workspace": get_active_workspace(),
            "workspaces": available,
        }
    }


@app.post("/workspace/switch")
def switch_workspace(payload: WorkspaceSwitchRequest):
    """Troca o workspace ativo em runtime."""
    name = payload.workspace.strip()
    if not name:
        raise HTTPException(status_code=400, detail="workspace name is required")

    ws_path = WORKSPACES_DIR / name
    if not ws_path.is_dir():
        raise HTTPException(status_code=404, detail=f"workspace '{name}' não encontrado")

    previous = get_active_workspace()
    _runtime_workspace["active"] = name

    append_structured_log(
        event      = EventType.CONTEXT_SWITCH,
        trigger    = f"workspace_switch_from_{previous}",
        action     = f"switched_to_{name}",
        result     = "ok",
        project_id = name,
        detail     = {"previous": previous, "new": name},
    )

    info = inspect_workspace(name)
    return {
        "success": True,
        "response": {
            "previous_workspace": previous,
            "active_workspace":   name,
            "complete":           info["all_required_present"],
            "file_count":         info["file_count"],
            "missing":            info["missing"],
        }
    }


@app.get("/workspace/context")
def get_workspace_context(workspace: str | None = None):
    """Retorna o contexto (CURRENT_STATUS + NEXT_STEPS) do workspace ativo."""
    name = (workspace or get_active_workspace()).strip()
    ws_dir = WORKSPACES_DIR / name
    status  = read_text_file(ws_dir / "CURRENT_STATUS.md")
    nexts   = read_text_file(ws_dir / "NEXT_STEPS.md")
    context = read_text_file(ws_dir / "PROJECT_CONTEXT.md")
    return {
        "success": True,
        "response": {
            "workspace":       name,
            "project_context": context,
            "current_status":  status,
            "next_steps":      nexts,
        }
    }


# ─── Image helpers ───────────────────────────────────────
def _get_image_provider() -> str:
    return (os.getenv("IMAGE_PROVIDER", "openai") or "openai").strip().lower()

def _get_stability_key() -> str:
    return (os.getenv("STABILITY_API_KEY", "") or "").strip()

def _get_openai_key() -> str:
    return (os.getenv("OPENAI_API_KEY", "") or "").strip()


# ─── Image models ────────────────────────────────────────
class ImageGenerateRequest(BaseModel):
    prompt:          str
    negative_prompt: str   = ""
    size:            str   = "1024x1024"
    quality:         str   = "standard"
    style:           str   = "vivid"
    # Stability-specific
    steps:           int   = 30
    cfg_scale:       float = 7.0
    style_preset:    str   = "none"
    seed:            int   = 0
    project_id:      str | None = None


# ─── Image endpoints ─────────────────────────────────────
@app.post("/image/generate")
def image_generate(payload: ImageGenerateRequest):
    """Gera imagem. Roteado para OpenAI ou Stability AI conforme IMAGE_PROVIDER."""
    provider   = _get_image_provider()
    project_id = payload.project_id or get_active_workspace()

    if provider == "stability":
        api_key = _get_stability_key()
        if not api_key:
            raise HTTPException(status_code=500, detail="STABILITY_API_KEY não configurada")
        result = generate_image_stability(
            api_key         = api_key,
            prompt          = payload.prompt,
            negative_prompt = payload.negative_prompt,
            size            = payload.size,
            steps           = payload.steps,
            cfg_scale       = payload.cfg_scale,
            style_preset    = payload.style_preset,
            seed            = payload.seed,
            project_id      = project_id,
        )
    else:
        api_key = _get_openai_key()
        if not api_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY não configurada")
        result = generate_image(
            api_key    = api_key,
            prompt     = payload.prompt,
            size       = payload.size,
            quality    = payload.quality,
            style      = payload.style,
            project_id = project_id,
        )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Erro na geração"))

    append_structured_log(
        event      = EventType.TOOL_RESULT,
        trigger    = payload.prompt[:200],
        action     = "image_generated",
        result     = "ok",
        project_id = project_id,
        detail     = {"image_id": result.get("image_id"), "provider": provider},
    )
    return {"success": True, "response": result}


@app.post("/image/edit")
async def image_edit(
    prompt:          str        = Form(...),
    negative_prompt: str        = Form(""),
    image:           UploadFile = File(...),
    mask:            UploadFile = File(None),
    size:            str        = Form("1024x1024"),
    project_id:      str        = Form(None),
):
    """Edita imagem. Roteado conforme IMAGE_PROVIDER."""
    provider   = _get_image_provider()
    project_id = project_id or get_active_workspace()

    image_bytes = await image.read()
    mask_bytes  = await mask.read() if mask else None

    if provider == "stability":
        api_key = _get_stability_key()
        if not api_key:
            raise HTTPException(status_code=500, detail="STABILITY_API_KEY não configurada")
        result = edit_image_stability(
            api_key         = api_key,
            image_bytes     = image_bytes,
            prompt          = prompt,
            negative_prompt = negative_prompt,
            mask_bytes      = mask_bytes,
            project_id      = project_id,
        )
    else:
        api_key = _get_openai_key()
        if not api_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY não configurada")
        result = edit_image(
            api_key     = api_key,
            image_bytes = image_bytes,
            prompt      = prompt,
            mask_bytes  = mask_bytes,
            size        = size,
            project_id  = project_id,
        )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Erro na edição"))

    append_structured_log(
        event      = EventType.TOOL_RESULT,
        trigger    = prompt[:200],
        action     = "image_edited",
        result     = "ok",
        project_id = project_id,
        detail     = {"image_id": result.get("image_id"), "provider": provider},
    )
    return {"success": True, "response": result}


@app.post("/image/variation")
async def image_variation(
    image:          UploadFile = File(...),
    prompt:         str        = Form("high quality variation"),
    size:           str        = Form("1024x1024"),
    n:              int        = Form(2),
    cfg_scale:      float      = Form(7.0),
    steps:          int        = Form(30),
    image_strength: float      = Form(0.35),
    project_id:     str        = Form(None),
):
    """Cria variações. Roteado conforme IMAGE_PROVIDER."""
    provider   = _get_image_provider()
    project_id = project_id or get_active_workspace()

    image_bytes = await image.read()

    if provider == "stability":
        api_key = _get_stability_key()
        if not api_key:
            raise HTTPException(status_code=500, detail="STABILITY_API_KEY não configurada")
        result = create_variation_stability(
            api_key        = api_key,
            image_bytes    = image_bytes,
            prompt         = prompt,
            image_strength = image_strength,
            size           = size,
            n              = n,
            cfg_scale      = cfg_scale,
            steps          = steps,
            project_id     = project_id,
        )
    else:
        api_key = _get_openai_key()
        if not api_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY não configurada")
        result = create_variation(
            api_key     = api_key,
            image_bytes = image_bytes,
            size        = size,
            n           = n,
            project_id  = project_id,
        )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Erro na variação"))

    return {"success": True, "response": result}


@app.get("/image/provider")
def image_provider_info():
    """Retorna o provider ativo e se a key está configurada."""
    provider = _get_image_provider()
    has_key  = bool(_get_stability_key() if provider == "stability" else _get_openai_key())
    return {
        "success": True,
        "response": {
            "provider": provider,
            "key_configured": has_key,
        }
    }


@app.get("/image/gallery")
def image_gallery(limit: int = 50, project_id: str | None = None):
    """Lista as últimas imagens geradas."""
    gallery = get_gallery(limit=limit, project_id=project_id)
    return {"success": True, "response": {"images": gallery, "count": len(gallery)}}


@app.get("/image/file/{image_id}")
def image_file(image_id: str):
    """Serve o arquivo de imagem pelo ID."""
    data = get_image_bytes(image_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Imagem não encontrada")
    return Response(content=data, media_type="image/png")


@app.delete("/image/{image_id}")
def image_delete(image_id: str):
    """Deleta uma imagem da galeria e do disco."""
    deleted = delete_image(image_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Imagem não encontrada")
    return {"success": True, "response": {"deleted": image_id}}


class ScreenAnalyzeRequest(BaseModel):
    image_b64: str
    mime: str = "image/jpeg"
    query: str = "Descreva objetivamente o que está acontecendo nessa tela: aplicativos abertos, conteúdo visível, estado geral do sistema. Seja direto e operacional."

@app.post("/screen/analyze")
def screen_analyze(payload: ScreenAnalyzeRequest):
    """Envia screenshot base64 para análise visual via gpt-4o."""
    api_key = _get_openai_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY não configurada")
    if not payload.image_b64:
        raise HTTPException(status_code=400, detail="image_b64 obrigatório")

    client = OpenAI(api_key=api_key)
    data_url = f"data:{payload.mime};base64,{payload.image_b64}"
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": payload.query},
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "auto"}},
                ],
            }],
            max_tokens=600,
        )
        analysis = resp.choices[0].message.content or ""
        return {"success": True, "response": {"analysis": analysis}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"análise visual falhou: {e}")


@app.post("/speak")
def speak(payload: SpeakRequest):
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    client = get_client()
    tts_model = os.getenv("LUNA_TTS_MODEL", "gpt-4o-mini-tts").strip() or "gpt-4o-mini-tts"
    tts_voice = os.getenv("LUNA_TTS_VOICE", "marin").strip() or "marin"
    tts_instructions = os.getenv(
        "LUNA_TTS_INSTRUCTIONS",
        "Fale em português do Brasil, com voz feminina, natural, calorosa, elegante, clara e levemente energética, como uma assistente premium e humana."
    ).strip()

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tmp_path = Path(tmp.name)

        try:
            with client.audio.speech.with_streaming_response.create(
                model=tts_model,
                voice=tts_voice,
                input=text,
                instructions=tts_instructions,
                response_format="mp3",
            ) as speech_response:
                speech_response.stream_to_file(tmp_path)

            audio_bytes = tmp_path.read_bytes()
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS error: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
# WORKER ENDPOINTS — Luna Agent Worker Premium Mode
# ═══════════════════════════════════════════════════════════════════════════════

from fastapi import Header as _Header


def _require_worker_token(authorization: str = _Header(default="")) -> None:
    """Valida token do Worker. Se LUNA_WORKER_TOKEN não estiver configurado, aceita tudo."""
    if not WORKER_TOKEN:
        return  # sem token configurado → aberto
    if not authorization.startswith("Bearer ") or authorization[7:] != WORKER_TOKEN:
        raise HTTPException(status_code=401, detail="Worker não autorizado — token inválido")


# ─── Register / Heartbeat ─────────────────────────────────────────────────────

class WorkerRegisterRequest(BaseModel):
    worker_id: str
    capabilities: list[str] = Field(default_factory=list)
    platform: str = ""
    version: str = ""


@app.post("/worker/register")
def worker_register(
    payload: WorkerRegisterRequest,
    authorization: str = _Header(default=""),
):
    _require_worker_token(authorization)
    info = _ws.register_worker(
        worker_id=payload.worker_id,
        capabilities=payload.capabilities,
        platform=payload.platform,
        version=payload.version,
    )
    return {"success": True, "response": info.model_dump()}


@app.post("/worker/heartbeat")
def worker_heartbeat(
    payload: WorkerRegisterRequest,
    authorization: str = _Header(default=""),
):
    _require_worker_token(authorization)
    # Re-register se necessário (auto re-register após restart do Brain)
    info = _ws.worker_heartbeat(payload.worker_id)
    if not info:
        info = _ws.register_worker(
            worker_id=payload.worker_id,
            capabilities=payload.capabilities,
            platform=payload.platform,
            version=payload.version,
        )
    return {"success": True, "response": info.model_dump()}


@app.get("/worker/workers")
def list_workers(authorization: str = _Header(default="")):
    _require_worker_token(authorization)
    workers = _ws.get_workers()
    return {"success": True, "response": {"workers": [w.model_dump() for w in workers]}}


# ─── Task Polling ─────────────────────────────────────────────────────────────

class WorkerPollRequest(BaseModel):
    worker_id: str


@app.post("/worker/tasks/poll")
def worker_poll_task(
    payload: WorkerPollRequest,
    authorization: str = _Header(default=""),
):
    """Worker chama este endpoint para pegar a próxima task disponível."""
    _require_worker_token(authorization)
    task = _ws.get_pending_task(payload.worker_id)
    if not task:
        return {"success": True, "response": {"task": None}}
    return {"success": True, "response": {"task": task.model_dump()}}


@app.get("/worker/tasks")
def list_worker_tasks(
    status: str | None = None,
    authorization: str = _Header(default=""),
):
    """Lista tasks do worker. Acessível pela UI e pelo Worker."""
    _require_worker_token(authorization)
    tasks = _ws.list_tasks(status_filter=status)
    return {
        "success": True,
        "response": {
            "tasks": [t.model_dump() for t in tasks],
            "count": len(tasks),
        },
    }


@app.get("/worker/task/{task_id}")
def get_worker_task(
    task_id: str,
    authorization: str = _Header(default=""),
):
    _require_worker_token(authorization)
    task = _ws.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"task '{task_id}' não encontrada")
    return {"success": True, "response": task.model_dump()}


# ─── Worker Result / Approval Request ────────────────────────────────────────

class WorkerResultPayload(BaseModel):
    task_id: str
    worker_id: str = ""
    status: str   # "completed" | "failed" | "awaiting_approval"
    result: dict = Field(default_factory=dict)
    error: str = ""
    # campos extras para awaiting_approval
    reason: str = ""


@app.post("/worker/result")
def worker_report_result(
    payload: WorkerResultPayload,
    authorization: str = _Header(default=""),
):
    """
    Worker reporta o resultado de uma task.
    status='awaiting_approval' → task entra em modo de aprovação humana.
    status='completed'/'failed' → task é encerrada.
    """
    _require_worker_token(authorization)

    task = _ws.get_task(payload.task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"task '{payload.task_id}' não encontrada")

    if payload.status == "awaiting_approval":
        updated = _ws.mark_awaiting_approval(
            task_id=payload.task_id,
            worker_id=payload.worker_id or task.worker_id,
            reason=payload.reason,
        )
        # Audit no sistema de agente principal também
        _write_audit(
            action_id=task.action_id or task.task_id,
            tool=task.tool,
            risk=task.risk,
            decision="awaiting_approval",
            session_id=task.session_id,
            target=str(task.args),
            error=payload.reason or "worker solicitou aprovação humana",
        )
        return {
            "success": True,
            "response": {
                "task_id": payload.task_id,
                "status": "awaiting_approval",
                "message": "task aguardando aprovação humana",
            },
        }

    ok = payload.status == "completed"
    updated = _ws.complete_task(
        task_id=payload.task_id,
        result=payload.result,
        ok=ok,
        error=payload.error,
    )

    # Audit no sistema de agente principal
    decision = "auto_executed" if ok else "failed"
    _write_audit(
        action_id=task.action_id or task.task_id,
        tool=task.tool,
        risk=task.risk,
        decision=decision,
        session_id=task.session_id,
        target=str(task.args),
        result_ok=ok,
        error=payload.error,
    )

    return {
        "success": True,
        "response": {
            "task_id": payload.task_id,
            "status": updated.status if updated else payload.status,
        },
    }


# ─── Approval Flow ────────────────────────────────────────────────────────────

@app.get("/worker/approvals")
def list_worker_approvals():
    """Lista tasks aguardando aprovação humana. Endpoint para a UI."""
    tasks = _ws.list_awaiting_approvals()
    return {
        "success": True,
        "response": {
            "pending_approvals": [t.model_dump() for t in tasks],
            "count": len(tasks),
        },
    }


@app.post("/worker/task/{task_id}/approve")
def approve_worker_task(
    task_id: str,
    payload: WorkerApprovalDecision,
):
    """
    UI aprova ou nega uma task em awaiting_approval.
    Se aprovado → task volta para 'pending', worker re-executa.
    Se negado → task encerrada como 'denied'.
    """
    task = _ws.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"task '{task_id}' não encontrada")
    if task.status != "awaiting_approval":
        raise HTTPException(
            status_code=400,
            detail=f"task '{task_id}' não está em awaiting_approval (status atual: {task.status})",
        )

    updated = _ws.approve_worker_task(
        task_id=task_id,
        approved_by=payload.approved_by or "admin",
        deny_reason=payload.deny_reason,
        approved=payload.approved,
    )

    decision = "approved" if payload.approved else "denied"
    _write_audit(
        action_id=task.action_id or task.task_id,
        tool=task.tool,
        risk=task.risk,
        decision=decision,
        session_id=task.session_id,
        target=str(task.args),
        error=payload.deny_reason if not payload.approved else "",
    )

    return {
        "success": True,
        "response": {
            "task_id": task_id,
            "decision": decision,
            "tool": task.tool,
            "risk": task.risk,
            "new_status": updated.status if updated else decision,
            "message": (
                "Task aprovada — worker irá re-executar na próxima poll."
                if payload.approved else
                f"Task negada — encerrada. Motivo: {payload.deny_reason or 'não informado'}"
            ),
        },
    }


@app.get("/worker/audit")
def worker_audit_log(
    limit: int = 50,
):
    """Audit log específico do worker."""
    entries = _ws.load_worker_audit(limit=limit)
    return {"success": True, "response": {"entries": entries, "count": len(entries)}}


# ─── Dispatch Helper — Brain cria tasks para o Worker ─────────────────────────

class WorkerDispatchRequest(BaseModel):
    """Payload para o Brain criar uma task e despachar para o Worker."""
    tool: str
    args: dict = Field(default_factory=dict)
    risk: str = "low"
    reason: str = ""
    session_id: str = ""
    action_id: str = ""
    requires_approval: bool = False


@app.post("/worker/dispatch")
def worker_dispatch(
    payload: WorkerDispatchRequest,
    authorization: str = _Header(default=""),
):
    """Brain cria uma nova task e a coloca na fila para o Worker pegar."""
    _require_worker_token(authorization)

    task = _ws.create_task(
        tool=payload.tool,
        args=payload.args,
        risk=payload.risk,
        reason=payload.reason,
        session_id=payload.session_id,
        action_id=payload.action_id,
        requires_approval=payload.requires_approval,
    )

    return {
        "success": True,
        "response": {
            "task_id": task.task_id,
            "status": task.status,
            "tool": task.tool,
            "risk": task.risk,
            "requires_approval": task.requires_approval,
        },
    }

# ═══════════════════════════════════════════════════════════════════════════════
# AGENT ENDPOINTS — Luna Autonomous Runtime
# ═══════════════════════════════════════════════════════════════════════════════

try:
    from .agent_runtime import AgentRuntime
    from .agent_state_store import (
        load_agent_config,
        load_last_plan,
        load_audit_log,
        approve_action,
        is_action_approved,
    )
    from .agent_models import AgentRequest, ApprovalDecision
except ImportError:
    from app.agent_runtime import AgentRuntime
    from app.agent_state_store import (
        load_agent_config,
        load_last_plan,
        load_audit_log,
        approve_action,
        is_action_approved,
    )
    from app.agent_models import AgentRequest, ApprovalDecision


def _get_agent_runtime() -> AgentRuntime:
    """Carrega a configuração do agente e retorna um runtime pronto para uso."""
    cfg = load_agent_config()
    return AgentRuntime(cfg)


@app.post("/agent/plan")
def agent_plan(payload: AgentRequest):
    """
    Gera um plano de ações para o objetivo informado.
    O plano é salvo em disco e retornado para revisão humana.
    """
    objective = (payload.objective or "").strip()
    if not objective:
        raise HTTPException(status_code=400, detail="objective is required")

    session_id = (payload.session_id or "").strip() or f"agent-{os.urandom(4).hex()}"
    runtime = _get_agent_runtime()

    # Sobrescreve target_root se informado no payload
    if payload.target_root:
        runtime.config.target_root = payload.target_root

    plan = runtime.plan(objective=objective, session_id=session_id)

    append_structured_log(
        event=EventType.TOOL_RESULT,
        trigger=objective[:200],
        action="agent_plan_generated",
        result="ok" if plan.mode != "blocked" else "blocked",
        project_id=get_active_workspace(),
        session_id=session_id,
        detail={"mode": plan.mode, "stop_reason": plan.stop_reason, "actions": len(plan.proposed_actions)},
    )

    return {"success": True, "response": plan.model_dump()}


@app.post("/agent/preview")
def agent_preview(payload: AgentRequest):
    """
    Retorna uma prévia do que o agente faria para o objetivo dado,
    sem executar nenhuma ação. Útil para revisão humana.
    """
    objective = (payload.objective or "").strip()
    if not objective:
        raise HTTPException(status_code=400, detail="objective is required")

    session_id = (payload.session_id or "").strip() or f"agent-{os.urandom(4).hex()}"
    runtime = _get_agent_runtime()

    if payload.target_root:
        runtime.config.target_root = payload.target_root

    plan = runtime.plan(objective=objective, session_id=session_id)

    previews = [runtime.preview(action) for action in plan.proposed_actions]

    return {
        "success": True,
        "response": {
            "objective": objective,
            "mode": plan.mode,
            "summary": plan.summary,
            "stop_reason": plan.stop_reason,
            "previews": previews,
        }
    }


@app.post("/agent/execute")
def agent_execute(payload: AgentRequest):
    """
    Executa o último plano gerado (ou gera e executa um novo).
    Ações que requerem aprovação são bloqueadas e retornam stop_reason='approval_required'.
    """
    objective = (payload.objective or "").strip()
    session_id = (payload.session_id or "").strip() or f"agent-{os.urandom(4).hex()}"
    runtime = _get_agent_runtime()

    if payload.target_root:
        runtime.config.target_root = payload.target_root

    # Carrega o último plano ou gera um novo
    last_plan = load_last_plan()
    if not last_plan or (objective and last_plan.objective != objective):
        last_plan = runtime.plan(objective=objective or "explorar workspace", session_id=session_id)

    if not last_plan.proposed_actions:
        return {
            "success": False,
            "response": {"error": "Nenhuma ação no plano.", "stop_reason": last_plan.stop_reason}
        }

    action = last_plan.proposed_actions[0]
    result = runtime.execute(action=action, session_id=session_id)

    append_structured_log(
        event=EventType.TOOL_RESULT,
        trigger=last_plan.objective[:200],
        action=f"agent_execute_{action.tool}",
        result="ok" if result.ok else "failed",
        project_id=get_active_workspace(),
        session_id=session_id,
        detail={
            "tool": result.tool,
            "ok": result.ok,
            "stop_reason": result.stop_reason,
            "error": result.error[:200] if result.error else "",
        },
    )

    return {"success": result.ok, "response": result.model_dump()}


@app.get("/agent/state")
def agent_state():
    """Retorna o estado atual do agente autônomo."""
    from .agent_state_store import load_agent_state
    state = load_agent_state()
    plan = load_last_plan()
    return {
        "success": True,
        "response": {
            "state": state.model_dump() if state else None,
            "last_plan": plan.model_dump() if plan else None,
        }
    }


@app.get("/agent/audit")
def agent_audit_log(limit: int = 50):
    """Retorna o audit log do agente autônomo."""
    entries = load_audit_log(limit=limit)
    # load_audit_log retorna list[dict], não list[AuditEntry]
    return {
        "success": True,
        "response": {
            "entries": entries,
            "count": len(entries),
        }
    }


@app.post("/agent/approve")
def agent_approve_action(payload: ApprovalDecision):
    """
    Aprova ou nega uma ação pendente do agente.
    Após aprovação, a ação pode ser executada via /agent/execute.
    """
    action_id = (payload.action_id or "").strip()
    if not action_id:
        raise HTTPException(status_code=400, detail="action_id is required")

    approve_action(
        action_id=action_id,
        approved=payload.approved,
        approved_by=payload.approved_by or "admin",
        deny_reason=payload.deny_reason or "",
    )

    decision = "approved" if payload.approved else "denied"
    append_structured_log(
        event=EventType.TOOL_RESULT,
        trigger=f"approval_{action_id}",
        action=f"agent_action_{decision}",
        result="ok",
        project_id=get_active_workspace(),
        detail={"action_id": action_id, "decision": decision},
    )

    return {
        "success": True,
        "response": {
            "action_id": action_id,
            "decision": decision,
            "message": f"Ação {action_id} foi {decision}.",
        }
    }

# ═══════════════════════════════════════════════════════════════════════════════
# /api/* — Endpoints consumidos pelo luna-desktop (frontend Vite/React)
# ═══════════════════════════════════════════════════════════════════════════════

# Runtime config store (in-memory, persiste enquanto o processo roda)
_runtime_config: dict = {
    "reflection_enabled": False,
    "zero_cloud_mode": False,
}

# ─── Workspace Real ────────────────────────────────────────────────────────────

@app.post("/api/workspace/register")
def api_workspace_register(body: dict = Body(...)):
    """
    Frontend chama este endpoint ao selecionar uma pasta via dialog.
    Registra o caminho real e retorna a árvore de arquivos para exibição.
    """
    import time as _time
    raw_path = (body.get("path") or "").strip()
    if not raw_path:
        raise HTTPException(status_code=400, detail="path is required")

    p = Path(raw_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Pasta não encontrada: {raw_path}")
    if not p.is_dir():
        raise HTTPException(status_code=400, detail="O caminho deve ser uma pasta")

    tree  = _scan_dir_tree(raw_path, max_files=200)
    # Conta arquivos usando os.walk — nunca acessa symlinks quebrados no Windows
    import os as _os_walk
    n_files = 0
    for _dpath, _ddirs, _dfiles in _os_walk.walk(raw_path, onerror=lambda e: None):
        # Não desce em dirs ignorados (node_modules, .git, etc.)
        _ddirs[:] = [d for d in _ddirs if d not in IGNORE_DIRS]
        n_files += len(_dfiles)

    # Stack detection
    stack_hints: list[str] = []
    for marker, label in [
        ("package.json",  "Node.js/JavaScript"),
        ("Cargo.toml",    "Rust"),
        ("go.mod",        "Go"),
        ("requirements.txt", "Python"),
        ("pyproject.toml", "Python"),
        ("pom.xml",       "Java/Maven"),
        ("Anchor.toml",   "Solana/Anchor"),
        ("hardhat.config.*", "Ethereum/Hardhat"),
        ("foundry.toml",  "Ethereum/Foundry"),
    ]:
        if list(p.glob(marker)):
            stack_hints.append(label)

    _real_workspace["path"]          = raw_path
    _real_workspace["name"]          = p.name
    _real_workspace["tree"]          = tree
    _real_workspace["registered_at"] = _time.time()

    logger.info(f"[workspace] Registrado: {raw_path} ({n_files} arquivos, stack: {stack_hints})")

    return {
        "success": True,
        "response": {
            "path":   raw_path,
            "name":   p.name,
            "files":  n_files,
            "stack":  stack_hints,
            "tree":   tree[:50],  # primeiros 50 para preview no frontend
        }
    }


@app.get("/api/workspace/current")
def api_workspace_current():
    """Retorna o workspace real atualmente registrado."""
    return {
        "success": True,
        "response": {
            "path": _real_workspace["path"],
            "name": _real_workspace["name"],
            "registered_at": _real_workspace["registered_at"],
        }
    }


@app.post("/api/workspace/scan-file")
def api_workspace_scan_file(body: dict = Body(...)):
    """
    Lê o conteúdo de um arquivo específico dentro do workspace registrado.
    Luna usa isso para analisar código com contexto real.
    """
    ws = _real_workspace["path"]
    if not ws:
        raise HTTPException(status_code=400, detail="Nenhum workspace registrado")

    rel = (body.get("file") or "").strip().lstrip("/\\")
    if not rel:
        raise HTTPException(status_code=400, detail="file is required")

    # Security: garante que o arquivo está dentro do workspace
    full_path = Path(ws) / rel
    try:
        resolved = full_path.resolve()
        ws_resolved = Path(ws).resolve()
        if not str(resolved).startswith(str(ws_resolved)):
            raise HTTPException(status_code=403, detail="Acesso negado")
    except Exception:
        raise HTTPException(status_code=403, detail="Caminho inválido")

    if not resolved.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
        # Limita tamanho para não explodir o contexto
        if len(content) > 60_000:
            content = content[:60_000] + "\n\n... [arquivo truncado — muito grande]"
        return {"success": True, "response": {"file": rel, "content": content, "size": len(content)}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# API keys store simples (in-memory; em produção use safeStorage via Electron)
_api_keys: dict[str, str] = {}

# Mapeamento de IDs curtos (frontend) → nomes de env var (backend)
_KEY_ENV_MAP: dict[str, str] = {
    "openai":    "OPENAI_API_KEY",
    "claude":    "ANTHROPIC_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq":      "GROQ_API_KEY",
    "grok":      "XAI_API_KEY",
    "xai":       "XAI_API_KEY",
    "gemini":    "GEMINI_API_KEY",
    "together":  "TOGETHER_API_KEY",
    # Passthrough: chaves já no formato correto (ex: vindas do App.tsx no startup)
    "OPENAI_API_KEY":    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY",
    "GROQ_API_KEY":      "GROQ_API_KEY",
    "XAI_API_KEY":       "XAI_API_KEY",
    "GROK_API_KEY":      "XAI_API_KEY",
    "GEMINI_API_KEY":    "GEMINI_API_KEY",
    "TOGETHER_API_KEY":  "TOGETHER_API_KEY",
}


@app.post("/api/config/keys")
def api_config_keys_set(body: dict = Body(...)):
    """
    Recebe API keys do Electron safeStorage e injeta como env vars em runtime.
    Aceita IDs curtos (openai, claude, groq...) ou nomes completos (OPENAI_API_KEY...).
    Reinicializa o LLM router após aplicar as keys.
    """
    keys: dict[str, str] = body.get("keys", {})
    if not isinstance(keys, dict):
        raise HTTPException(status_code=422, detail="'keys' deve ser um objeto {id: valor}")

    updated: list[str] = []
    for key_id, value in keys.items():
        if not isinstance(value, str) or not value.strip():
            continue
        env_name = _KEY_ENV_MAP.get(key_id) or _KEY_ENV_MAP.get(key_id.upper())
        if env_name:
            os.environ[env_name] = value.strip()
            _api_keys[env_name] = value.strip()
            updated.append(env_name)
            logger.info(f"[config/keys] {env_name} configurada via IPC")
        else:
            # Chave desconhecida — salva como está (pode ser custom)
            os.environ[key_id] = value.strip()
            _api_keys[key_id] = value.strip()
            updated.append(key_id)
            logger.info(f"[config/keys] {key_id} configurada (custom)")

    # Reinicializa o router para que ele detecte as novas keys
    if updated:
        try:
            from app.llm_router import reset_router
            reset_router()
            logger.info(f"[config/keys] Router reinicializado após {len(updated)} key(s)")
        except Exception as e:
            logger.warning(f"[config/keys] reset_router error: {e}")

    return {"success": True, "response": {"updated": updated, "total": len(updated)}}


@app.delete("/api/config/keys/{key_id}")
def api_config_keys_delete(key_id: str):
    """Remove uma API key do runtime (não afeta o safeStorage do Electron)."""
    env_name = _KEY_ENV_MAP.get(key_id) or _KEY_ENV_MAP.get(key_id.upper()) or key_id
    removed = False
    if env_name in os.environ:
        del os.environ[env_name]
        removed = True
    if env_name in _api_keys:
        del _api_keys[env_name]
        removed = True
    if removed:
        try:
            from app.llm_router import reset_router
            reset_router()
        except Exception:
            pass
    return {"success": True, "response": {"removed": env_name, "found": removed}}


@app.post("/api/config")
def api_config_update(body: dict = Body(...)):
    """Atualiza configurações de runtime (zero_cloud_mode, reflection_enabled, etc.)."""
    _runtime_config.update({k: v for k, v in body.items()})
    return {"success": True, "response": _runtime_config}


@app.get("/api/config")
def api_config_get():
    """Retorna configurações atuais de runtime."""
    return {"success": True, "response": _runtime_config}


@app.get("/api/providers/ollama/status")
def ollama_status():
    """Verifica se o Ollama está rodando localmente e lista modelos disponíveis."""
    import httpx as _httpx
    ollama_base = os.getenv("OLLAMA_URL", "http://localhost:11434/v1").rstrip("/").removesuffix("/v1")
    try:
        resp = _httpx.get(f"{ollama_base}/api/tags", timeout=3)
        resp.raise_for_status()
        models = [
            {"name": m["name"], "size_gb": round(m.get("size", 0) / 1e9, 1)}
            for m in resp.json().get("models", [])
        ]
        return {"running": True, "models": models, "url": ollama_base}
    except Exception:
        return {"running": False, "models": [], "url": ollama_base}


@app.post("/api/providers/ollama/pull")
def ollama_pull(body: dict = Body(...)):
    """Inicia pull de um modelo Ollama (fire-and-forget)."""
    import httpx as _httpx
    import threading
    model = (body.get("model") or "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="model is required")

    ollama_base = os.getenv("OLLAMA_URL", "http://localhost:11434/v1").rstrip("/").removesuffix("/v1")

    def _pull():
        try:
            _httpx.post(
                f"{ollama_base}/api/pull",
                json={"name": model},
                timeout=600,
            )
        except Exception as e:
            import logging
            logging.getLogger("luna.ollama").warning(f"Ollama pull error: {e}")

    threading.Thread(target=_pull, daemon=True).start()
    return {"success": True, "response": {"model": model, "status": "pulling"}}


# ═══════════════════════════════════════════════════════════════════════════════
# /api/projects — Sistema de projetos com chat isolado e memória persistente
# ═══════════════════════════════════════════════════════════════════════════════

_projects_db = None

def _get_projects_db():
    global _projects_db
    if _projects_db is None:
        try:
            from app.projects import ProjectsDB
        except ImportError:
            from .projects import ProjectsDB
        _projects_db = ProjectsDB()
    return _projects_db


@app.get("/api/projects")
def api_projects_list():
    """Lista todos os projetos ordenados por fixados e atividade recente."""
    try:
        db = _get_projects_db()
        projects = db.list_projects()
        return {"projects": projects}
    except Exception as e:
        logger.error(f"[projects] list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects")
def api_projects_create(body: dict = Body(...)):
    """Cria um novo projeto."""
    try:
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name é obrigatório")
        db = _get_projects_db()
        pid = db.create_project(
            name=name,
            path=body.get("path", ""),
            project_type=body.get("project_type", "other"),
            description=body.get("description", ""),
            color=body.get("color", "cyan"),
        )
        project = db.get_project(pid)
        return {"project": project, "id": pid}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[projects] create error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/projects/{project_id}")
def api_projects_get(project_id: int):
    """Busca um projeto específico por ID."""
    try:
        db = _get_projects_db()
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Projeto não encontrado")
        return {"project": project}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[projects] get error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/projects/{project_id}")
def api_projects_update(project_id: int, body: dict = Body(...)):
    """Atualiza campos de um projeto (name, path, description, color, pinned)."""
    try:
        db = _get_projects_db()
        ok = db.update_project(project_id, **body)
        if not ok:
            raise HTTPException(status_code=404, detail="Projeto não encontrado ou sem campos para atualizar")
        project = db.get_project(project_id)
        return {"project": project}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[projects] update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/projects/{project_id}")
def api_projects_delete(project_id: int):
    """Exclui um projeto e todas as suas mensagens e fatos (CASCADE)."""
    try:
        db = _get_projects_db()
        ok = db.delete_project(project_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Projeto não encontrado")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[projects] delete error: {e}")
        raise HTTPExcepti