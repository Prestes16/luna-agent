# Cheatsheet: Comandos de Scaffolding Rapido

Sempre preferir scaffold oficial em vez de criar package.json a mao.

## Electron + React + Vite + TS
```bash
npm create vite@latest meu-app -- --template react-ts
cd meu-app
npm i -D electron electron-builder electron-vite
npm i zustand react-router-dom lucide-react
npm i -D tailwindcss postcss autoprefixer && npx tailwindcss init -p
```

## Next.js 15
```bash
npx create-next-app@latest meu-saas --typescript --tailwind --app --eslint --src-dir=false --import-alias="@/*"
```

## Next.js + shadcn + componentes essenciais
```bash
cd meu-saas
npx shadcn@latest init -d
npx shadcn@latest add button card input dialog form label select sonner dropdown-menu sheet table badge avatar tabs
```

## React SPA puro (Vite)
```bash
npm create vite@latest meu-app -- --template react-ts
cd meu-app && npm i
```

## Node API + TS (tsx dev)
```bash
mkdir meu-api && cd meu-api && npm init -y
npm i -D typescript tsx @types/node
npm i hono zod
npx tsc --init
```

## Python FastAPI
```bash
python -m venv .venv
.\.venv\Scripts\activate   # Windows
pip install fastapi uvicorn[standard] pydantic python-dotenv
```

## Drizzle + Postgres (Neon)
```bash
npm i drizzle-orm postgres
npm i -D drizzle-kit
# criar drizzle.config.ts
npx drizzle-kit push
```

## Better Auth
```bash
npm i better-auth
npx @better-auth/cli generate   # gera schema se usando adapter
```

## Tanstack Query
```bash
npm i @tanstack/react-query
```

## Playwright E2E
```bash
npm init playwright@latest
npx playwright test
```

## Tauri (alternativa Electron, mais leve)
```bash
npm create tauri-app@latest
```

## Prisma (se preferir sobre Drizzle)
```bash
npm i prisma @prisma/client
npx prisma init --datasource-provider postgresql
npx prisma migrate dev --name init
```

## Regras de uso
- SEMPRE rodar o scaffold oficial via run_command
- NUNCA inventar package.json quando existe um scaffold oficial
- Instalar deps imediatamente apos o scaffold
- Validar que `npm run dev` / `uvicorn` / equivalente inicia antes de prosseguir