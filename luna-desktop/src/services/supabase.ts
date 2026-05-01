import { createClient } from '@supabase/supabase-js'

// ── Supabase Auth Client ───────────────────────────────────────────────────
// ANON key: segura para usar no frontend (Row Level Security protege os dados)
// SERVICE key: somente no backend (main.ts / FastAPI) — nunca expor no renderer

const SUPABASE_URL  = 'https://bddwpgwqrlfhvezthpsv.supabase.co'
const SUPABASE_ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJkZHdwZ3dxcmxmaHZlenRocHN2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY3MTQ4MDcsImV4cCI6MjA5MjI5MDgwN30.hW0Vdz2MpPMPpR4G6h8WCksdCPPpkDGGMdLDcuRPvEA'

/**
 * Deep link redirect para Electron — o app.setAsDefaultProtocolClient('luna-agent')
 * em main.ts garante que o sistema operacional redireciona de volta para o app.
 */
export const OAUTH_REDIRECT_URL = 'luna-agent://auth/callback'

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON, {
  auth: {
    // Electron não tem localStorage nativo no contexto sandbox — usa memória
    // Os tokens são persistidos via safeStorage no main process (IPC)
    storage: {
      getItem:    (key: string) => window.__lunaAuthStore?.get(key) ?? null,
      setItem:    (key: string, value: string) => { window.__lunaAuthStore?.set(key, value) },
      removeItem: (key: string) => { window.__lunaAuthStore?.delete(key) },
    },
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: false,
  }
})

// ── Helper: inicia OAuth no browser padrão do sistema ─────────────────────
export async function signInWithProvider(provider: 'google' | 'twitter') {
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider,
    options: {
      redirectTo: OAUTH_REDIRECT_URL,
      skipBrowserRedirect: true,  // não deixa o Supabase navegar — fazemos via shell
    }
  })

  if (error) throw error

  // Abre a URL de autorização no browser padrão do SO via IPC
  if (data?.url) {
    await window.electronAPI?.shell?.openExternal(data.url)
  }
}

// ── Helper: troca o deep-link URL pelo session do Supabase ─────────────────
export async function handleOAuthCallback(deepLinkUrl: string) {
  // O deep link tem formato: luna-agent://auth/callback#access_token=...&refresh_token=...
  const hash = deepLinkUrl.split('#')[1] ?? deepLinkUrl.split('?')[1] ?? ''
  const params = new URLSearchParams(hash)

  const accessToken  = params.get('access_token')
  const refreshToken = params.get('refresh_token')

  if (!accessToken || !refreshToken) {
    throw new Error('Deep link inválido: tokens não encontrados')
  }

  const { data, error } = await supabase.auth.setSession({
    access_token:  accessToken,
    refresh_token: refreshToken,
  })

  if (error) throw error
  return data.session
}

// ── Helper: sessão atual ───────────────────────────────────────────────────
export async function getSession() {
  const { data } = await supabase.auth.getSession()
  return data.session
}

export async function signOut() {
  await supabase.auth.signOut()
}

// ── Declaração global para o mini-store de auth em memória ────────────────
declare global {
  interface Window {
    __lunaAuthStore?: Map<string, string>
  }
}
