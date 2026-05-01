# Design Tokens Luna (referencia visual canonica)

Todos os apps/sites construidos pela Luna seguem esse vocabulario visual por padrao, salvo pedido explicito do usuario.

## Paleta cyber/dark

### Background
- Canvas principal: #0a0f1e
- Surface 1 (cards): rgba(255, 255, 255, 0.02)
- Surface 2 (elevated): rgba(10, 15, 28, 0.95)
- Input bg: rgba(0, 212, 255, 0.03)

### Accents
- Cyan primario: #00d4ff
- Purple secundario: #7c3aed
- Green success: #10b981
- Orange warn: #f59e0b
- Red danger: #ef4444

### Texto
- Texto principal: #e6edf3
- Texto muted: #8b949e
- Texto desabilitado: #4a5568

### Bordas
- Padrao: rgba(0, 212, 255, 0.15)
- Hover: rgba(0, 212, 255, 0.4)
- Ativo: rgba(0, 212, 255, 0.6)
- Foco ring: 0 0 0 3px rgba(0, 212, 255, 0.25)

## Tipografia
- UI: "Inter", "-apple-system", "Segoe UI", system-ui, sans-serif
- Code: "JetBrains Mono", "Fira Code", "Consolas", monospace
- Escala: 12 / 14 / 16 / 18 / 20 / 24 / 32 / 48

## Espacamento (Tailwind scale)
Favorecer multiplos de 4: 2, 3, 4, 6, 8, 12, 16.

## Bordas arredondadas
- Botoes e inputs: rounded-md (6px)
- Cards: rounded-xl (12px)
- Modais: rounded-2xl (16px)
- Chips/pills: rounded-full

## Shadows
- Card: 0 1px 2px rgba(0,0,0,0.3)
- Elevated: 0 8px 24px rgba(0, 0, 0, 0.45)
- Glow cyan: 0 0 24px rgba(0, 212, 255, 0.25)

## Transicoes padrao
- transition-all duration-200 ease-out em hover/focus
- fade-in duration-300 para entrada de elementos

## Tailwind config snippet (copiar para tailwind.config.ts)
```ts
export default {
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        cyber: {
          bg: "#0a0f1e",
          cyan: "#00d4ff",
          purple: "#7c3aed",
          muted: "#8b949e",
        },
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "Consolas", "monospace"],
      },
    },
  },
}
```

## Regras de uso
1. Nunca usar white puro (#ffffff) como background - quebra o tema
2. Nunca usar cores primarias fora desta paleta sem justificativa explicita
3. Sempre testar contraste de texto sobre surface (minimo AA WCAG)
4. Icones de lucide-react com stroke-width 1.5 ou 2 (nunca 3+)