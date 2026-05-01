import { Suspense, lazy, useEffect, useRef, useState, useCallback } from 'react'
import { HashRouter as Router, Routes, Route } from 'react-router-dom'
import { useStore } from '@store/appStore'
import Layout from '@components/Layout'
import Login from '@pages/Login'
import './App.css'

// ── Lazy load all pages — heavy deps (web3, solana, syntax-highlighter)
//    only load when the user actually navigates to that page
const Dashboard    = lazy(() => import('@pages/Dashboard'))
const Chat         = lazy(() => import('@pages/Chat'))
const CodeAnalyzer = lazy(() => import('@pages/CodeAnalyzer'))
const Security     = lazy(() => import('@pages/Security'))
const Blockchain   = lazy(() => import('@pages/Blockchain'))
const Settings     = lazy(() => import('@pages/Settings'))
const Workspace    = lazy(() => import('@pages/Workspace'))
const Projects     = lazy(() => import('@pages/Projects'))
const Credits      = lazy(() => import('@pages/Credits'))

// ── Minimal loading fallback
const PageLoader = () => (
  <div className="flex items-center justify-center h-full">
    <div className="flex flex-col items-center gap-3">
      <div className="w-8 h-8 rounded-full border-2 border-cyber-cyan border-t-transparent animate-spin" />
      <span className="text-[11px] font-mono text-cyber-muted tracking-widest uppercase">Loading</span>
    </div>
  </div>
)

// ── Tela de loading inicial (enquanto tenta restaurar sessão) ─────────────
const BootLoader = () => (
  <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
    <div className="flex flex-col items-center gap-4">
      <div className="w-10 h-10 rounded-full border-2 border-[#00d4ff] border-t-transparent animate-spin" />
      <span className="text-[11px] font-mono text-[#8b8b9a] tracking-widest uppercase">Iniciando Luna</span>
    </div>
  </div>
)

function App() {
  const { backendUrl, setBackendStatus, setLessonStats, setLunaApiToken, setApiKeys, setUserId, setUserEmail } = useStore()
  const tokenRef = useRef<string>('')

  // ── Estado de autenticação ─────────────────────────────────────────────
  // null = ainda verificando | false = não autenticado | true = autenticado
  const [authState, setAuthState] = useState<null | false | true>(null)

  // ── Callback chamado pelo Login quando o usuário autentica com sucesso ─
  const handleAuthenticated = useCallback((userId: string, email: string) => {
    console.log('[Luna] Usuário autenticado:', email, '| ID:', userId)
    setUserId(userId)
    setUserEmail(email)
    setAuthState(true)
  }, [setUserId, setUserEmail])

  // ── Startup: carregar token IPC + API keys do safeStorage + sync ao backend ─
  useEffect(() => {
    const api = window.electronAPI
    if (!api) {
      // Modo browser sem Electron — pula autenticação para desenvolvimento
      setAuthState(true)
      return
    }

    const init = async () => {
      try {
        // 1. Obtém o token de auth gerado pelo Electron no startup
        const token = await api.auth?.getToken?.() ?? ''
        tokenRef.current = token
        setLunaApiToken(token)

        // 2. Lista as keys salvas no safeStorage
        const savedKeys = await api.keys?.list?.() ?? []

        // 3. Carrega cada key e monta o objeto de providers
        const keysObj: Record<string, string> = {}
        await Promise.all(
          savedKeys.map(async (name: string) => {
            const res = await api.keys?.get?.(name)
            if (res?.value) keysObj[name] = res.value
          })
        )

        // 4. Atualiza o store local (para uso em tela)
        if (Object.keys(keysObj).length) setApiKeys(keysObj)

        // 5. Envia as keys ao backend (aguarda o backend estar pronto)
        if (Object.keys(keysObj).length && token) {
          const pushKeys = async (attempt = 0) => {
            try {
              const r = await fetch(`${backendUrl}/api/config/keys`, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  'X-Luna-Token': token,
                },
                body: JSON.stringify({ keys: keysObj }),
                signal: AbortSignal.timeout(5000),
              })
              if (!r.ok) throw new Error(`HTTP ${r.status}`)
              console.log('[Luna] API keys sincronizadas com backend')
            } catch (err) {
              // Backend pode ainda estar iniciando — retry até 5x com backoff
              if (attempt < 5) {
                setTimeout(() => pushKeys(attempt + 1), (attempt + 1) * 2000)
              } else {
                console.warn('[Luna] Não foi possível sincronizar keys com backend:', err)
              }
            }
          }
          pushKeys()
        }
      } catch (err) {
        console.warn('[Luna] Startup init error:', err)
      }

      // Auth state é definido pelo Login.tsx ao tentar restaurar sessão do safeStorage.
      // Se não tiver sessão salva, o Login exibe os botões OAuth.
      // Aqui garantimos que o boot loader sai após 500ms mesmo sem resposta OAuth.
      setTimeout(() => {
        setAuthState(prev => prev === null ? false : prev)
      }, 500)
    }

    init()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const token = tokenRef.current
    const headers: Record<string, string> = token ? { 'X-Luna-Token': token } : {}

    const check = () => {
      fetch(`${backendUrl}/health`, { signal: AbortSignal.timeout(4000), headers })
        .then((r) => r.json())
        .then((d) => setBackendStatus({ connected: true, model: d.model ?? 'gpt-4o', version: d.version ?? '4.0' }))
        .catch(() => setBackendStatus({ connected: false }))
    }
    check()
    const interval = setInterval(check, 15_000)
    return () => clearInterval(interval)
  }, [backendUrl])

  useEffect(() => {
    fetch(`${backendUrl}/lessons`, { signal: AbortSignal.timeout(4000) })
      .then((r) => r.json())
      .then((d) => setLessonStats(d))
      .catch(() => {})
  }, [backendUrl])

  // ── Boot loading ───────────────────────────────────────────────────────
  if (authState === null) return <BootLoader />

  // ── Login screen ───────────────────────────────────────────────────────
  if (authState === false) {
    return <Login onAuthenticated={handleAuthenticated} />
  }

  // ── App principal ──────────────────────────────────────────────────────
  return (
    <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Layout>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/"              element={<Dashboard />} />
            <Route path="/chat"          element={<Chat />} />
            <Route path="/code-analyzer" element={<CodeAnalyzer />} />
            <Route path="/security"      element={<Security />} />
            <Route path="/blockchain"    element={<Blockchain />} />
            <Route path="/settings"      element={<Settings />} />
            <Route path="/projects"      element={<Projects />} />
            <Route path="/workspace"     element={<Workspace />} />
            <Route path="/credits"       element={<Credits />} />
          </Routes>
        </Suspense>
      </Layout>
    </Router>
  )
}

export default App
