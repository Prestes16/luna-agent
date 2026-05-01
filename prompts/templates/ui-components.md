# Template: UI Components & Design System (shadcn + Tailwind + Motion)

Use ao construir UI polida, landing pages, dashboards ou quando o usuario quer "bonito", "moderno", "animado".

## Stack visual 2025
- shadcn/ui como base de componentes (copiaveis, editaveis)
- Tailwind CSS com tokens de design-tokens.md
- framer-motion (motion) para animacoes suaves
- lucide-react para icones (stroke-width 1.5-2)
- sonner para toasts
- vaul para drawers mobile
- cmdk para command palette
- tailwind-merge + clsx via `cn()` helper

## Setup rapido
```bash
npx shadcn@latest init -d
npx shadcn@latest add button card input dialog dropdown-menu sheet sonner form label select tabs badge avatar separator tooltip command
npm i framer-motion
```

## Padroes de polish (nao negociaveis)
- Hover sempre com `transition-all duration-200 ease-out`
- Estados focus com ring-2 ring-cyber-cyan/40 ring-offset-2 ring-offset-cyber-bg
- Skeleton loaders, NUNCA spinners simples sem contexto
- Empty states com ilustracao ou icone + mensagem explicativa + CTA
- Error states com icone AlertCircle + mensagem humana + acao de recovery
- Cards elevados: border + subtle shadow + hover lift (translate -translate-y-0.5)
- Botoes primarios com glow sutil em hover: `hover:shadow-[0_0_24px_rgba(0,212,255,0.25)]`

## Animacoes padrao (framer-motion)
```tsx
import { motion } from "framer-motion"
const fadeInUp = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.3, ease: "easeOut" },
}
<motion.div {...fadeInUp}>...</motion.div>
```

## Layout principles
- Max-width containers: `max-w-7xl mx-auto px-6`
- Grid responsive: `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6`
- Spacing vertical: `space-y-8` entre secoes, `space-y-4` dentro de cards
- Tipografia hierarquica: h1 text-4xl font-bold tracking-tight, h2 text-2xl, body text-sm leading-relaxed

## Anti-padroes (PROIBIDO)
- Nunca usar cores primarias Tailwind padrao sem ajustar (blue-500, purple-500 genericos)
- Nunca deixar bordas cinza padrao (#ccc) — sempre cyan translucido
- Nunca usar fontes do sistema sem especificar — sempre Inter ou similar
- Nunca fazer UI sem dark mode — nosso padrao E dark
- Nunca esquecer estados loading/empty/error