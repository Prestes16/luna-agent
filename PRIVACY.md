# Privacy Policy - Luna Agent

**Last updated:** April 30, 2026

## 1. Who we are

Luna Agent is a local AI assistant developed by Cleiton Luna. This
policy describes how personal data is handled, aligned with the
Brazilian LGPD (Law 13.709/2018) and general privacy best practices.

## 2. Data collected

### 2.1 Locally (on your device)
- Chat history (SQLite in `~/.luna-agent/`)
- Episodic memory and learned lessons
- Registered projects and messages
- Workspace settings and API keys

**This data does NOT leave your computer without an explicit action from you.**

### 2.2 Transmitted to third parties (when you use each feature)
- **LLM providers** (OpenAI / Anthropic / Together / Groq / Gemini / Ollama):
  receive your messages to generate responses. You choose which one.
- **Helius RPC** (Solana): blockchain queries when you use
  solana / defi / launchpad modes.
- **Supabase** (when payments enabled): email + Grains balance.
- **External APIs** (Birdeye, DexScreener, Jupiter): public blockchain
  data, no personal information included.

### 2.3 Telemetry
- By default: **none**.
- If enabled (opt-in in Settings): anonymous usage metrics (skill
  activated, generic errors) without message content.

## 3. Legal basis (LGPD Art. 7)

- **Consent:** by installing and accepting the Terms of Use.
- **Contract execution:** processing Grains payments.
- **Legitimate interest:** improving the product via opt-in telemetry.

## 4. Your rights

You may, at any time:
- **Access** your data: everything lives in `~/.luna-agent/` (readable SQLite).
- **Correct** data: edit directly or through the UI.
- **Delete** data: removing the `~/.luna-agent/` folder wipes all local data.
- **Port** data: export via Settings > Data > Export JSON.
- **Withdraw consent:** uninstall the app.

For data sent to third parties (LLM providers, Supabase), contact each
service directly according to their policies.

## 5. Security

- API keys stored with user-level permissions by the OS.
- All network traffic over HTTPS.
- Source code open and auditable in this repository.

## 6. Minors

The service is not intended for users under 18 years of age.

## 7. Changes

Material changes will be announced in `CHANGELOG.md` and on the next
app launch.

## 8. Contact

For privacy-related requests, open an issue on the official repository
or contact the maintainer via the channel listed in the README.