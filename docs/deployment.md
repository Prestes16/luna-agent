# Deployment Guide

## Release prerequisites

### 1. Code signing

**Windows:** EV/OV code signing certificate (~$200-400/year).
Without signing, SmartScreen blocks new installers for weeks.

**macOS:** Apple Developer Program ($99/year) with a Developer ID
Application certificate. Notarization is mandatory since macOS 10.15
(use `notarytool`).

**Linux:** AppImage does not require signing; for `.deb` / `.rpm`
use `dpkg-sig` / `rpm-sign`.

### 2. App icons

Place in `luna-desktop/assets/`:
- `icon.ico` — Windows multi-resolution (16, 32, 48, 64, 128, 256)
- `icon.icns` — macOS (1024 base via `iconutil`)
- `icon.png` — Linux (512+ recommended)
- `icon-tray.png` — system tray (32x32)

### 3. Auto-update

```bash
cd luna-desktop && npm i electron-updater
```

In `package.json > build`:

```json
"publish": {
  "provider": "github",
  "owner": "<user>",
  "repo":  "<repo>"
}
```

GitHub Releases becomes the update feed.

### 4. Environment variables in production

Never commit `.env`. In production:
- **Desktop:** `electron-store` with encryption, or Windows Credential
  Manager / macOS Keychain / libsecret via a native module
- **Self-hosted backend:** systemd `EnvironmentFile=` or Docker secrets
- **Supabase:** rotate service keys quarterly

### 5. Secrets to rotate before public launch

- `HELIUS_API_KEY`
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `TOGETHER_API_KEY` / `GROQ_API_KEY`
- `SUPABASE_URL` / `SUPABASE_SERVICE_KEY`
- `LUNA_TREASURY_WALLET` — generate a new wallet, keep the current one as legacy
- Any OAuth tokens previously committed

### 6. Observability

- **Sentry** (free 5k events/month): wrap Electron `main.ts`, renderer,
  and FastAPI
- **Health check:** expose `GET /healthz` on the backend
- **Structured logs:** `structlog` (Python), `winston` (Node)

### 7. Release checklist

```
[ ] LICENSE, PRIVACY, TERMS, SECURITY, CONTRIBUTING, CHANGELOG present
[ ] .env removed from git history and from local filesystem
[ ] Treasury wallet moved to an env var
[ ] Icons placed in luna-desktop/assets/
[ ] Code signing configured for Windows and macOS
[ ] electron-updater + publish config set
[ ] CI: multi-OS build green
[ ] Tests: pytest + tsc clean
[ ] Sentry DSN configured
[ ] Version bumped in package.json and any Python metadata
[ ] Git tag: v1.0.0-rc1
[ ] Release notes drafted
[ ] Landing page pointing to the release
```