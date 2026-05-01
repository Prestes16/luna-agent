# Template: Electron + React App (padrao Luna Desktop)

Use este template sempre que o usuario pedir "app", "ferramenta com interface", "tracker", "dashboard", "painel", "tool desktop" ou qualquer coisa que envolva UI para uso continuo.

## Stack obrigatoria
- Electron (main process em JS puro ou TS)
- React 18 + TypeScript
- Vite como bundler (electron-vite ou vite + electron-builder)
- Tailwind CSS para estilizacao
- Zustand para estado global (quando houver mais de 2 telas)
- React Router (HashRouter) para navegacao
- lucide-react para icones

## Estrutura de pastas esperada
```
meu-app/
  package.json
  vite.config.ts
  electron/
    main.ts          # processo principal
    preload.ts       # bridge segura
  src/
    main.tsx         # entry React
    App.tsx          # rotas
    index.css        # tailwind base + tokens cyber
    components/
    pages/
    store/
    hooks/
  tailwind.config.ts
  tsconfig.json
```

## package.json minimo
```json
{
  "name": "meu-app",
  "version": "0.1.0",
  "main": "dist-electron/main.js",
  "scripts": {
    "dev": "electron-vite dev",
    "build": "electron-vite build",
    "preview": "electron-vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.0",
    "zustand": "^4.5.5",
    "lucide-react": "^0.445.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.20",
    "electron": "^32.0.0",
    "electron-vite": "^2.3.0",
    "postcss": "^8.4.45",
    "tailwindcss": "^3.4.10",
    "typescript": "^5.5.4",
    "vite": "^5.4.2"
  }
}
```

## Scaffolding rapido
```bash
# Opcao 1: scaffold oficial
npx create-electron-app@latest meu-app --template=vite-typescript

# Opcao 2: vite + electron manual
npm create vite@latest meu-app -- --template react-ts
cd meu-app
npm i -D electron electron-vite electron-builder tailwindcss postcss autoprefixer
npm i react-router-dom zustand lucide-react
npx tailwindcss init -p
```

## Padrao visual (cyber/dark - ver design-tokens.md)
- Fundo base: #0a0f1e
- Accent cyan: #00d4ff
- Accent purple: #7c3aed
- Texto muted: #8b949e
- Bordas: rgba(0, 212, 255, 0.15) normal, rgba(0, 212, 255, 0.4) hover
- Fonte UI: -apple-system, Segoe UI, system-ui
- Fonte mono: JetBrains Mono, Fira Code, monospace

## Regras de entrega
1. Criar o projeto rodando o scaffold com run_command - nao escrever package.json manualmente se o scaffold cria igual
2. Instalar dependencias imediatamente apos o scaffold (npm install)
3. Aplicar tema cyber no index.css e no tailwind.config.ts antes de qualquer tela
4. Primeira tela ja deve estar funcional (nao placeholder vazio)
5. npm run dev deve iniciar sem erros antes de encerrar a sessao