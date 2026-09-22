import { Suspense, lazy, useEffect, useState } from 'react'
import { HashRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { useStore } from '@store/appStore'
import Layout from '@components/Layout'
import { fetchLessonStats } from '@services/lessons'
import './App.css'

// Heavy pages stay lazy so the local desktop shell opens quickly.
const Dashboard    = lazy(() => import('@pages/Dashboard'))
const Chat         = lazy(() => import('@pages/Chat'))
const CodeAnalyzer = lazy(() => import('@pages/CodeAnalyzer'))
const Security     = lazy(() => import('@pages/Security'))
const Blockchain   = lazy(() => import('@pages/Blockchain'))
const Settings     = lazy(() => import('@pages/Settings'))
const Workspace    = lazy(() => import('@pages/Workspace'))
const Projects     = lazy(() => import('@pages/Projects'))

const PageLoader = () => (
  <div className="flex h-full items-center justify-center" role="status" aria-live="polite">
    <div className="flex flex-col items-center gap-3">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyber-cyan border-t-transparent" />
      <span className="font-mono text-[11px] uppercase tracking-widest text-cyber-muted">Carregando</span>
    </div>
  </div>
)

const BootLoader = () => (
  <div className="flex min-h-screen items-center justify-center bg-[#080b14]" role="status" aria-live="polite">
    <div className="flex flex-col items-center gap-4">
      <div
        className="flex h-12 w-12 items-center justify-center rounded-xl border border-cyber-cyan/30 bg-cyber-cyan/5 text-2xl"
        aria-hidden="true"
      >
        🌙
      </div>
      <div className="text-center">
        <p className="font-mono text-xs font-semibold tracking-[0.16em] text-cyber-cyan">LUNA CYBER</p>
        <p className="mt-1 font-mono text-[10px] text-cyber-muted">Preparando o runtime local</p>
      </div>
    </div>
  </div>
)

function App() {
  const {
    backendUrl,
    lunaApiToken,
    currentModel,
    zeroCloudMode,
    setLessonStats,
    setLunaApiToken,
    setCurrentModel,
    setZeroCloudMode,
    refreshBackendHealth,
  } = useStore()
  const [bootReady, setBootReady] = useState(false)

  useEffect(() => {
    if (currentModel !== 'luna-cyber-fast' && currentModel !== 'qwen3.5:4b') {
      setCurrentModel('luna-cyber-fast')
    }
  }, [currentModel, setCurrentModel])

  useEffect(() => {
    if (!zeroCloudMode) setZeroCloudMode(true)
  }, [setZeroCloudMode, zeroCloudMode])

  // The only startup credential is the local Electron ↔ FastAPI security token.
  useEffect(() => {
    let active = true

    const initializeLocalRuntime = async () => {
      try {
        const token = await window.electronAPI?.auth?.getToken?.() ?? ''
        if (active) setLunaApiToken(token)
      } catch (error) {
        console.warn('[Luna] Não foi possível carregar o token local:', error)
      } finally {
        if (active) setBootReady(true)
      }
    }

    void initializeLocalRuntime()
    return () => { active = false }
  }, [setLunaApiToken])

  useEffect(() => {
    void refreshBackendHealth(true)
    const interval = window.setInterval(() => void refreshBackendHealth(true), 15_000)
    return () => window.clearInterval(interval)
  }, [backendUrl, lunaApiToken, refreshBackendHealth])

  useEffect(() => {
    if (!lunaApiToken) return

    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 4_000)
    void fetchLessonStats(backendUrl, lunaApiToken, controller.signal)
      .then(setLessonStats)
      .catch(() => undefined)
      .finally(() => window.clearTimeout(timeout))

    return () => {
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [backendUrl, lunaApiToken, setLessonStats])

  if (!bootReady) return <BootLoader />

  return (
    <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Layout>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/code-analyzer" element={<CodeAnalyzer />} />
            <Route path="/security" element={<Security />} />
            <Route path="/blockchain" element={<Blockchain />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/workspace" element={<Workspace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Layout>
    </Router>
  )
}

export default App
