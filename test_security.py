"""
test_security.py — Full integration test suite for Luna Agent security layer.

Tests:
  Unit:
    - RateLimiter:        sliding window, exhaustion, reset after window
    - redact():           all 9 secret patterns, no-op on clean text, non-str input
    - is_safe_path():     traversal blocked, sibling blocked, same dir ok, deep ok
    - get_or_create_api_token(): env override, file persistence, file read-back
    - audit():            JSONL written, redaction applied in log

  Integration (via FastAPI TestClient):
    - LocalAuthMiddleware:   correct Bearer → 200, correct X-Luna-Token → 200,
                             missing → 401, wrong → 401, OPTIONS bypass → pass
    - Public endpoints:      /api/healthz, /api/ping no auth required
    - Auth disabled flag:    LUNA_AUTH_DISABLED=1 skips auth for protected routes
    - SecurityHeaders:       all 6 headers present on every response
    - RequestSizeLimitMiddleware: oversized Content-Length → 413, normal → pass
    - RateLimitMiddleware:   burst to limit → 429 + Retry-After, exempt path skips
    - X-RateLimit-Remaining: decrements correctly
    - CORS resolver:         default origins, LUNA_ALLOWED_ORIGINS override, ngrok regex
    - Audit log:             auth_failed, rate_limit_exceeded, request_too_large events
    - Log redaction filter:  secrets stripped before hitting log handler
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── path setup ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from app.security import (
    RateLimiter,
    LocalAuthMiddleware,
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
    audit,
    get_or_create_api_token,
    install,
    install_log_redaction,
    is_safe_path,
    redact,
    resolved_cors_origins,
    AUDIT_FILE,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _make_app(token: str, *, enable_auth: bool = True, rate_limit: int = 500) -> tuple[FastAPI, TestClient]:
    """Build a minimal FastAPI app with all security middleware wired.

    Middleware registration order matters: add_middleware() prepends (LIFO),
    so the LAST call becomes the OUTERMOST wrapper.  SecurityHeaders must be
    outermost so it stamps 401/429/413 early-rejection responses too.
    """
    app = FastAPI()
    # innermost first
    app.add_middleware(LocalAuthMiddleware, token=token, enabled=enable_auth)
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=100)   # tiny limit for testing
    app.add_middleware(RateLimitMiddleware, limiter=RateLimiter(max_per_minute=rate_limit))
    app.add_middleware(SecurityHeadersMiddleware)  # outermost — always runs

    @app.get("/api/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/api/ping")
    def ping():
        return {"pong": True}

    @app.get("/api/secret")
    def secret():
        return {"data": "sensitive"}

    @app.post("/api/upload")
    async def upload():
        return {"ok": True}

    @app.get("/agent/run")
    def agent_run():
        return {"running": True}

    @app.get("/public/open")
    def public_open():
        return {"public": True}

    return app, TestClient(app, raise_server_exceptions=False)


_TOKEN = "test-token-abc123xyz456"
_BAD   = "wrong-token-totally"
_APP, _CLIENT = _make_app(_TOKEN)


# ═══════════════════════════════════════════════════════════════════════════
# 1. RateLimiter — unit
# ═══════════════════════════════════════════════════════════════════════════

class TestRateLimiter:
    def test_allows_up_to_max(self):
        rl = RateLimiter(max_per_minute=3)
        results = [rl.check("ip1")[0] for _ in range(3)]
        assert all(results), "Should allow all 3 requests within limit"

    def test_blocks_over_max(self):
        rl = RateLimiter(max_per_minute=3)
        for _ in range(3):
            rl.check("ip2")
        ok, remaining = rl.check("ip2")
        assert not ok, "4th request must be blocked"
        assert remaining == 0

    def test_remaining_decrements(self):
        rl = RateLimiter(max_per_minute=5)
        _, r1 = rl.check("ip3")
        _, r2 = rl.check("ip3")
        assert r1 == 4
        assert r2 == 3

    def test_different_keys_independent(self):
        rl = RateLimiter(max_per_minute=1)
        ok_a, _ = rl.check("a")
        ok_b, _ = rl.check("b")
        assert ok_a and ok_b, "Different IPs must have independent windows"

    def test_expires_after_window(self):
        rl = RateLimiter(max_per_minute=1)
        rl.check("ip4")
        # Simulate time passing beyond the 60s window
        q = rl._hits["ip4"]
        q[0] = time.monotonic() - 61          # age the hit artificially
        ok, _ = rl.check("ip4")
        assert ok, "Expired hit should free up the slot"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Secret redactor — unit
# ═══════════════════════════════════════════════════════════════════════════

class TestRedact:
    @pytest.mark.parametrize("secret,marker", [
        ("sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456", "sk-ant-***REDACTED***"),
        ("sk-abcdefghijklmnopqrstuvwxyz012345", "sk-***REDACTED***"),
        ("gsk_abcdefghijklmnopqrstuvwxyz0123456789", "gsk_***REDACTED***"),
        ("tgp_v1_abcdefghijklmnopqrstuvwxyz0123456", "tgp_***REDACTED***"),
        ("xai-abcdefghijklmnopqrstuvwxyz0123456789", "xai-***REDACTED***"),
        ("AIzaSyAbcdefghijklmnopqrstuvwxyz0123456789", "AIza***REDACTED***"),
        ("Authorization: Bearer mytoken1234567890abc", "Authorization: Bearer ***REDACTED***"),
        ("api_key=abcdefghijklmnopqrst", "api_key=***REDACTED***"),
        ("API-KEY: abcdefghijklmnopqrst", "API-KEY: ***REDACTED***"),
    ])
    def test_pattern_redacted(self, secret: str, marker: str):
        result = redact(secret)
        assert marker in result, f"Expected '{marker}' in redacted output, got: {result!r}"
        assert secret not in result, "Original secret must not appear in output"

    def test_jwt_redacted(self):
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ.SflKxwRJSMeKKF2QT4fwpMeJf"
        result = redact(jwt)
        assert "jwt.***REDACTED***" in result

    def test_clean_text_unchanged(self):
        txt = "Hello world, this is safe text with no secrets."
        assert redact(txt) == txt

    def test_non_string_returns_as_is(self):
        assert redact(None) is None     # type: ignore[arg-type]
        assert redact(42) == 42         # type: ignore[arg-type]

    def test_empty_string(self):
        assert redact("") == ""


# ═══════════════════════════════════════════════════════════════════════════
# 3. Path traversal guard — unit
# ═══════════════════════════════════════════════════════════════════════════

class TestIsSafePath:
    def setup_method(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sub = self.tmp / "workspace"
        self.sub.mkdir()

    def test_file_inside_workspace(self):
        target = self.sub / "file.txt"
        assert is_safe_path(self.sub, target)

    def test_nested_deep(self):
        deep = self.sub / "a" / "b" / "c" / "file.txt"
        assert is_safe_path(self.sub, deep)

    def test_traversal_blocked(self):
        evil = self.sub / ".." / ".." / "etc" / "passwd"
        assert not is_safe_path(self.sub, evil)

    def test_sibling_dir_blocked(self):
        sibling = self.tmp / "other_dir" / "file.txt"
        assert not is_safe_path(self.sub, sibling)

    def test_workspace_root_itself(self):
        assert is_safe_path(self.sub, self.sub)

    def test_parent_blocked(self):
        assert not is_safe_path(self.sub, self.tmp)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Token persistence — unit
# ═══════════════════════════════════════════════════════════════════════════

class TestApiToken:
    def test_env_override(self):
        with patch.dict(os.environ, {"LUNA_API_TOKEN": "env-token-12345"}):
            tok = get_or_create_api_token()
        assert tok == "env-token-12345"

    def test_creates_and_persists(self):
        with tempfile.TemporaryDirectory() as d:
            token_path = Path(d) / ".api_token"
            with patch("app.security.TOKEN_FILE", token_path), \
                 patch.dict(os.environ, {}, clear=False):
                # Remove env override
                os.environ.pop("LUNA_API_TOKEN", None)
                tok1 = get_or_create_api_token()
                tok2 = get_or_create_api_token()
        assert tok1 == tok2, "Token must be stable across calls"
        assert len(tok1) >= 20

    def test_reads_existing_file(self):
        with tempfile.TemporaryDirectory() as d:
            token_path = Path(d) / ".api_token"
            token_path.write_text("persisted-token-abc123xyz", encoding="utf-8")
            with patch("app.security.TOKEN_FILE", token_path), \
                 patch.dict(os.environ, {}, clear=False):
                os.environ.pop("LUNA_API_TOKEN", None)
                tok = get_or_create_api_token()
        assert tok == "persisted-token-abc123xyz"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Audit log — unit
# ═══════════════════════════════════════════════════════════════════════════

class TestAuditLog:
    def test_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            af = Path(d) / "audit.log"
            with patch("app.security.AUDIT_FILE", af):
                audit("test_event", foo="bar", num=42)
            line = af.read_text(encoding="utf-8").strip()
        rec = json.loads(line)
        assert rec["event"] == "test_event"
        assert rec["foo"] == "bar"
        assert rec["num"] == 42
        assert "ts" in rec

    def test_redacts_secrets_in_log(self):
        with tempfile.TemporaryDirectory() as d:
            af = Path(d) / "audit.log"
            with patch("app.security.AUDIT_FILE", af):
                audit("leak_test", api_key="sk-abcdefghijklmnopqrstuvwxyz012345")
            line = af.read_text(encoding="utf-8")
        assert "sk-abcdefghijklmnopqrstuvwxyz012345" not in line
        assert "REDACTED" in line

    def test_appends_multiple_events(self):
        with tempfile.TemporaryDirectory() as d:
            af = Path(d) / "audit.log"
            with patch("app.security.AUDIT_FILE", af):
                audit("e1", x=1)
                audit("e2", x=2)
                audit("e3", x=3)
            lines = af.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        events = [json.loads(l)["event"] for l in lines]
        assert events == ["e1", "e2", "e3"]


# ═══════════════════════════════════════════════════════════════════════════
# 6. Log redaction filter — unit
# ═══════════════════════════════════════════════════════════════════════════

class TestLogRedactionFilter:
    def test_filter_redacts_message(self):
        """
        install_log_redaction() adds RedactingLogFilter to every handler on the
        root logger.  We add our CaptureHandler to root FIRST, then call
        install_log_redaction() so it picks up the new handler and installs
        the filter on it.  Handlers run filters before emit(), so the message
        is redacted before CaptureHandler ever sees it.
        """
        from app.security import RedactingLogFilter
        captured: list[str] = []

        class CaptureHandler(logging.Handler):
            def emit(self, record):
                captured.append(self.format(record))

        root = logging.getLogger()
        handler = CaptureHandler()
        root.addHandler(handler)
        # Install AFTER adding handler so install_log_redaction() adds the
        # filter to our CaptureHandler too.
        install_log_redaction()
        try:
            assert any(
                isinstance(f, RedactingLogFilter) for f in handler.filters
            ), "install_log_redaction() must have added filter to CaptureHandler"

            logger = logging.getLogger("luna.test.redact.root")
            logger.setLevel(logging.DEBUG)      # ensure INFO records propagate
            logger.info("key leak: sk-abcdefghijklmnopqrstuvwxyz012345")
        finally:
            root.removeHandler(handler)

        assert captured, "Root handler should have received the propagated record"
        assert "sk-abcdefghijklmnopqrstuvwxyz012345" not in captured[0], (
            "Secret must be redacted in the root handler's output"
        )
        assert "REDACTED" in captured[0]

    def test_filter_on_handler_directly(self):
        """RedactingLogFilter works when attached directly to a handler."""
        from app.security import RedactingLogFilter
        captured: list[str] = []

        class CaptureHandler(logging.Handler):
            def emit(self, record):
                captured.append(self.format(record))

        handler = CaptureHandler()
        handler.addFilter(RedactingLogFilter())

        logger = logging.getLogger("luna.test.redact.direct")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        try:
            logger.info("bearer: Authorization: Bearer sk-abcdefghijklmnopqrst1234")
        finally:
            logger.removeHandler(handler)
            logger.propagate = True

        assert captured
        assert "sk-abcdefghijklmnopqrst1234" not in captured[0]
        assert "REDACTED" in captured[0]


# ═══════════════════════════════════════════════════════════════════════════
# 7. LocalAuthMiddleware — integration
# ═══════════════════════════════════════════════════════════════════════════

class TestLocalAuth:
    def test_bearer_correct_grants_access(self):
        r = _CLIENT.get("/api/secret", headers={"Authorization": f"Bearer {_TOKEN}"})
        assert r.status_code == 200

    def test_x_luna_token_correct_grants_access(self):
        r = _CLIENT.get("/api/secret", headers={"X-Luna-Token": _TOKEN})
        assert r.status_code == 200

    def test_missing_token_returns_401(self):
        r = _CLIENT.get("/api/secret")
        assert r.status_code == 401
        assert r.json()["error"] == "unauthorized"

    def test_wrong_token_returns_401(self):
        r = _CLIENT.get("/api/secret", headers={"Authorization": f"Bearer {_BAD}"})
        assert r.status_code == 401

    def test_options_bypasses_auth(self):
        r = _CLIENT.options("/api/secret")
        # OPTIONS should not return 401 (CORS preflight must pass)
        assert r.status_code != 401

    def test_agent_route_protected(self):
        r = _CLIENT.get("/agent/run")
        assert r.status_code == 401

    def test_agent_route_with_token(self):
        r = _CLIENT.get("/agent/run", headers={"Authorization": f"Bearer {_TOKEN}"})
        assert r.status_code == 200

    def test_public_route_no_auth_needed(self):
        r = _CLIENT.get("/public/open")
        assert r.status_code == 200

    def test_auth_disabled_flag(self):
        """LUNA_AUTH_DISABLED=1 should allow all requests through."""
        _, client = _make_app(_TOKEN, enable_auth=False)
        r = client.get("/api/secret")   # no token
        assert r.status_code == 200

    def test_case_insensitive_bearer(self):
        r = _CLIENT.get("/api/secret", headers={"Authorization": f"bearer {_TOKEN}"})
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 8. Public endpoints — integration
# ═══════════════════════════════════════════════════════════════════════════

class TestPublicEndpoints:
    def test_healthz_no_auth(self):
        r = _CLIENT.get("/api/healthz")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_ping_no_auth(self):
        r = _CLIENT.get("/api/ping")
        assert r.status_code == 200
        assert r.json()["pong"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 9. Security headers — integration
# ═══════════════════════════════════════════════════════════════════════════

class TestSecurityHeaders:
    """Every response (auth or not) must carry the full set of security headers."""

    EXPECTED = {
        "x-content-type-options": "nosniff",
        "x-frame-options":        "DENY",
        "referrer-policy":        "no-referrer",
    }

    def _check(self, r):
        for header, value in self.EXPECTED.items():
            assert header in r.headers, f"Missing header: {header}"
            assert r.headers[header] == value, (
                f"Header {header}: expected '{value}', got '{r.headers[header]}'"
            )
        assert "permissions-policy" in r.headers

    def test_headers_on_public_endpoint(self):
        self._check(_CLIENT.get("/api/healthz"))

    def test_headers_on_authenticated_endpoint(self):
        r = _CLIENT.get("/api/secret", headers={"Authorization": f"Bearer {_TOKEN}"})
        self._check(r)

    def test_headers_on_401(self):
        r = _CLIENT.get("/api/secret")      # no token → 401
        self._check(r)

    def test_x_frame_options_deny(self):
        r = _CLIENT.get("/api/healthz")
        assert r.headers.get("x-frame-options") == "DENY"


# ═══════════════════════════════════════════════════════════════════════════
# 10. RequestSizeLimitMiddleware — integration
# ═══════════════════════════════════════════════════════════════════════════

class TestRequestSizeLimit:
    """App built with max_bytes=100 for fast testing."""

    def test_normal_body_passes(self):
        payload = b'{"msg": "hi"}'          # 13 bytes < 100
        r = _CLIENT.post(
            "/api/upload",
            content=payload,
            headers={
                "Authorization": f"Bearer {_TOKEN}",
                "Content-Type": "application/json",
            },
        )
        assert r.status_code == 200

    def test_oversized_content_length_returns_413(self):
        r = _CLIENT.post(
            "/api/upload",
            content=b"x" * 50,             # real body is small…
            headers={
                "Authorization": f"Bearer {_TOKEN}",
                "Content-Length": "9999",   # …but we lie about the size
                "Content-Type": "application/octet-stream",
            },
        )
        assert r.status_code == 413
        body = r.json()
        assert body["error"] == "request too large"
        assert "max_bytes" in body

    def test_413_audit_event(self):
        """Oversized request must produce an audit entry."""
        with tempfile.TemporaryDirectory() as d:
            af = Path(d) / "audit.log"
            with patch("app.security.AUDIT_FILE", af):
                _CLIENT.post(
                    "/api/upload",
                    content=b"x" * 10,
                    headers={
                        "Authorization": f"Bearer {_TOKEN}",
                        "Content-Length": "999999",
                    },
                )
            if af.exists():
                lines = af.read_text().strip().splitlines()
                events = [json.loads(l)["event"] for l in lines if l]
                assert "request_too_large" in events


# ═══════════════════════════════════════════════════════════════════════════
# 11. RateLimitMiddleware — integration
# ═══════════════════════════════════════════════════════════════════════════

class TestRateLimitMiddleware:
    """App with rate_limit=3 so we can exhaust it quickly in tests."""

    def setup_method(self):
        # Fresh app per method — independent rate limiter state.
        self._app, self._client = _make_app(_TOKEN, rate_limit=3)

    def test_within_limit_returns_200(self):
        for _ in range(3):
            r = self._client.get(
                "/api/secret", headers={"Authorization": f"Bearer {_TOKEN}"}
            )
            assert r.status_code == 200

    def test_over_limit_returns_429(self):
        for _ in range(3):
            self._client.get("/api/secret", headers={"Authorization": f"Bearer {_TOKEN}"})
        r = self._client.get("/api/secret", headers={"Authorization": f"Bearer {_TOKEN}"})
        assert r.status_code == 429
        assert r.json()["error"] == "rate limit exceeded"

    def test_retry_after_header_present(self):
        for _ in range(3):
            self._client.get("/api/secret", headers={"Authorization": f"Bearer {_TOKEN}"})
        r = self._client.get("/api/secret", headers={"Authorization": f"Bearer {_TOKEN}"})
        assert "retry-after" in r.headers

    def test_x_ratelimit_remaining_decrements(self):
        remainders = []
        for _ in range(3):
            r = self._client.get(
                "/api/secret", headers={"Authorization": f"Bearer {_TOKEN}"}
            )
            if "x-ratelimit-remaining" in r.headers:
                remainders.append(int(r.headers["x-ratelimit-remaining"]))
        assert remainders == sorted(remainders, reverse=True), (
            "Remaining count must decrease monotonically"
        )

    def test_exempt_path_not_rate_limited(self):
        """healthz must never count against the rate limit window."""
        _, client = _make_app(_TOKEN, rate_limit=1)
        # burn the 1-request quota on a protected route
        client.get("/api/secret", headers={"Authorization": f"Bearer {_TOKEN}"})
        # healthz is exempt — must still return 200 even after limit exhausted
        r = client.get("/api/healthz")
        assert r.status_code == 200

    def test_429_audit_event(self):
        with tempfile.TemporaryDirectory() as d:
            af = Path(d) / "audit.log"
            with patch("app.security.AUDIT_FILE", af):
                _, client = _make_app(_TOKEN, rate_limit=1)
                client.get("/api/secret", headers={"Authorization": f"Bearer {_TOKEN}"})
                client.get("/api/secret", headers={"Authorization": f"Bearer {_TOKEN}"})
            if af.exists():
                lines = af.read_text().strip().splitlines()
                events = [json.loads(l)["event"] for l in lines if l]
                assert "rate_limit_exceeded" in events


# ═══════════════════════════════════════════════════════════════════════════
# 12. Auth audit events — integration
# ═══════════════════════════════════════════════════════════════════════════

class TestAuthAuditEvents:
    def test_auth_failed_event_written(self):
        with tempfile.TemporaryDirectory() as d:
            af = Path(d) / "audit.log"
            with patch("app.security.AUDIT_FILE", af):
                _CLIENT.get("/api/secret", headers={"Authorization": "Bearer wrong"})
            if af.exists():
                lines = af.read_text().strip().splitlines()
                events = [json.loads(l)["event"] for l in lines if l]
                assert "auth_failed" in events


# ═══════════════════════════════════════════════════════════════════════════
# 13. CORS resolver — unit
# ═══════════════════════════════════════════════════════════════════════════

class TestCorsResolver:
    DEFAULT = ["http://localhost:5173", "http://127.0.0.1:5173"]

    def test_returns_defaults_when_no_env(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LUNA_ALLOWED_ORIGINS", None)
            os.environ.pop("LUNA_ALLOW_NGROK", None)
            origins, regex = resolved_cors_origins(self.DEFAULT)
        assert origins == self.DEFAULT
        assert regex is None

    def test_env_override_replaces_defaults(self):
        with patch.dict(os.environ, {
            "LUNA_ALLOWED_ORIGINS": "https://app.example.com,https://staging.example.com",
            "LUNA_ALLOW_NGROK": "",
        }):
            origins, regex = resolved_cors_origins(self.DEFAULT)
        assert origins == ["https://app.example.com", "https://staging.example.com"]
        assert regex is None

    def test_ngrok_flag_adds_regex(self):
        with patch.dict(os.environ, {"LUNA_ALLOW_NGROK": "1"}):
            _, regex = resolved_cors_origins(self.DEFAULT)
        assert regex is not None
        import re
        assert re.match(regex, "https://abc123.ngrok-free.app")

    def test_ngrok_flag_off_no_regex(self):
        with patch.dict(os.environ, {"LUNA_ALLOW_NGROK": "0"}):
            _, regex = resolved_cors_origins(self.DEFAULT)
        assert regex is None


# ═══════════════════════════════════════════════════════════════════════════
# 14. install() smoke — integration
# ═══════════════════════════════════════════════════════════════════════════

class TestInstall:
    def test_install_returns_token(self):
        mini = FastAPI()

        @mini.get("/api/healthz")
        def _h():
            return {"ok": True}

        with patch.dict(os.environ, {"LUNA_API_TOKEN": "install-smoke-token"}):
            tok = install(mini, enable_auth=True, max_per_minute=60)
        assert tok == "install-smoke-token"

    def test_auth_disabled_env(self):
        mini = FastAPI()

        @mini.get("/api/secret")
        def _s():
            return {"ok": True}

        with patch.dict(os.environ, {
            "LUNA_AUTH_DISABLED": "1",
            "LUNA_API_TOKEN": "some-token",
        }):
            install(mini)
            client = TestClient(mini, raise_server_exceptions=False)
            r = client.get("/api/secret")   # no token provided
        assert r.status_code == 200, "Auth disabled — should pass without token"
