<div align="center">

<img src="luna-desktop/assets/icon.png" alt="Luna Agent" width="120" height="120" />

# 🌙 Luna Agent

**Autonomous AI copilot for Web3 developers & ethical hackers**

[![License: MIT](https://img.shields.io/badge/License-MIT-cyan.svg?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-blue?style=for-the-badge&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Solana](https://img.shields.io/badge/Solana-Native-9945FF?style=for-the-badge&logo=solana&logoColor=white)](https://solana.com)
[![Electron](https://img.shields.io/badge/Electron-Desktop-47848F?style=for-the-badge&logo=electron&logoColor=white)](https://electronjs.org)

[![Website](https://img.shields.io/badge/🌐_Website-lunaagent.dev-00d4ff?style=for-the-badge)](https://lunaagent.dev)
[![GitHub Sponsors](https://img.shields.io/badge/❤️_Sponsor-GitHub_Sponsors-EA4AAA?style=for-the-badge)](https://github.com/sponsors/prestes16)
[![Gitcoin](https://img.shields.io/badge/🟢_Fund-Gitcoin_Grants-00433B?style=for-the-badge)](https://gitcoin.co)

> Luna is a local-first, autonomous AI desktop agent that reasons, reads code, executes commands, and audits smart contracts — all running 100% on your machine. Built specifically for Solana developers and Immunefi bug bounty hunters.

</div>

---

## 🎯 Why Luna?

Most AI tools send your code to remote servers. Luna doesn't.

- **100% local** — your private keys, smart contracts, and vulnerability findings never leave your machine
- **Autonomous loop** — up to 40 chained tool calls per task (read → analyze → execute → synthesize)
- **Web3-native** — understands Anchor/Rust, Solana PDAs, SPL tokens, and DeFi attack vectors out of the box
- **Multi-model** — routes each task to the optimal model: Groq (free/fast), Grok-3 (code), Claude Sonnet (security), Claude Opus (deep analysis)
- **Pay-as-you-go** — Solana-based credit system (Grains), no subscriptions, no lock-in

---

## ✨ Features

| Feature | Description |
|---|---|
| 🧠 **Agent Loop** | ReAct-style reasoning: plan → tool call → observe → synthesize |
| 🔍 **Code Intelligence** | Reads files, searches patterns, maps project trees, detects tech stacks |
| 🛡️ **Security Audit** | Finds vulnerabilities in Solana programs, EVM contracts, and web APIs |
| ⚡ **Command Execution** | Runs `cargo build`, `anchor test`, `npm`, `git` — with live output |
| 🔀 **Multi-model Router** | Auto-selects best model per task type with cost optimization |
| 💳 **Solana Payments** | Native USDC payment via Solana Pay QR — 1 USDC = 1,000 Grains |
| 🧬 **Episodic Memory** | Remembers past sessions, workspaces, and findings |
| 📡 **Live Tool Panel** | See every tool call as it happens — full transparency |
| 🔐 **Security Layer** | Local bearer token, rate limiting, secret redaction, audit log |
| 🌐 **Zero-Cloud Mode** | Works fully offline with Ollama — no API keys needed |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Electron (React + TS)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │   Chat UI    │  │ Live Tools   │  │  Workspace    │  │
│  │  + History   │  │   Panel      │  │  Selector     │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
└─────────────────────── IPC / HTTP ──────────────────────┘
                         localhost:8000
┌─────────────────────────────────────────────────────────┐
│                  FastAPI (Python 3.11)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ Agent Loop   │  │  LLM Router  │  │   Security    │  │
│  │ (40 ops max) │  │ Multi-model  │  │  Middleware   │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Filesystem  │  │   Episodic   │  │   Payments    │  │
│  │    Tools     │  │    Memory    │  │  (Solana Pay) │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   Anthropic API      OpenAI API         Groq / xAI
   (Claude Sonnet)   (GPT-4o)           (Llama / Grok)
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+** — [python.org](https://python.org)
- **Node.js 18+** — [nodejs.org](https://nodejs.org)
- At least one API key (see `.env.example`)

### Windows (recommended)

```bash
# 1. Clone the repo
git clone https://github.com/prestes16/luna-agent.git
cd luna-agent

# 2. Copy and configure environment
cp .env.example .env
# Edit .env — add your API keys

# 3. Launch Luna
start-luna.bat
```

That's it. The script creates the virtualenv, installs dependencies, and opens both backend and Electron frontend automatically.

### Manual / Linux / macOS

```bash
# Backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add your keys
uvicorn app.main:app --host 127.0.0.1 --port 8000

# Frontend (new terminal)
cd luna-desktop
npm install && npm run dev
```

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and configure:

```env
# Primary LLM (pick one or more)
ANTHROPIC_API_KEY=sk-ant-...      # Claude Sonnet/Opus — best for security audit
OPENAI_API_KEY=sk-...             # GPT-4o
GROK_API_KEY=...                  # Grok-3 — fast code analysis
GROQ_API_KEY=...                  # Llama 3 — free tier

# Solana payments (optional)
SOLANA_RPC_URL=https://mainnet.helius-rpc.com/?api-key=...
LUNA_WALLET_ADDRESS=...           # Your USDC receiving wallet

# Model selection
LUNA_MODEL=claude-sonnet-4-5      # default model
```

> **Zero API keys?** Set `OLLAMA_URL=http://localhost:11434` and run `ollama pull llama3.1` — Luna works fully offline.

---

## 🎯 Use Cases

### Bug Bounty (Immunefi)
```
"Audit this Solana program for authority check vulnerabilities 
 and reentrancy patterns — focus on the vault instructions"
```
Luna reads all `.rs` files, traces account validation logic, checks PDAs, and outputs a structured vulnerability report.

### Smart Contract Development
```
"Build an Anchor escrow program with timelock and dispute resolution"
```
Luna scaffolds the full program, writes tests, runs `anchor build` and `anchor test`, auto-fixes compiler errors.

### Web3 Security Research
```
"Find all publicly known attack vectors for this DeFi protocol's liquidity pool"
```
Luna cross-references the codebase against known vulnerability patterns and generates an Immunefi-ready report.

---

## 💰 Credit System (Grains)

Luna uses a transparent, on-chain credit system:

| Tier | Price | Grains | Per-grain cost |
|------|-------|--------|----------------|
| Starter | $29 | 30,000 | ~$0.00097 |
| Builder | $79 | 95,000 | ~$0.00083 |
| Pro Hunter | $199 | 270,000 | ~$0.00074 |
| Elite | $499 | 750,000 | ~$0.00067 |

**1 USDC = 1,000 Grains.** Pay via Solana Pay QR — transaction confirmed on-chain, credits added instantly.

---

## 🛣️ Roadmap

- [x] Electron desktop app (React + TypeScript)
- [x] FastAPI backend with autonomous agent loop
- [x] Multi-model LLM router (Claude, GPT-4, Grok, Groq)
- [x] Solana Pay integration + Grains credit system
- [x] Episodic memory + session history
- [x] Security hardening layer (auth, rate limit, audit log)
- [x] Zero-cloud mode (Ollama)
- [ ] **Luna's Computer** — live screen capture + visual reasoning
- [ ] **Immunefi MCP** — direct bounty submission from Luna
- [ ] **Anchor LSP integration** — inline security hints in editor
- [ ] **Multi-agent mode** — parallel analysis across multiple contracts
- [ ] **Mobile companion** — iOS/Android dashboard
- [ ] **Plugin marketplace** — community security audit packs

---

## 🤝 Contributing

Contributions are welcome! Luna is built for the Web3 security community.

1. Fork the repo
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Commit your changes (`git commit -m 'feat: add X'`)
4. Push and open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## ❤️ Sponsorship & Funding

Luna is an open-source project built by a solo Web3 developer actively hunting bug bounties on Immunefi. Your support directly funds development time, API costs, and new security features.

### Why sponsor?

- Help build the best open-source tool for Solana security researchers
- Get your logo/name in the README and on [lunaagent.dev](https://lunaagent.dev)
- Influence the roadmap — sponsors vote on features
- Early access to Luna Pro features before public release

### Ways to support

| Platform | Link | Notes |
|----------|------|-------|
| ⭐ **GitHub Sponsors** | [github.com/sponsors/prestes16](https://github.com/sponsors/prestes16) | Recurring or one-time, zero fees |
| 🟢 **Gitcoin Grants** | [gitcoin.co](https://gitcoin.co) | Quadratic funding — small donations get matched |
| 🏛️ **Open Collective** | [opencollective.com](https://opencollective.com) | Full financial transparency |
| ◎ **Solana** | `Send USDC to lunaagent.dev` | Direct wallet, instant settlement |

> Every contribution — no matter the size — directly funds bug bounty research tools that benefit the entire Web3 ecosystem.

---

## 📄 License

[MIT](LICENSE) — free to use, modify, and distribute.

---

<div align="center">

Built with 🌙 by [@prestes16](https://github.com/prestes16) · [lunaagent.dev](https://lunaagent.dev)

*"The best security tool is the one that runs on your machine."*

</div>
