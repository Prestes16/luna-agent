"""Luna Agent - Security hardening layer.

Stdlib-only. Provides local bearer token, rate limit, secret redaction,
security headers, request size limit, path traversal guard, audit log.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import time
from collections import deque
from pathlib import Path
from typing import Iterable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

_log = logging.getLogger("luna.security")

LUNA_HOME = Path.home() / ".luna-agent"
LUNA_HOME.mkdir(parents=True, exist_ok=True)
TOKEN_FILE = LUNA_HOME / ".api_token"
AUDIT_FILE = LUNA_HOME / "audit.log"


# ----- Local API token --------------------------------------------------------
def get_or_create_api_token() -> str:
    env_tok = (os.getenv("LUNA_API_TOKEN") or "").strip()
    if env_tok:
        return env_tok
    try:
        if TOKEN_FILE.exists():
            val = TOKEN_FILE.read_text(encoding="utf-8").strip()
            if val:
                return val
    except OSError:
        pass
    tok = secrets.token_urlsafe(32)
    try:
        TOKEN_FILE.write_text(tok, encoding="utf-8")
        try:
            os.chmod(TOKEN_FILE, 0o600)
        except OSError:
            pass
    except OSError as e:
        _log.warning("could not persist API token: %s", e)
    return tok


# ----- Secret redactor --------------------------------------------------------
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "sk-ant-***REDACTED***"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "sk-***REDACTED***"),
    (re.compile(r"gsk_[A-Za-z0-9]{20,}"), "gsk_***REDACTED***"),
    (re.compile(r"tgp_v[0-9]_[A-Za-z0-9_\-]{20,}"), "tgp_***REDACTED***"),
    (re.compile(r"xai-[A-Za-z0-9]{20,}"), "xai-***REDACTED***"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), "AIza***REDACTED***"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}"),
     "jwt.***REDACTED***"),
    (re.compile(r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9_\-\.]{10,}"),
     r"\1***REDACTED***"),
    (re.compile(r"(?i)(api[_\-]?key\s*[:=]\s*)[\"']?[A-Za-z0-9_\-]{16,}[\"']?"),
     r"\1***REDACTED***"),
]


def redact(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    for pat, repl in _SECRET_PATTERNS:
        text = pat.sub(repl, text)
    return text


class RedactingLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(str(record.msg))
            if record.args:
                record.args = tuple(
                    redact(a) if isinstance(a, str) else a for a in record.args
                )
        except Exception:
            pass
        return True


def install_log_redaction() -> None:
    root = logging.getLogger()
    flt = RedactingLogFilter()
    if not any(isinstance(f, RedactingLogFilter) for f in root.filters):
        root.addFilter(flt)
    for h in root.handlers:
        if not any(isinstance(f, RedactingLogFilter) for f in h.filters):
            h.addFilter(RedactingLogFilter())


# ----- Path traversal guard ---------------------------------------------------
def is_safe_path(base: str | Path, target: str | Path) -> bool:
    try:
        base_r = Path(base).resolve()
        target_r = Path(target).resolve()
        return str(target_r).startswith(str(base_r))
    except (OSError, ValueError):
        return False


# ----- Audit log --------------------------------------------------------------
def audit(event: str, **fields) -> None:
    try:
        rec = {"ts": time.time(), "event": event, **fields}
        with AUDIT_FILE.open("a", encoding="utf-8") as f:
            f.write(redact(json.dumps(rec, ensure_ascii=False)) + "\n")
    except Exception:
        pass


# ----- Rate limiter -----------------------------------------------------------
class RateLimiter:
    def __init__(self, max_per_minute: int = 120):
        self.window = 60.0
        self.max = max_per_minute
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        q = self._hits.setdefault(key, deque())
        while q and (now - q[0]) > self.window:
            q.popleft()
        if len(q) >= self.max:
            return False, 0
        q.append(now)
        return True, max(0, self.max - len(q))


# ----- Middlewares ------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        resp: Response = await call_next(request)
        h = resp.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Permissions-Policy",
                     "geolocation=(), microphone=(), camera=(), payment=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Cross-Origin-Resource-Policy", "same-site")
        return resp


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, max_bytes: int = 20 * 1024 * 1024):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > self.max_bytes:
            audit("request_too_large",
                  path=str(request.url.path),
                  size=int(cl),
                  ip=(request.client.host if request.client else None))
            return JSONResponse(
                {"error": "request too large", "max_bytes": self.max_bytes},
                status_code=413,
            )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    EXEMPT_PREFIXES = ("/static", "/healthz", "/favicon", "/api/healthz")

    def __init__(self, app: ASGIApp, limiter: RateLimiter | None = None):
        super().__init__(app)
        self.limiter = limiter or RateLimiter()

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in self.EXEMPT_PREFIXES):
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        ok, remaining = self.limiter.check(ip)
        if not ok:
            audit("rate_limit_exceeded", ip=ip, path=path)
            return JSONResponse(
                {"error": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        resp = await call_next(request)
        resp.headers["X-RateLimit-Remaining"] = str(remaining)
        return resp


class LocalAuthMiddleware(BaseHTTPMiddleware):
    PROTECTED_PREFIXES = ("/api/", "/agent/", "/chat")
    PUBLIC_PATHS = {"/api/healthz", "/api/ping", "/api/version"}
    PUBLIC_PREFIXES = ("/payment/webhook", "/static/")

    def __init__(self, app: ASGIApp, token: str, enabled: bool = True):
        super().__init__(app)
        self.token = token
        self.enabled = enabled

    def _is_protected(self, path: str) -> bool:
        if not self.enabled:
            return False
        if path in self.PUBLIC_PATHS:
            return False
        if any(path.startswith(p) for p in self.PUBLIC_PREFIXES):
            return False
        return any(path.startswith(p) for p in self.PROTECTED_PREFIXES)

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path
        if not self._is_protected(path):
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            provided = auth[7:].strip()
        else:
            provided = request.headers.get("x-luna-token", "").strip()
        if not provided or not secrets.compare_digest(provided, self.token):
            audit("auth_failed", path=path,
                  ip=(request.client.host if request.client else None))
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


# ----- Installer --------------------------------------------------------------
def install(app,
            *,
            enable_auth: bool | None = None,
            max_per_minute: int = 240,
            max_body_bytes: int = 20 * 1024 * 1024) -> str:
    token = get_or_create_api_token()

    if enable_auth is None:
        enable_auth = os.getenv("LUNA_AUTH_DISABLED", "").strip() not in ("1", "true", "yes")

    try:
        max_per_minute = int(os.getenv("LUNA_RATE_LIMIT_PER_MIN", str(max_per_minute)))
    except ValueError:
        pass
    try:
        mb = int(os.getenv("LUNA_MAX_BODY_MB", "0"))
        if mb > 0:
            max_body_bytes = mb * 1024 * 1024
    except ValueError:
        pass

    # Middleware order: add_middleware() prepends (LIFO), so the LAST added
    # becomes the OUTERMOST wrapper — it runs first on requests and last on
    # responses.  SecurityHeaders must be outermost so it stamps every
    # response, including early-rejection 401 / 429 / 413 responses.
    if enable_auth:
        app.add_middleware(LocalAuthMiddleware, token=token, enabled=True)
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=max_body_bytes)
    if max_per_minute > 0:
        app.add_middleware(RateLimitMiddleware,
                           limiter=RateLimiter(max_per_minute=max_per_minute))
    app.add_middleware(SecurityHeadersMiddleware)   # outermost — always runs

    install_log_redaction()
    audit("security_installed",
          auth=enable_auth,
          rate_limit_per_min=max_per_minute,
          max_body_bytes=max_body_bytes)
    _log.info("security layer installed (auth=%s, rl=%s/min, max=%sMB)",
              enable_auth, max_per_minute, max_body_bytes // (1024 * 1024))
    return token


def resolved_cors_origins(default_dev: Iterable[str]) -> tuple[list[str], str | None]:
    raw = (os.getenv("LUNA_ALLOWED_ORIGINS") or "").strip()
    origins = [o.strip() for o in raw.split(",") if o.strip()] if raw else list(default_dev)
    regex = None
    if os.getenv("LUNA_ALLOW_NGROK", "").strip() in ("1", "true", "yes"):
        regex = r"https://.*\.ngrok(-free)?\.app"
    return origins, regex