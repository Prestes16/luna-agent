# Security Architecture

Luna Agent ships a defense-in-depth stack aimed at preventing remote
intrusion, local token theft, secret leakage in logs, abuse of the local
API, and compromise via the Electron renderer.

## 1. Backend hardening (`app/security.py`)

All middlewares are wired by `app.security.install(app)` and activated
from `app/main.py` immediately after `FastAPI()`.

| Layer                         | Purpose                                                   |
| ----------------------------- | --------------------------------------------------------- |
| `LocalAuthMiddleware`         | Bearer token / `X-Luna-Token` on `/api/*`, `/agent/*`, `/chat*`. Uses `secrets.compare_digest` (constant-time). |
| `RateLimitMiddleware`         | Per-IP sliding window (default 240 req/min). Emits `429 + Retry-After`. |
| `RequestSizeLimitMiddleware`  | Rejects payloads over `LUNA_MAX_BODY_MB` (default 20 MB). |
| `SecurityHeadersMiddleware`   | `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `COOP/CORP`. |
| `install_log_redaction()`     | Regex filter strips OpenAI / Anthropic / Groq / Together / xAI / Gemini / JWT tokens and `Authorization: Bearer` headers before anything hits the log handler. |
| `audit()`                     | Append-only JSONL log in `~/.luna-agent/audit.log` for: `security_installed`, `auth_failed`, `rate_limit_exceeded`, `request_too_large`. |
| `is_safe_path(base, target)`  | Resolves both paths and ensures the target stays within the workspace base. Call this before any FS operation driven by user input. |

### Public endpoints (no auth)

- `GET /api/healthz`
- `GET /api/ping`
- `GET /api/version`
- `POST /payment/webhook` (Helius — validates its own HMAC signature)
- `/static/*`

### Configuration (env vars)

```
LUNA_API_TOKEN=           # override auto-generated token
LUNA_AUTH_DISABLED=1      # dev only — disables bearer auth
LUNA_RATE_LIMIT_PER_MIN=  # 0 = disable, default 240
LUNA_MAX_BODY_MB=         # default 20
LUNA_ALLOWED_ORIGINS=     # comma-separated CORS origins
LUNA_ALLOW_NGROK=1        # re-enable ngrok regex in CORS
```

### Token lifecycle

1. Electron generates a random 32-byte hex token at startup
   (`luna-desktop/src/main.ts` → `LUNA_API_TOKEN`).
2. The child Python process inherits it via `env`.
3. `get_or_create_api_token()` returns that env value; otherwise it reads
   or creates `~/.luna-agent/.api_token` (`chmod 600`).
4. Renderer retrieves it through the `auth:getToken` IPC handler and
   sends `X-Luna-Token` on every `fetch()` / SSE call.

Rotate the persisted token by deleting `~/.luna-agent/.api_token` — a
new one is minted on the next start.

## 2. Electron hardening (`luna-desktop/src/main.ts`)

- `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`,
  `webSecurity: true`.
- Content-Security-Policy injected via `onHeadersReceived`. Production
  CSP: `default-src 'self'; script-src 'self'`.
- `web-contents-created` hook:
  - `will-navigate` blocks everything except `localhost`, `127.0.0.1`
    and `file://`.
  - `setWindowOpenHandler` denies new windows and hands external URLs
    to `shell.openExternal`.
  - `setPermissionRequestHandler` grants only `clipboard-read` and
    `clipboard-sanitized-write`; camera, mic, geolocation, notifications,
    MIDI, USB, etc. are denied.
- Deep-link handler (`luna-agent://`) validates the scheme and ignores
  any other argv entries.

## 3. Secret management

- `.env` is gitignored. Use `.env.example` as the canonical template.
- Every renderer log call is eligible for redaction; backend log
  filtering is always on.
- Treasury wallet should move to `LUNA_TREASURY_WALLET` before the first
  public release (currently tracked in the deployment checklist).

## 4. Path traversal

Every tool that takes a user-controlled path must call
`app.security.is_safe_path(workspace_base, requested_path)` before any
read/write. The helper resolves symlinks and rejects anything outside
the workspace root.

## 5. Audit log

`~/.luna-agent/audit.log` is append-only JSONL. Each record includes:

```
{"ts": 1714500000.12, "event": "auth_failed", "path": "/api/agent/stream", "ip": "127.0.0.1"}
```

Use this file to investigate incidents and to feed external SIEMs.

## 6. Reporting a vulnerability

See `SECURITY.md` at the repository root for the disclosure policy.