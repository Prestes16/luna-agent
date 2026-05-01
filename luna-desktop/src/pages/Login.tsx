import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { signInWithProvider, handleOAuthCallback, supabase } from '@services/supabase'

interface LoginProps {
  onAuthenticated: (userId: string, email: string) => void
}

const GoogleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
  </svg>
)

const XIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
  </svg>
)

// Ícone da Luna — fiel ao ícone do app (fundo gradiente roxo/azul + lua crescente)
const LunaLogo = () => (
  <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
    <defs>
      <linearGradient id="bgGrad" x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#3b1fa8"/>
        <stop offset="100%" stopColor="#1a0f6e"/>
      </linearGradient>
      <linearGradient id="moonGrad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#fde68a"/>
        <stop offset="100%" stopColor="#fbbf24"/>
      </linearGradient>
    </defs>
    {/* Fundo arredondado igual ao ícone do app */}
    <rect width="64" height="64" rx="14" fill="url(#bgGrad)"/>
    {/* Brilho sutil no topo */}
    <ellipse cx="32" cy="10" rx="22" ry="8" fill="rgba(255,255,255,0.06)"/>
    {/* Lua crescente */}
    <path
      d="M38 18a16 16 0 1 0 0 28 12 12 0 1 1 0-28z"
      fill="url(#moonGrad)"
    />
  </svg>
)

export default function Login({ onAuthenticated }: LoginProps) {
  const [loading, setLoading]           = useState<'google' | 'twitter' | null>(null)
  const [error, setError]               = useState<string | null>(null)
  const [waitingOAuth, setWaitingOAuth] = useState(false)

  // ── Escuta deep link OAuth vindo do main process ───────────────────────
  useEffect(() => {
    const api = window.electronAPI
    if (!api?.auth?.onDeepLink) return

    api.auth.onDeepLink(async (url: string) => {
      try {
        setWaitingOAuth(true)
        setError(null)
        const session = await handleOAuthCallback(url)
        if (!session) throw new Error('Sessão inválida após callback OAuth')
        await api.auth.saveSession?.(session.access_token, session.refresh_token)
        onAuthenticated(session.user.id, session.user.email ?? '')
      } catch (err: any) {
        setError(err.message ?? 'Erro ao processar login')
        setWaitingOAuth(false)
        setLoading(null)
      }
    })
  }, [onAuthenticated])

  // ── Tenta restaurar sessão salva ───────────────────────────────────────
  useEffect(() => {
    const tryRestore = async () => {
      try {
        const api = window.electronAPI
        const saved = await api?.auth?.loadSession?.()
        if (!saved) return
        const { data, error: err } = await supabase.auth.setSession({
          access_token:  saved.accessToken,
          refresh_token: saved.refreshToken,
        })
        if (err || !data.session) return
        onAuthenticated(data.session.user.id, data.session.user.email ?? '')
      } catch { /* sessão expirada — mostra login */ }
    }
    tryRestore()
  }, [onAuthenticated])

  const handleLogin = async (provider: 'google' | 'twitter') => {
    setLoading(provider)
    setError(null)
    try {
      await signInWithProvider(provider)
      setWaitingOAuth(true)
    } catch (err: any) {
      setError(err.message ?? 'Erro ao iniciar login')
      setLoading(null)
    }
  }

  return (
    <div className="cyber-bg scanlines flex h-screen w-full items-center justify-center overflow-hidden">

      {/* Glow orbs — mesmo padrão do app */}
      <div className="pointer-events-none absolute top-1/4 left-1/3 h-80 w-80 rounded-full bg-[#00d4ff] opacity-[0.04] blur-[100px]" />
      <div className="pointer-events-none absolute bottom-1/4 right-1/3 h-64 w-64 rounded-full bg-[#7c3aed] opacity-[0.04] blur-[80px]" />

      <AnimatePresence mode="wait">
        {waitingOAuth ? (
          /* ── Aguardando browser ────────────────────────────────────────── */
          <motion.div
            key="waiting"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center gap-5 text-center"
          >
            <div className="relative h-14 w-14">
              <div className="absolute inset-0 animate-spin rounded-full border-2 border-[#00d4ff] border-t-transparent" />
              <div className="absolute inset-2 animate-ping rounded-full border border-[#00d4ff] opacity-20" />
            </div>
            <div>
              <p className="font-mono text-xs tracking-[0.2em] text-[#00d4ff] uppercase">Aguardando autorização</p>
              <p className="mt-1 text-[11px] text-[#4a5568]">Complete o login no seu browser</p>
            </div>
            <button
              onClick={() => { setWaitingOAuth(false); setLoading(null) }}
              className="text-[11px] text-[#4a5568] underline hover:text-[#8b9ab0] transition-colors"
            >
              Cancelar
            </button>
          </motion.div>

        ) : (
          /* ── Card de login ─────────────────────────────────────────────── */
          <motion.div
            key="login"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -16 }}
            transition={{ duration: 0.35 }}
            className="w-full max-w-[360px] px-4"
          >
            {/* Glass card — mesmo glass-strong do sidebar */}
            <div className="glass-strong rounded-2xl border border-[rgba(0,212,255,0.12)] p-8">

              {/* Logo */}
              <div className="mb-7 flex flex-col items-center gap-3">
                <motion.div
                  animate={{
                    filter: [
                      'drop-shadow(0 0 6px rgba(0,212,255,0.4))',
                      'drop-shadow(0 0 18px rgba(0,212,255,0.7))',
                      'drop-shadow(0 0 6px rgba(0,212,255,0.4))',
                    ]
                  }}
                  transition={{ duration: 3, repeat: Infinity }}
                >
                  <LunaLogo />
                </motion.div>

                <div className="text-center">
                  <h1 className="glow-text-cyan text-xl font-bold tracking-wide text-white">
                    LUNA <span className="text-[#00d4ff]">AGENT</span>
                  </h1>
                  <p className="mt-0.5 font-mono text-[10px] tracking-[0.18em] text-[#4a5568] uppercase">
                    Elite AI · Web3 · Bug Bounty
                  </p>
                </div>
              </div>

              {/* Tagline */}
              <p className="mb-5 text-center text-[12px] leading-relaxed text-[#4a5568]">
                Faça login para acessar seus <span className="text-[#00d4ff]">Grains</span> e continuar de qualquer dispositivo
              </p>

              {/* Error */}
              {error && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-center text-[11px] text-red-400"
                >
                  {error}
                </motion.div>
              )}

              {/* Botões */}
              <div className="space-y-2.5">
                {/* Google */}
                <motion.button
                  onClick={() => handleLogin('google')}
                  disabled={loading !== null}
                  whileHover={{ scale: 1.015 }}
                  whileTap={{ scale: 0.985 }}
                  className="flex w-full items-center justify-center gap-2.5 rounded-xl bg-white px-4 py-2.5 text-[13px] font-medium text-gray-800 transition-all duration-150 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {loading === 'google'
                    ? <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-400 border-t-transparent" />
                    : <GoogleIcon />
                  }
                  Continuar com Google
                </motion.button>

                {/* X / Twitter */}
                <motion.button
                  onClick={() => handleLogin('twitter')}
                  disabled={loading !== null}
                  whileHover={{ scale: 1.015 }}
                  whileTap={{ scale: 0.985 }}
                  className="flex w-full items-center justify-center gap-2.5 rounded-xl border border-[rgba(0,212,255,0.15)] bg-[#0d1117] px-4 py-2.5 text-[13px] font-medium text-white transition-all duration-150 hover:border-[rgba(0,212,255,0.3)] hover:bg-[#111827] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {loading === 'twitter'
                    ? <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    : <XIcon />
                  }
                  Continuar com X (Twitter)
                </motion.button>
              </div>

              {/* Divisor */}
              <div className="my-5 flex items-center gap-3">
                <div className="h-px flex-1 bg-[rgba(0,212,255,0.08)]" />
                <span className="text-[10px] text-[#2a3042]">seguro</span>
                <div className="h-px flex-1 bg-[rgba(0,212,255,0.08)]" />
              </div>

              {/* Nota de segurança */}
              <div className="flex items-start gap-2 rounded-lg border border-[rgba(0,212,255,0.08)] bg-[rgba(0,212,255,0.03)] p-3">
                <svg className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-[#00d4ff]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                <p className="text-[10px] leading-relaxed text-[#4a5568]">
                  Grains vinculados à conta — acessíveis em qualquer dispositivo. Nenhuma senha armazenada.
                </p>
              </div>
            </div>

            {/* Versão */}
            <p className="mt-3 text-center font-mono text-[9px] tracking-widest text-[#2a3042] uppercase">
              Luna v4.0 · Powered by Claude &amp; GPT-4o
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
