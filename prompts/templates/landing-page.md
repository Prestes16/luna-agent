# Template: Landing Page Moderna

Use quando o pedido for "landing", "site institucional", "hero", "pagina de vendas", "marketing site".

## Stack
- Next.js App Router (rota (marketing))
- Tailwind + shadcn
- framer-motion para scroll reveals
- lucide-react icones

## Estrutura de secoes (em ordem)
1. **Hero** — headline 48-64px, subheadline, 2 CTAs (primario + secundario), imagem/video/code preview a direita
2. **Logo cloud** — "usado por" com logos em grayscale hover colorido (opcional)
3. **Features grid** — 3-6 cards com icone + titulo + descricao curta
4. **Como funciona** — 3 passos visuais com numeros e conexao
5. **Social proof** — testimonials em carousel ou grid
6. **Pricing** — 2-3 tiers, destaque no recomendado
7. **FAQ** — accordion com 5-8 perguntas
8. **CTA final** — banner full-width com acao primaria
9. **Footer** — links organizados em colunas + newsletter

## Padroes visuais
- Background hero: gradient sutil cyan→purple com grain/noise overlay
- Secoes alternadas: bg-cyber-bg e bg-cyber-bg/60
- Bordas de separacao invisiveis — usar espaco (py-24) para ritmo
- CTAs sempre com glow cyber
- Texto com max-w-prose para legibilidade

## Hero reference code
```tsx
<section className="relative overflow-hidden py-24">
  <div className="absolute inset-0 bg-gradient-to-br from-cyber-cyan/10 via-transparent to-cyber-purple/10" />
  <div className="relative max-w-7xl mx-auto px-6 text-center">
    <motion.h1 initial={{opacity:0,y:20}} animate={{opacity:1,y:0}}
      className="text-5xl md:text-6xl font-bold tracking-tight text-white">
      Headline que <span className="bg-gradient-to-r from-cyber-cyan to-cyber-purple bg-clip-text text-transparent">converte</span>
    </motion.h1>
    <p className="mt-6 text-lg text-cyber-muted max-w-2xl mx-auto">
      Subheadline clara em uma ou duas frases.
    </p>
    <div className="mt-10 flex gap-4 justify-center">
      <Button size="lg">Comecar gratis</Button>
      <Button size="lg" variant="outline">Ver demo</Button>
    </div>
  </div>
</section>
```

## Regras
- Performance: imagens em next/image com priority no hero
- SEO: metadata no layout com openGraph
- Acessibilidade: aria-label em icon buttons
- Mobile-first: testar em 375px antes de desktop