"""
backend/app/security.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Módulo central de segurança da Luna.

Classes:
  AuditLogger              — log estruturado JSONL com auto-rotação
  SlidingWindowRateLimiter — limita req/min por chave (IP ou session)
  InputSanitizer           — valida e higieniza entradas da API
  LunaSecurityMiddleware   — middleware ASGI: auth + rate-limit + headers + audit

Uso em main.py:
  from app.security import LunaSecurityMiddleware, AuditLogger
  app.add_middleware(LunaSecurityMiddleware)
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import time
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

log = logging.getLogger("luna.security")

# ═══════════════════════════════════════════════════════════════════════════
#  TOKEN — gerado pelo Electron no startup e injetado via env var
# ═══════════════════════════════════════════════════════════════════════════
LUNA_API_TOKEN: Optional[str] = os.getenv("LUNA_API_TOKEN")

# Rotas que NÃO precisam de token (health checks públicos)
_PUBLIC_PATHS: frozenset[str] = frozenset({
    "/health",
    "/status",
    "/docs",
    "/openapi.json",
    "/redoc",
})

# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _constant_time_eq(a: str, b: str) -> bool:
    """
    Comparação de strings em tempo constante usando HMAC para evitar
    timing attacks mesmo quando os tamanhos diferem.
    """
    # Normaliza para bytes com hash fixo
    ha = hashlib.sha256(a.encode()).digest()
    hb = hashlib.sha256(b.encode()).digest()
    return hmac.compare_digest(ha, hb)


def _get_client_ip(request: Request) -> str:
    """Extrai IP real do cliente, respeitando X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Pega o primeiro IP da cadeia (o mais próximo do cliente)
        ip = forwarded.split(",")[0].strip()
        # Valida se é um IP real
        try:
            ipaddress.ip_address(ip)
            return ip
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"


# ═══════════════════════════════════════════════════════════════════════════
#  AUDIT LOGGER
# ═══════════════════════════════════════════════════════════════════════════

class AuditLogger:
    """
    Logger de auditoria estruturado em JSONL.
    Auto-rotaciona o arquivo quando atinge max_bytes (padrão 10 MB).
    Thread-safe via lock interno.
    """

    _MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB

    def __init__(self, log_dir: str = "logs", filename: str = "audit.jsonl") -> None:
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / filename
        self._lock = threading.Lock()

    def _rotate(self) -> None:
        """Renomeia o log atual com timestamp e cria novo arquivo."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive = self._dir / f"audit_{ts}.jsonl"
        try:
            self._path.rename(archive)
            log.info(f"[AuditLogger] Rotacionado para {archive.name}")
        except Exception as e:
            log.warning(f"[AuditLogger] Falha na rotação: {e}")

    def write(self, event: str, data: Dict[str, Any]) -> None:
        """Escreve uma entrada de auditoria."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **data,
        }
        line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            try:
                if self._path.exists() and self._path.stat().st_size >= self._MAX_BYTES:
                    self._rotate()
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(line)
            except Exception as e:
                log.error(f"[AuditLogger] Erro ao escrever: {e}")

    def log_request(
        self,
        method: str,
        path: str,
        ip: str,
        status: int,
        session_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
    ) -> None:
        self.write("http_request", {
            "method": method,
            "path": path,
            "ip": ip,
            "status": status,
            "session_id": session_id,
            "duration_ms": round(duration_ms, 2) if duration_ms else None,
        })

    def log_tool_call(
        self,
        tool: str,
        session_id: str,
        args_summary: str,
        result_ok: bool,
    ) -> None:
        self.write("tool_call", {
            "tool": tool,
            "session_id": session_id,
            "args_summary": args_summary[:200],
            "result_ok": result_ok,
        })

    def log_auth_failure(self, ip: str, path: str, reason: str) -> None:
        self.write("auth_failure", {
            "ip": ip,
            "path": path,
            "reason": reason,
        })

    def log_rate_limit(self, key: str, path: str) -> None:
        self.write("rate_limit", {
            "key": key,
            "path": path,
        })

    def log_security_event(self, event_type: str, detail: str, ip: str) -> None:
        self.write("security_event", {
            "type": event_type,
            "detail": detail[:500],
            "ip": ip,
        })


# Instância global — importada por tools.py e luna_engine.py
audit = AuditLogger()


# ═══════════════════════════════════════════════════════════════════════════
#  SLIDING WINDOW RATE LIMITER
# ═══════════════════════════════════════════════════════════════════════════

class SlidingWindowRateLimiter:
    """
    Rate limiter com janela deslizante.
    Mantém timestamps de requisições em deque por chave.
    Thread-safe via lock por chave.

    Parâmetros:
      max_requests — máximo de requisições na janela
      window_secs  — tamanho da janela em segundos
    """

    def __init__(self, max_requests: int = 60, window_secs: int = 60) -> None:
        self._max = max_requests
        self._window = window_secs
        self._store: Dict[str, deque] = defaultdict(deque)
        self._locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._global_lock = threading.Lock()

    def _get_lock(self, key: str) -> threading.Lock:
        with self._global_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]

    def is_allowed(self, key: str) -> bool:
        """Retorna True se a requisição for permitida, False se bloqueada."""
        now = time.monotonic()
        cutoff = now - self._window
        lock = self._get_lock(key)

        with lock:
            q = self._store[key]
            # Remove timestamps fora da janela
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self._max:
                return False
            q.append(now)
            return True

    def get_count(self, key: str) -> int:
        """Retorna o número de requisições na janela atual."""
        now = time.monotonic()
        cutoff = now - self._window
        lock = self._get_lock(key)
        with lock:
            q = self._store[key]
            while q and q[0] < cutoff:
                q.popleft()
            return len(q)

    def reset(self, key: str) -> None:
        """Limpa o histórico de uma chave (útil para testes)."""
        lock = self._get_lock(key)
        with lock:
            self._store[key].clear()


# Limitadores globais — configurações distintas por endpoint sensível
_rate_limiter_general = SlidingWindowRateLimiter(max_requests=120, window_secs=60)
_rate_limiter_chat    = SlidingWindowRateLimiter(max_requests=30,  window_secs=60)
_rate_limiter_keys    = SlidingWindowRateLimiter(max_requests=10,  window_secs=60)

# Mapeamento: prefixo de path → limiter específico
_PATH_LIMITERS: List[tuple[str, SlidingWindowRateLimiter]] = [
    ("/api/chat",       _rate_limiter_chat),
    ("/api/config/keys", _rate_limiter_keys),
]


def _get_limiter_for_path(path: str) -> SlidingWindowRateLimiter:
    """Retorna o rate limiter adequado para o path dado."""
    for prefix, limiter in _PATH_LIMITERS:
        if path.startswith(prefix):
            return limiter
    return _rate_limiter_general


# ═══════════════════════════════════════════════════════════════════════════
#  INPUT SANITIZER
# ═══════════════════════════════════════════════════════════════════════════

# Modelos permitidos — whitelist explícita
_ALLOWED_MODELS: frozenset[str] = frozenset({
    # OpenAI
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
    # Anthropic
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
    # Groq
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma-7b-it",
})

# Pattern para session_id válido (alfanumérico + hífens, 8-64 chars)
_SESSION_ID_RE = re.compile(r'^[a-zA-Z0-9_\-]{8,64}$')

# Limites de tamanho
_MAX_MESSAGE_LEN   = 32_000   # ~8k tokens de texto
_MAX_SESSION_LEN   = 64
_MAX_FILENAME_LEN  = 255


class InputSanitizer:
    """Valida e higieniza entradas da API antes do processamento."""

    @staticmethod
    def validate_session_id(session_id: str) -> str:
        """Valida session_id — levanta ValueError se inválido."""
        if not isinstance(session_id, str):
            raise ValueError("session_id deve ser string")
        if len(session_id) > _MAX_SESSION_LEN:
            raise ValueError(f"session_id muito longo (max {_MAX_SESSION_LEN})")
        if not _SESSION_ID_RE.match(session_id):
            raise ValueError("session_id inválido: use apenas letras, números, _ e -")
        return session_id

    @staticmethod
    def validate_message(message: str) -> str:
        """Valida e limpa mensagem do usuário."""
        if not isinstance(message, str):
            raise ValueError("message deve ser string")
        msg = message.strip()
        if not msg:
            raise ValueError("message não pode ser vazio")
        if len(msg) > _MAX_MESSAGE_LEN:
            raise ValueError(f"message muito longa (max {_MAX_MESSAGE_LEN} chars)")
        return msg

    @staticmethod
    def validate_model(model: str) -> str:
        """Valida modelo contra whitelist."""
        if model not in _ALLOWED_MODELS:
            raise ValueError(f"Modelo não permitido: {model!r}")
        return model

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Remove caracteres perigosos de nomes de arquivo."""
        if not isinstance(filename, str):
            raise ValueError("filename deve ser string")
        # Remove path traversal e caracteres especiais
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
        cleaned = cleaned.strip('. ')
        if not cleaned or cleaned in {'.', '..'}:
            raise ValueError("filename inválido")
        if len(cleaned) > _MAX_FILENAME_LEN:
            cleaned = cleaned[:_MAX_FILENAME_LEN]
        return cleaned


# Instância global
sanitizer = InputSanitizer()


# ═══════════════════════════════════════════════════════════════════════════
#  SECURITY HEADERS
# ═══════════════════════════════════════════════════════════════════════════

_SECURITY_HEADERS: Dict[str, str] = {
    # Impede que o browser interprete content-type errado
    "X-Content-Type-Options": "nosniff",
    # Impede clickjacking
    "X-Frame-Options": "DENY",
    # Força HTTPS (mesmo sendo localhost por enquanto)
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    # Restringe o que pode ser carregado na página
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self';"
    ),
    # Remove referrer em cross-origin
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # Impede acesso a features perigosas
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    # Remove identificação do servidor
    "X-Powered-By": "",  # será removido, não adicionado
}


def _apply_security_headers(response: Response) -> None:
    """Aplica headers de segurança na resposta."""
    for header, value in _SECURITY_HEADERS.items():
        if value:  # Não adiciona headers vazios
            response.headers[header] = value
    # Remove headers que identificam o servidor
    for _h in ("server", "x-powered-by"):
        try:
            del response.headers[_h]
        except KeyError:
            pass


# ═══════════════════════════════════════════════════════════════════════════
#  LUNA SECURITY MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════════

class LunaSecurityMiddleware(BaseHTTPMiddleware):
    """
    Middleware ASGI que aplica em cada requisição:
      1. Extração de IP do cliente
      2. Rate limiting (sliding window por IP)
      3. Autenticação via X-Luna-Token (exceto rotas públicas)
      4. Headers de segurança na resposta
      5. Log de auditoria de todas as requisições
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._audit = audit

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.monotonic()
        ip = _get_client_ip(request)
        path = request.url.path
        method = request.method

        # ── 1. Rate limiting ───────────────────────────────────────────────
        limiter = _get_limiter_for_path(path)
        if not limiter.is_allowed(ip):
            self._audit.log_rate_limit(key=ip, path=path)
            log.warning(f"[RateLimit] IP={ip} bloqueado em {path}")
            return self._rate_limit_response(ip)

        # ── 2. Autenticação ────────────────────────────────────────────────
        if path not in _PUBLIC_PATHS and not path.startswith("/docs"):
            auth_error = self._check_auth(request, ip, path)
            if auth_error:
                return auth_error

        # ── 3. Processa requisição ─────────────────────────────────────────
        try:
            response = await call_next(request)
        except Exception as e:
            log.error(f"[Security] Erro interno: {e}")
            duration_ms = (time.monotonic() - start) * 1000
            self._audit.log_request(method, path, ip, 500, duration_ms=duration_ms)
            return JSONResponse(
                {"detail": "Erro interno do servidor"},
                status_code=500,
            )

        # ── 4. Security headers ────────────────────────────────────────────
        _apply_security_headers(response)

        # ── 5. Audit log ───────────────────────────────────────────────────
        duration_ms = (time.monotonic() - start) * 1000
        session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
        self._audit.log_request(method, path, ip, response.status_code, session_id, duration_ms)

        return response

    def _check_auth(self, request: Request, ip: str, path: str) -> Optional[JSONResponse]:
        """
        Verifica o token de autenticação.
        Retorna None se OK, JSONResponse de erro se falhar.
        """
        if LUNA_API_TOKEN is None:
            # Token não configurado — ambiente de desenvolvimento sem Electron
            # Permite requisições mas loga aviso
            log.debug("[Auth] LUNA_API_TOKEN não definido — modo dev sem auth")
            return None

        token = request.headers.get("X-Luna-Token", "")
        if not token:
            self._audit.log_auth_failure(ip, path, "token ausente")
            log.warning(f"[Auth] Token ausente: IP={ip} path={path}")
            return JSONResponse(
                {"detail": "Token de autenticação obrigatório"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not _constant_time_eq(token, LUNA_API_TOKEN):
            self._audit.log_auth_failure(ip, path, "token inválido")
            log.warning(f"[Auth] Token inválido: IP={ip} path={path}")
            # Delay mínimo para dificultar brute-force timing
            time.sleep(0.1)
            return JSONResponse(
                {"detail": "Token inválido"},
                status_code=403,
            )

        return None  # Auth OK

    @staticmethod
    def _rate_limit_response(ip: str) -> JSONResponse:
        return JSONResponse(
            {
                "detail": "Rate limit excedido. Aguarde antes de tentar novamente.",
                "retry_after": 60,
            },
            status_code=429,
            headers={
                "Retry-After": "60",
                "X-RateLimit-Limit": "60",
                "X-RateLimit-Window": "60s",
            },
        )
