import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { I18nProvider } from '@i18n'
import { initErrorCapture } from './services/bugReport'
import './App.css'

// Activate global error capture before mounting React
initErrorCapture()

// ── Mini-store em memória para os tokens do Supabase Auth ─────────────────
// O Supabase precisa de um storage para persistir a sessão.
// Electron com sandbox=true não tem localStorage disponível no renderer.
// Usamos um Map em memória + sincronizamos os tokens via safeStorage (IPC).
window.__lunaAuthStore = new Map<string, string>()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </React.StrictMode>,
)
