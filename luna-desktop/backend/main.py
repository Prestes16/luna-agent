#!/usr/bin/env python3
"""
Luna Desktop Backend - FastAPI Server
Elite Autonomous AI Agent Backend
"""

import os
import sys
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

# ── Load .env BEFORE any other import that reads env vars ──────────────────────
# Tries: backend/.env → luna-desktop/.env → luna-agent/.env (root)
from dotenv import load_dotenv
for _env in [
    Path(__file__).parent / ".env",
    Path(__file__).parent.parent / ".env",
    Path(__file__).parent.parent.parent / ".env",
]:
    if _env.exists():
        load_dotenv(_env, override=False)
        break

import json as _json

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

# ── SSRF guard ────────────────────────────────────────────────────────────────
import ipaddress as _ipaddress
import urllib.parse as _urlparse

_SSRF_BLOCKED_NETWORKS = [
    _ipaddress.ip_network('127.0.0.0/8'),      # loopback
    _ipaddress.ip_network('10.0.0.0/8'),        # private class A
    _ipaddress.ip_network('172.16.0.0/12'),     # private class B
    _ipaddress.ip_network('192.168.0.0/16'),    # private class C
    _ipaddress.ip_network('169.254.0.0/16'),    # link-local / AWS metadata
    _ipaddress.ip_network('::1/128'),           # IPv6 loopback
    _ipaddress.ip_network('fc00::/7'),          # IPv6 private
]

def _is_ssrf_safe(url: str) -> bool:
    """Return True only if the URL hostname resolves to a public IP."""
    try:
        parsed = _urlparse.urlparse(url)
        host = parsed.hostname or ''
        # Reject plain IP references to internal ranges
        try:
            addr = _ipaddress.ip_address(host)
            return not any(addr in net for net in _SSRF_BLOCKED_NETWORKS)
        except ValueError:
            # hostname — block common internal names even before DNS
            blocked_hosts = {'localhost', 'metadata', 'metadata.google.internal'}
            if host.lower() in blocked_hosts:
                return False
            # We cannot do DNS resolution here (sync); block by pattern instead
            if host.endswith('.local') or host.endswith('.internal'):
                return False
            return True
    except Exception:
        return False

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from app.luna_engine import LunaEngine
from app.models import ChatRequest, ChatResponse
from app.project_store import ProjectNotFoundError, ProjectStore, ProjectValidationError
from app.security import LunaSecurityMiddleware, audit, sanitizer
from services.code_analyzer import CodeAnalyzer
from services.security_scanner import SecurityScanner
from services.blockchain_service import BlockchainService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
luna_engine: Optional[LunaEngine] = None
code_analyzer: Optional[CodeAnalyzer] = None
security_scanner: Optional[SecurityScanner] = None
blockchain_service: Optional[BlockchainService] = None
project_store = ProjectStore()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global luna_engine, code_analyzer, security_scanner, blockchain_service
    
    logger.info("Luna Desktop Backend Starting...")
    
    # Initialize services
    luna_engine = LunaEngine()
    code_analyzer = CodeAnalyzer()
    security_scanner = SecurityScanner()
    blockchain_service = BlockchainService()
    
    logger.info("All services initialized")
    
    yield
    
    logger.info("Luna Desktop Backend Shutting down...")

# Create FastAPI app
app = FastAPI(
    title="Luna Desktop Backend",
    description="Elite Autonomous AI Agent Backend API",
    version="3.0.0",
    lifespan=lifespan
)

# ── Security Middleware (deve ser adicionado ANTES do CORS) ──────────────────
# Ordem: request entra → LunaSecurity → CORS → rotas
# Starlette aplica middlewares em ordem reversa de registro,
# então adicionamos Security primeiro para que execute por último no request
# mas primeiro no response (headers de segurança aparecem em todas as respostas)
app.add_middleware(LunaSecurityMiddleware)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-Luna-Token", "X-Session-Id"],
)

# ============================================================================
# Health & Status Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    diagnostics = luna_engine.get_local_diagnostics() if luna_engine else {
        "ollama": False,
        "ollama_base_url": "http://localhost:11434/v1",
        "default_model": "luna-cyber-fast",
        "zero_cloud_mode": True,
        "supervised_mode": True,
        "config_dir": os.getenv("LUNA_CONFIG_DIR", r"D:\LunaCyber\config"),
        "modules": {"mentor_kali_devtools": {"found": False, "loaded": False, "enabled": True}},
    }
    available_models: list[str] = []
    if diagnostics.get("ollama"):
        try:
            from app.luna_engine import _ollama_list_models_async
            available_models = await _ollama_list_models_async()
        except Exception:
            available_models = []
    return {
        "status": "healthy",
        "service": "Luna Desktop Backend",
        "version": "3.0.0",
        "model": diagnostics["default_model"],
        "mode": "local_copilot",
        "available_models": available_models,
        **diagnostics,
    }

@app.get("/lessons")
async def get_lessons():
    """Lesson / interaction stats for the dashboard"""
    return {
        "total_lessons": 0,
        "by_type": {
            "chat":     {"total": 0, "success": 0},
            "code":     {"total": 0, "success": 0},
            "security": {"total": 0, "success": 0},
            "blockchain": {"total": 0, "success": 0},
        }
    }

@app.get("/status")
async def status():
    """Get backend status"""
    return {
        "luna_engine": "ready" if luna_engine else "not_initialized",
        "code_analyzer": "ready" if code_analyzer else "not_initialized",
        "security_scanner": "ready" if security_scanner else "not_initialized",
        "blockchain_service": "ready" if blockchain_service else "not_initialized"
    }


# ============================================================================
# Local Projects — JSON UTF-8 atômico em LUNA_PROJECTS_DIR
# ============================================================================

class LocalProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    path: str = ""
    project_type: str = "other"
    description: str = ""
    color: str = "cyan"


class LocalProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = None
    path: Optional[str] = None
    project_type: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    pinned: Optional[bool] = None


class LocalProjectMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str
    content: str
    model: str = ""


class LocalProjectFactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fact: str


def _raise_project_http_error(error: Exception) -> None:
    if isinstance(error, ProjectNotFoundError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, ProjectValidationError):
        raise HTTPException(status_code=422, detail=str(error)) from error
    raise error


@app.get("/api/projects")
async def list_local_projects():
    return {"projects": project_store.list_projects()}


@app.post("/api/projects", status_code=201)
async def create_local_project(body: LocalProjectCreate):
    try:
        return project_store.create_project(body.model_dump())
    except (ProjectValidationError, ProjectNotFoundError) as error:
        _raise_project_http_error(error)


@app.put("/api/projects/{project_id}")
async def update_local_project(project_id: int, body: LocalProjectUpdate):
    try:
        return project_store.update_project(project_id, body.model_dump(exclude_unset=True))
    except (ProjectValidationError, ProjectNotFoundError) as error:
        _raise_project_http_error(error)


@app.delete("/api/projects/{project_id}")
async def delete_local_project(project_id: int):
    try:
        project_store.delete_project(project_id)
        return {"deleted": True, "id": project_id}
    except (ProjectValidationError, ProjectNotFoundError) as error:
        _raise_project_http_error(error)


@app.get("/api/projects/{project_id}/messages")
async def list_local_project_messages(project_id: int):
    try:
        return {"messages": project_store.list_messages(project_id)}
    except (ProjectValidationError, ProjectNotFoundError) as error:
        _raise_project_http_error(error)


@app.post("/api/projects/{project_id}/messages", status_code=201)
async def create_local_project_message(project_id: int, body: LocalProjectMessageCreate):
    try:
        return project_store.add_message(project_id, body.model_dump())
    except (ProjectValidationError, ProjectNotFoundError) as error:
        _raise_project_http_error(error)


@app.get("/api/projects/{project_id}/facts")
async def list_local_project_facts(project_id: int):
    try:
        return {"facts": project_store.list_facts(project_id)}
    except (ProjectValidationError, ProjectNotFoundError) as error:
        _raise_project_http_error(error)


@app.post("/api/projects/{project_id}/facts", status_code=201)
async def create_local_project_fact(project_id: int, body: LocalProjectFactCreate):
    try:
        return {"facts": project_store.add_fact(project_id, body.fact)}
    except (ProjectValidationError, ProjectNotFoundError) as error:
        _raise_project_http_error(error)


@app.get("/api/projects/{project_id}/context")
async def get_local_project_context(project_id: int):
    try:
        return {"context": project_store.context(project_id)}
    except (ProjectValidationError, ProjectNotFoundError) as error:
        _raise_project_http_error(error)


@app.post("/api/projects/{project_id}/compress")
async def compress_local_project(project_id: int):
    try:
        return project_store.compress(project_id)
    except (ProjectValidationError, ProjectNotFoundError) as error:
        _raise_project_http_error(error)

# ============================================================================
# Text-to-Speech — Luna Voice
# ============================================================================

class SpeakRequest(BaseModel):
    text: str
    voice: str = "nova"        # OpenAI voice: nova, shimmer, alloy, coral, echo, fable
    speed: float = 1.0         # 0.25 – 4.0
    model: str = "tts-1-hd"   # tts-1 (fast) or tts-1-hd (premium)

@app.post("/speak")
async def speak(req: SpeakRequest):
    """
    Synthesize text to MP3 audio using OpenAI TTS.
    Falls back gracefully if no OpenAI key is configured.
    Voice: nova (feminine, warm, clear) — configurable via request.
    """
    import tempfile
    from pathlib import Path as _Path
    from fastapi.responses import Response as _Response

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key não configurada. Configure em Settings > Provedores para ativar voz."
        )

    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text vazio")

    # Limit to 4096 chars (OpenAI limit for TTS)
    if len(text) > 4096:
        text = text[:4096]

    try:
        from openai import AsyncOpenAI as _OAI
        client = _OAI(api_key=openai_key)

        # TTS instructions for Luna's voice persona
        response = await client.audio.speech.create(
            model=req.model,
            voice=req.voice,          # type: ignore[arg-type]
            input=text,
            speed=req.speed,
            response_format="mp3",
        )

        audio_bytes = response.content
        return _Response(content=audio_bytes, media_type="audio/mpeg",
                         headers={"Cache-Control": "no-store"})

    except Exception as e:
        logger.error(f"[TTS] error: {e}")
        raise HTTPException(status_code=500, detail=f"TTS error: {e}")


@app.get("/speak/voices")
async def list_voices():
    """Available OpenAI TTS voices and their personality."""
    return {
        "voices": [
            {"id": "nova",    "label": "Nova (Padrão Luna)",  "style": "feminina, calorosa, clara"},
            {"id": "shimmer", "label": "Shimmer",             "style": "feminina, suave, expressiva"},
            {"id": "coral",   "label": "Coral",               "style": "feminina, energética"},
            {"id": "alloy",   "label": "Alloy",               "style": "neutra, profissional"},
            {"id": "echo",    "label": "Echo",                "style": "masculina, profunda"},
            {"id": "fable",   "label": "Fable",               "style": "narrativa, dramática"},
            {"id": "onyx",    "label": "Onyx",                "style": "masculina, grave"},
        ],
        "models": [
            {"id": "tts-1",    "label": "Rápido",   "desc": "Menor latência"},
            {"id": "tts-1-hd", "label": "Premium",  "desc": "Maior qualidade (Luna usa este)"},
        ]
    }


# ============================================================================
# Primary Chat Endpoint — SSE Streaming (used by the frontend)
# ============================================================================

@app.post("/chat/agent/stream")
async def chat_agent_stream(request: Request):
    """
    Server-Sent Events endpoint for streaming Luna responses.
    Frontend sends: {message, session_id, model, workspace_path?}
    Emits SSE events: text_chunk | tool_start | tool_done | done | error
    """
    if not luna_engine:
        raise HTTPException(status_code=503, detail="Luna engine not initialized")

    body           = await request.json()
    message        = body.get("message", "").strip()
    session_id     = str(body.get("session_id", "default") or "default")[:128]
    model_str      = body.get("model", "luna-cyber-fast")
    workspace_path = body.get("workspace_path") or None  # may be null/None
    user_context   = body.get("user_context") or None
    project_context = None
    project_match = re.fullmatch(r"project-(\d{1,10})", session_id)
    if project_match:
        try:
            project_context = project_store.retrieval_context(
                int(project_match.group(1)),
                message or "contexto atual",
            )
        except (ProjectValidationError, ProjectNotFoundError):
            logger.info("[chat] Projeto da sessão não foi encontrado: %s", session_id)

    # Imagens para visão multimodal — lista de {data: base64, mime: "image/png"}
    raw_images = body.get("images") or []
    images = None
    if raw_images and isinstance(raw_images, list):
        # Valida e limita: max 4 imagens, max 5MB cada (base64 ~7MB raw)
        MAX_IMGS   = 4
        MAX_B64_LEN = 7 * 1024 * 1024 // 1  # ~5MB raw → ~7MB base64
        validated = []
        for img in raw_images[:MAX_IMGS]:
            if isinstance(img, dict) and "data" in img:
                b64 = img["data"]
                if len(b64) <= MAX_B64_LEN:
                    validated.append({
                        "data": b64,
                        "mime": img.get("mime", "image/png"),
                    })
        images = validated or None

    if not message and not images:
        raise HTTPException(status_code=400, detail="message ou images é obrigatório")
    if not message:
        message = "Analise esta imagem."  # fallback quando só imagem é enviada

    async def generate():
        full_text = ""
        try:
            async for event_json in luna_engine.stream_agent(
                message=message,
                session_id=session_id,
                model_str=model_str,
                workspace_path=workspace_path,
                images=images,
                user_context=user_context,
                project_context=project_context,
            ):
                # event_json is already a JSON string like {"type":..., ...}
                try:
                    ev = _json.loads(event_json)
                    if ev.get("type") == "text_chunk":
                        full_text += ev.get("text", "")
                except Exception:
                    pass
                yield f"data: {event_json}\n\n"

            done_event = _json.dumps({"type": "done", "final_text": full_text})
            yield f"data: {done_event}\n\n"

        except Exception as exc:
            logger.error(f"[chat/agent/stream] error: {exc}")
            err_event = _json.dumps({"type": "error", "message": str(exc)})
            yield f"data: {err_event}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

# ============================================================================
# Bug Report Endpoint
# ============================================================================

BUG_REPORT_FILE = Path(__file__).parent / "bug_reports.jsonl"

@app.post("/bug-report")
async def receive_bug_report(request: Request):
    """
    Receives bug reports from the frontend, stores locally,
    and optionally forwards to a configured webhook (Discord, Slack, email relay).
    """
    import httpx as _httpx
    import datetime as _dt

    body        = await request.json()
    reports     = body.get("reports", [])
    webhook_url = body.get("webhook_url", "").strip()
    platform    = body.get("platform", "unknown")
    sent_at     = body.get("sent_at", _dt.datetime.utcnow().isoformat())

    if not reports:
        raise HTTPException(status_code=400, detail="No reports provided")

    # ── Persist to JSONL file ────────────────────────────────────────────────
    try:
        with open(BUG_REPORT_FILE, "a", encoding="utf-8") as f:
            for r in reports:
                entry = {**r, "platform": platform, "received_at": sent_at}
                f.write(_json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info(f"[bug-report] Stored {len(reports)} report(s)")
    except Exception as e:
        logger.error(f"[bug-report] Failed to write: {e}")

    # ── Forward to webhook (Discord format) ──────────────────────────────────
    forwarded = False
    if webhook_url and webhook_url.startswith("https://") and _is_ssrf_safe(webhook_url):
        try:
            SEVERITY_COLORS = {
                "critical": 0xFF0000, "error": 0xFF6B35,
                "warning":  0xFFD93D, "info":  0x4ECDC4,
            }
            SEVERITY_EMOJI = {
                "critical": "🔴", "error": "🟠", "warning": "🟡", "info": "🔵"
            }
            embeds = []
            for r in reports[:10]:  # Discord limit
                sev   = r.get("severity", "error")
                color = SEVERITY_COLORS.get(sev, 0xFF6B35)
                emoji = SEVERITY_EMOJI.get(sev, "🟠")
                fields = [
                    {"name": "Severity",  "value": f"{emoji} {sev.upper()}", "inline": True},
                    {"name": "Timestamp", "value": _dt.datetime.fromtimestamp(
                        r.get("timestamp", 0) / 1000).strftime('%Y-%m-%d %H:%M:%S'), "inline": True},
                    {"name": "Platform",  "value": platform, "inline": True},
                ]
                if r.get("context"):
                    ctx_text = "\n".join(f"`{k}`: {v}" for k, v in r["context"].items())
                    fields.append({"name": "Context", "value": ctx_text[:1024], "inline": False})
                if r.get("stack"):
                    fields.append({
                        "name": "Stack Trace",
                        "value": f"```\n{r['stack'][:1000]}\n```",
                        "inline": False,
                    })
                if r.get("userNote"):
                    fields.append({"name": "📝 Nota do usuário", "value": r["userNote"][:500], "inline": False})

                embeds.append({
                    "title": f"🐛 Luna Bug Report — {r.get('title', 'Sem título')[:200]}",
                    "description": r.get("message", "")[:2048],
                    "color": color,
                    "fields": fields,
                    "footer": {"text": f"Luna Agent v3.0 • {sent_at[:10]}"},
                })

            async with _httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook_url, json={"embeds": embeds})
                if resp.status_code in (200, 204):
                    forwarded = True
                    logger.info(f"[bug-report] Forwarded to webhook OK")
                else:
                    logger.warning(f"[bug-report] Webhook returned {resp.status_code}")
        except Exception as e:
            logger.error(f"[bug-report] Webhook error: {e}")

    return {
        "ok": True,
        "stored": len(reports),
        "forwarded": forwarded,
    }


@app.get("/bug-report")
async def list_bug_reports(limit: int = 50):
    """Return stored bug reports (most recent first)."""
    try:
        if not BUG_REPORT_FILE.exists():
            return {"reports": []}
        reports = []
        with open(BUG_REPORT_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        reports.append(_json.loads(line))
                    except Exception:
                        pass
        return {"reports": list(reversed(reports[-limit:]))}
    except Exception as e:
        return {"reports": [], "error": str(e)}


@app.delete("/bug-report")
async def clear_bug_reports():
    """Clear all stored bug reports."""
    try:
        if BUG_REPORT_FILE.exists():
            BUG_REPORT_FILE.unlink()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================================
# Legacy Chat Endpoints
# ============================================================================

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Send a message to Luna and get a response
    """
    if not luna_engine:
        raise HTTPException(status_code=503, detail="Luna engine not initialized")
    
    try:
        response = await luna_engine.process_message(
            message=request.message,
            conversation_id=request.conversation_id,
            model=request.model
        )
        return response
    except Exception as e:
        logger.error(f"Error processing chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Stream a response from Luna
    """
    if not luna_engine:
        raise HTTPException(status_code=503, detail="Luna engine not initialized")
    
    return await luna_engine.stream_response(
        message=request.message,
        conversation_id=request.conversation_id,
        model=request.model
    )

# ============================================================================
# Code Analysis Endpoints
# ============================================================================

_MAX_UPLOAD_BYTES = 1 * 1024 * 1024  # 1 MB — prevent OOM from huge uploads

@app.post("/api/analyze-code")
async def analyze_code(file: UploadFile = File(...)):
    """
    Analyze uploaded code file (max 1 MB).
    """
    if not code_analyzer:
        raise HTTPException(status_code=503, detail="Code analyzer not initialized")

    try:
        content = await file.read(_MAX_UPLOAD_BYTES + 1)
        if len(content) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"Arquivo muito grande (máx {_MAX_UPLOAD_BYTES // 1024} KB)")
        analysis = await code_analyzer.analyze(
            content=content.decode('utf-8', errors='replace'),
            filename=file.filename,
        )
        return analysis
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing code: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze-project")
async def analyze_project(path: str):
    """
    Analyze entire project directory.
    SECURITY: path must be an existing directory — no traversal allowed.
    """
    if not code_analyzer:
        raise HTTPException(status_code=503, detail="Code analyzer not initialized")

    # Validate that path is a real, accessible directory (prevents traversal / arbitrary reads)
    resolved = Path(path).resolve()
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Caminho inválido ou não é um diretório")

    try:
        analysis = await code_analyzer.analyze_project(str(resolved))
        return analysis
    except Exception as e:
        logger.error(f"Error analyzing project: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Security Endpoints
# ============================================================================

@app.post("/api/security/scan")
async def security_scan(file: UploadFile = File(...)):
    """
    Scan file for security vulnerabilities (max 1 MB).
    """
    if not security_scanner:
        raise HTTPException(status_code=503, detail="Security scanner not initialized")

    try:
        content = await file.read(_MAX_UPLOAD_BYTES + 1)
        if len(content) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"Arquivo muito grande (máx {_MAX_UPLOAD_BYTES // 1024} KB)")
        scan_result = await security_scanner.scan(
            content=content.decode('utf-8', errors='replace'),
            filename=file.filename,
        )
        return scan_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scanning security: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/security/status")
async def security_status():
    """
    Get security status
    """
    if not security_scanner:
        raise HTTPException(status_code=503, detail="Security scanner not initialized")
    
    return await security_scanner.get_status()

# ============================================================================
# Blockchain Endpoints
# ============================================================================

@app.get("/api/blockchain/wallet")
async def get_wallet():
    """
    Get Solana wallet information
    """
    if not blockchain_service:
        raise HTTPException(status_code=503, detail="Blockchain service not initialized")
    
    return await blockchain_service.get_wallet_info()

@app.post("/api/blockchain/transaction")
async def create_transaction(to_address: str, amount: float):
    """
    Create a Solana transaction
    """
    if not blockchain_service:
        raise HTTPException(status_code=503, detail="Blockchain service not initialized")
    
    try:
        tx = await blockchain_service.create_transaction(to_address, amount)
        return tx
    except Exception as e:
        logger.error(f"Error creating transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/blockchain/transactions")
async def get_transactions(limit: int = 10):
    """
    Get recent transactions
    """
    if not blockchain_service:
        raise HTTPException(status_code=503, detail="Blockchain service not initialized")
    
    return await blockchain_service.get_transactions(limit)

# ============================================================================
# Memory Endpoints
# ============================================================================

@app.get("/api/memory/short-term")
async def get_short_term_memory(conversation_id: str):
    """
    Get short-term memory for conversation
    """
    if not luna_engine:
        raise HTTPException(status_code=503, detail="Luna engine not initialized")
    
    return await luna_engine.get_short_term_memory(conversation_id)

@app.get("/api/memory/long-term")
async def get_long_term_memory(query: str, limit: int = 5):
    """
    Search long-term memory
    """
    if not luna_engine:
        raise HTTPException(status_code=503, detail="Luna engine not initialized")
    
    return await luna_engine.search_long_term_memory(query, limit)

@app.post("/api/memory/clear")
async def clear_memory(conversation_id: str):
    """
    Clear memory for conversation
    """
    if not luna_engine:
        raise HTTPException(status_code=503, detail="Luna engine not initialized")
    
    await luna_engine.clear_memory(conversation_id)
    return {"status": "cleared"}

# ============================================================================
# Configuration Endpoints
# ============================================================================

@app.get("/api/config")
async def get_config():
    """
    Get Luna configuration
    """
    if not luna_engine:
        raise HTTPException(status_code=503, detail="Luna engine not initialized")
    
    return await luna_engine.get_config()

_CONFIG_WHITELIST = {
    'default_model', 'temperature', 'max_tokens', 'zero_cloud_mode',
    'mentor_mode', 'reflection_enabled',
}

@app.post("/api/config")
async def update_config(config: dict):
    """
    Update allowed Luna configuration fields (whitelist enforced).
    """
    if not luna_engine:
        raise HTTPException(status_code=503, detail="Luna engine not initialized")

    # Strip any keys not in the whitelist to prevent injection of arbitrary config
    safe_config = {k: v for k, v in config.items() if k in _CONFIG_WHITELIST}
    if not safe_config:
        raise HTTPException(status_code=400, detail=f"Nenhum campo válido. Permitidos: {_CONFIG_WHITELIST}")

    await luna_engine.update_config(safe_config)
    return {"status": "updated", "applied": list(safe_config.keys())}

# ============================================================================
# Ollama Status Endpoint
# ============================================================================

@app.get("/api/providers/ollama/status")
async def ollama_status():
    """
    Verifica se o Ollama está rodando localmente e retorna os modelos disponíveis.
    Usado pelo frontend para mostrar quais modelos locais estão instalados.
    """
    import httpx as _httpx
    from app.luna_engine import _ollama_is_available_sync, OLLAMA_API_ROOT, OLLAMA_BASE_URL

    running = _ollama_is_available_sync()
    models: list = []
    if running:
        try:
            async with _httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{OLLAMA_API_ROOT}/api/tags")
                if r.status_code == 200:
                    data = r.json()
                    models = [
                        {
                            "name": m["name"],
                            "size_gb": round(m.get("size", 0) / 1e9, 1),
                            "modified": m.get("modified_at", ""),
                        }
                        for m in data.get("models", [])
                    ]
        except Exception:
            pass

    return {
        "running": running,
        "base_url": OLLAMA_BASE_URL,
        "models": models,
        "recommended": ["luna-cyber-fast", "qwen3.5:4b"],
    }

@app.post("/api/providers/ollama/pull")
async def ollama_pull(body: dict):
    """
    Instrui o Ollama a baixar um modelo. Retorna status imediatamente —
    o download roda em background no Ollama daemon.
    """
    import httpx as _httpx
    model = body.get("model", "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="model é obrigatório")
    try:
        async with _httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post("http://localhost:11434/api/pull",
                                  json={"name": model, "stream": False})
            return {"status": "pulling", "model": model, "ollama_response": r.status_code}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama não disponível: {e}")

# ============================================================================
# API Keys Endpoint — recebe chaves do Electron (safeStorage) em runtime
# ============================================================================

_KEY_ENV_MAP: dict[str, str] = {
    "openai":    "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq":      "GROQ_API_KEY",
    "coingecko": "COINGECKO_API_KEY",
}

class KeysPayload(BaseModel):
    keys: dict  # {"openai": "sk-...", "anthropic": "sk-ant-..."}

@app.post("/api/config/keys")
async def update_api_keys(payload: KeysPayload):
    """
    Recebe API keys enviadas pelo Electron (via safeStorage) e as injeta nas
    variáveis de ambiente do processo Python, reinicializando os clientes LLM.
    Endpoint protegido por X-Luna-Token (via LunaSecurityMiddleware).
    """
    if not luna_engine:
        raise HTTPException(status_code=503, detail="Luna engine not initialized")

    updated: list[str] = []
    for provider, value in payload.keys.items():
        env_key = _KEY_ENV_MAP.get(provider.lower())
        if not env_key:
            continue  # ignora provedores desconhecidos
        if not isinstance(value, str) or not value.strip():
            continue  # ignora valores vazios
        os.environ[env_key] = value.strip()
        updated.append(provider)
        audit.log_security_event(
            "api_key_updated", f"provider={provider}", ip="localhost"
        )

    # Reinicializa os clientes LLM com as novas keys
    if updated and hasattr(luna_engine, '_reinit_clients'):
        try:
            luna_engine._reinit_clients()
        except Exception as e:
            logger.warning(f"[keys] _reinit_clients error: {e}")

    logger.info(f"[keys] Atualizadas: {updated}")
    return {"status": "ok", "updated": updated}

@app.delete("/api/config/keys/{provider}")
async def delete_api_key(provider: str):
    """Remove uma API key do ambiente (não apaga do safeStorage)."""
    env_key = _KEY_ENV_MAP.get(provider.lower())
    if not env_key:
        raise HTTPException(status_code=404, detail=f"Provedor desconhecido: {provider}")
    os.environ.pop(env_key, None)
    audit.log_security_event("api_key_removed", f"provider={provider}", ip="localhost")
    return {"status": "ok", "removed": provider}

@app.get("/api/config/keys")
async def list_api_keys():
    """Lista quais provedores têm key configurada (sem expor os valores)."""
    result = {}
    for provider, env_key in _KEY_ENV_MAP.items():
        val = os.getenv(env_key, "")
        result[provider] = {
            "configured": bool(val),
            "preview": f"{val[:4]}...{val[-4:]}" if len(val) > 8 else ("***" if val else ""),
        }
    return result

# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Luna Desktop Backend...")
    uvicorn.run(
        app,
        # SECURITY: bind only to loopback — Electron connects via localhost.
        # 0.0.0.0 would expose the API (with full filesystem + AI access) to the
        # entire LAN without any authentication.
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )
