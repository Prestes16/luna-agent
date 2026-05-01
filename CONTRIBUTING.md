# Contributing to Luna Agent

Thanks for your interest. Luna combines a Python (FastAPI) backend with
an Electron (React + TypeScript) frontend. This guide helps you set up
the environment and submit contributions.

## Local setup

### Backend (Python 3.11+)
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # fill in your keys
python run.py
```

### Frontend (Node 20+)
```bash
cd luna-desktop
npm install
npm run dev
```

## Project structure

- `app/` — FastAPI backend, agent loop, tools, skills
- `app/tools/` — tools the agent can invoke
- `prompts/` — identity, rules, skills, templates
- `luna-desktop/` — Electron + React app
- `data/` — local SQLite (gitignored)

## Pre-PR checks

```bash
# Python
python -m pytest test_*.py
python -c "import ast; [ast.parse(open(f).read()) for f in ('app/main.py','app/strategy.py')]"

# Frontend
cd luna-desktop
npx tsc --noEmit
```

## Style

- **Python:** PEP 8, type hints where reasonable, no emojis in code
- **TypeScript:** strict mode, avoid `any` without justification
- **Commits:** imperative mood, English or Portuguese, e.g. `add skill X`
- **Do not change** backend SSE event names (`tool_start`, `tool_done`, ...)
- **Do not change** the tool dispatcher without updating tool definitions

## Adding a skill

1. Create a template at `prompts/templates/<skill-name>.md`
2. Add a `## SKILL: <NAME>` block to `prompts/skills.md`
3. Add a row to the routing table in `skills.md`
4. Validate with `build_system_prompt('agent')`

## Adding a tool

1. Create `app/tools/<tool_name>_tool.py` with `get_tool_definitions()`
2. Register in the `app/main.py` dispatcher
3. Add an icon in `luna-desktop/src/components/ExecutionPanel.tsx`
4. Verify backend ↔ UI coherence (all names match)

## Reporting bugs

Open an issue with:
- Version (see `package.json`)
- OS (Windows / macOS / Linux + version)
- Reproduction steps
- Relevant logs (never include API keys)

## Security

Do not open public issues for vulnerabilities. See `SECURITY.md`.