# Template: Auth Stack (Better Auth)

Use quando o projeto precisar de login, signup, sessao, OAuth, protecao de rotas.

## Por que Better Auth
- TypeScript-first
- Adapters nativos para Drizzle, Prisma, MongoDB
- Plugins: 2FA, magic link, passkey, organization, admin
- Integracao limpa com Next.js App Router

## Setup
```bash
npm i better-auth
```

## Config minima (lib/auth.ts)
```ts
import { betterAuth } from "better-auth"
import { drizzleAdapter } from "better-auth/adapters/drizzle"
import { db } from "@/lib/db"

export const auth = betterAuth({
  database: drizzleAdapter(db, { provider: "pg" }),
  emailAndPassword: { enabled: true },
  socialProviders: {
    github: {
      clientId: process.env.GITHUB_CLIENT_ID!,
      clientSecret: process.env.GITHUB_CLIENT_SECRET!,
    },
  },
})
```

## API route (app/api/auth/[...all]/route.ts)
```ts
import { auth } from "@/lib/auth"
import { toNextJsHandler } from "better-auth/next-js"
export const { GET, POST } = toNextJsHandler(auth)
```

## Client (lib/auth-client.ts)
```ts
import { createAuthClient } from "better-auth/react"
export const authClient = createAuthClient()
export const { signIn, signUp, signOut, useSession } = authClient
```

## Middleware para rotas protegidas
```ts
// middleware.ts
import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"
export async function middleware(req: NextRequest) {
  const session = req.cookies.get("better-auth.session_token")
  if (!session && req.nextUrl.pathname.startsWith("/dashboard")) {
    return NextResponse.redirect(new URL("/login", req.url))
  }
}
export const config = { matcher: ["/dashboard/:path*"] }
```

## Variaveis de ambiente
```
BETTER_AUTH_SECRET=openssl rand -base64 32
BETTER_AUTH_URL=http://localhost:3000
DATABASE_URL=...
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
```

## Regras
- NUNCA hardcode secret
- Schema da tabela users deve ser migrado pelo drizzle-kit antes do primeiro login
- Testar login + logout + sessao persistida antes de construir features dependentes