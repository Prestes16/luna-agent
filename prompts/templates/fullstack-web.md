# Template: Fullstack Web Moderno (Next.js + tRPC/Server Actions + Drizzle)

Use quando o usuario pedir "saas", "plataforma", "crud completo", "backend + frontend", "API + UI".

## Stack canonica 2025
- Next.js 15 (App Router, Server Components, Server Actions)
- TypeScript strict
- Tailwind CSS + shadcn/ui
- Drizzle ORM + Neon/Postgres (ou SQLite via libsql para dev)
- Better Auth (email/password + OAuth)
- Zod para schemas compartilhados
- TanStack Query apenas quando precisar cache client-side complexo
- tRPC SOMENTE se o projeto ja tem tRPC — caso contrario, Server Actions

## Estrutura recomendada
```
app/
  (marketing)/page.tsx        # landing
  (app)/dashboard/page.tsx    # area autenticada
  api/auth/[...all]/route.ts  # better-auth
  layout.tsx
  globals.css
components/
  ui/                          # shadcn
  forms/
  layout/
lib/
  auth.ts                      # better-auth config
  db/
    index.ts                   # drizzle client
    schema.ts                  # tabelas
  validators/                  # zod schemas
actions/                       # server actions
drizzle.config.ts
```

## Setup em comandos
```bash
npx create-next-app@latest meu-saas --typescript --tailwind --app --eslint --src-dir=false --import-alias="@/*"
cd meu-saas
npx shadcn@latest init -d
npx shadcn@latest add button card input dialog sonner form label select dropdown-menu sheet table badge avatar
npm i drizzle-orm postgres zod better-auth
npm i -D drizzle-kit @types/node
```

## Drizzle bootstrap
```ts
// lib/db/schema.ts
import { pgTable, text, timestamp, uuid } from "drizzle-orm/pg-core"
export const users = pgTable("users", {
  id: uuid("id").primaryKey().defaultRandom(),
  email: text("email").notNull().unique(),
  name: text("name"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
})
```

## Server Action padrao
```ts
"use server"
import { z } from "zod"
import { db } from "@/lib/db"
const schema = z.object({ name: z.string().min(1) })
export async function createThing(input: unknown) {
  const data = schema.parse(input)
  await db.insert(things).values(data)
}
```

## Regras de entrega
1. Sempre iniciar com scaffold oficial
2. shadcn init e componentes base ANTES das paginas
3. Tema cyber aplicado em globals.css usando tokens de design-tokens.md
4. Auth funcional (login/logout real) antes de paginas protegidas
5. Pelo menos UM CRUD end-to-end funcionando com persistencia real
6. npm run dev rodando sem erros no final