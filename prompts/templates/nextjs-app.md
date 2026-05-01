# Template: Next.js App (web fullstack)

Use este template quando o usuario pedir "site", "web app", "landing page", "painel web", "SaaS" ou qualquer coisa que rode em navegador com URL publica.

## Stack obrigatoria
- Next.js 14+ (App Router)
- React 18 + TypeScript
- Tailwind CSS
- shadcn/ui para componentes base
- lucide-react para icones
- Zod para validacao de schemas
- Server Actions para mutations quando possivel

## Estrutura esperada (App Router)
```
meu-site/
  package.json
  next.config.mjs
  tailwind.config.ts
  tsconfig.json
  app/
    layout.tsx
    page.tsx
    globals.css
    (routes)/
  components/
    ui/              # shadcn
  lib/
    utils.ts
  public/
```

## Scaffolding rapido
```bash
npx create-next-app@latest meu-site --typescript --tailwind --app --eslint --src-dir=false --import-alias="@/*"
cd meu-site
npx shadcn@latest init -d
npx shadcn@latest add button card input dialog sonner
npm i lucide-react zod
```

## Tema (dark-first, cyber)
- Editar app/globals.css com os tokens de design-tokens.md
- CSS variables no :root e .dark usando HSL para compatibilidade shadcn
- background: 222 47% 8% (equivale a #0a0f1e)
- primary: 189 100% 50% (equivale ao cyan #00d4ff)
- accent: 262 83% 58% (equivale ao purple #7c3aed)

## Regras de entrega
1. Scaffold via create-next-app com as flags acima
2. shadcn init imediato apos o scaffold
3. Ajustar globals.css com tokens cyber ANTES de criar telas
4. Pagina inicial funcional (hero + alguma interacao real), nunca template generico "Welcome to Next.js"
5. npm run dev roda sem erros antes de encerrar
6. Se houver dados dinamicos, usar Server Components por padrao; Client Components somente com interacao