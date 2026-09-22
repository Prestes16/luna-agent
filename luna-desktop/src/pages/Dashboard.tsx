import React, { useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  Bot, CheckCircle2, Code2, Database, FolderOpen, MessageSquare,
  RefreshCw, Shield, Terminal, Wifi, WifiOff, Zap,
} from 'lucide-react'
import { useStore } from '@store/appStore'

function RuntimeRow({ icon: Icon, label, value, ok }: {
  icon: React.ElementType
  label: string
  value: string
  ok: boolean
}) {
  return (
    <div className="flex items-center gap-3 border-b border-white/[0.04] py-3 last:border-b-0">
      <span
        className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md"
        style={{ color: ok ? '#14f195' : '#f87171', background: ok ? 'rgba(20,241,149,0.08)' : 'rgba(248,113,113,0.08)' }}
      >
        <Icon size={15} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-mono text-[9px] text-cyber-muted">{label}</p>
        <p className="mt-0.5 truncate text-[12px] font-medium text-cyber-text" title={value}>{value}</p>
      </div>
      <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full" style={{ background: ok ? '#14f195' : '#f87171', boxShadow: ok ? '0 0 6px rgba(20,241,149,0.6)' : 'none' }} />
    </div>
  )
}

const Dashboard: React.FC = () => {
  const {
    backendUrl, backendStatus, healthLoading, refreshBackendHealth,
    workspaceName, workspacePath, chatSessions, messages, setActivePage,
  } = useStore()

  useEffect(() => { void refreshBackendHealth() }, [refreshBackendHealth])

  const mentor = backendStatus.modules?.mentor_kali_devtools
  const moduleReady = Boolean(mentor?.found && mentor?.loaded && mentor?.enabled)
  const quickActions = [
    { icon: MessageSquare, label: 'Chat', description: 'Conversar com a Luna', path: '/chat', page: 'chat', accent: '#00d4ff' },
    { icon: Shield, label: 'Security', description: 'Analisar superfícies de ataque', path: '/security', page: 'security', accent: '#14f195' },
    { icon: Code2, label: 'Code Analyzer', description: 'Revisar código local', path: '/code-analyzer', page: 'code', accent: '#9945ff' },
    { icon: Zap, label: 'Blockchain', description: 'Ferramentas Solana e Web3', path: '/blockchain', page: 'blockchain', accent: '#f59e0b' },
  ]

  return (
    <div className="dashboard-bg h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-6 py-6">
        <header className="flex flex-wrap items-start justify-between gap-4 border-b border-cyber-cyan/10 pb-5">
          <div className="min-w-0">
            <div className="mb-2 flex items-center gap-2 font-mono text-[9px] text-cyber-muted">
              <Terminal size={11} className="text-cyber-cyan" />
              <span>LOCAL AI COPILOT</span>
              <span className="rounded-full border border-cyber-green/20 bg-cyber-green/10 px-2 py-0.5 text-cyber-green">ZERO-CLOUD</span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-cyber-text">Luna Cyber</h1>
            <p className="mt-2 max-w-[65ch] text-[12px] leading-relaxed text-cyber-muted">
              Análise, desenvolvimento e segurança com inferência local supervisionada.
            </p>
          </div>

          <div
            className="flex min-h-11 items-center gap-3 rounded-lg border px-3"
            style={{
              background: backendStatus.connected ? 'rgba(20,241,149,0.05)' : 'rgba(248,113,113,0.05)',
              borderColor: backendStatus.connected ? 'rgba(20,241,149,0.2)' : 'rgba(248,113,113,0.2)',
            }}
          >
            {backendStatus.connected ? <Wifi size={15} className="text-cyber-green" /> : <WifiOff size={15} className="text-red-400" />}
            <div>
              <p className="text-[11px] font-semibold text-cyber-text">{backendStatus.connected ? 'Runtime operacional' : 'Runtime indisponível'}</p>
              <p className="mt-0.5 font-mono text-[9px] text-cyber-muted">{backendStatus.connected ? backendStatus.model : backendUrl}</p>
            </div>
            <button type="button" onClick={() => void refreshBackendHealth(true)} disabled={healthLoading} className="ml-1 inline-flex h-8 w-8 items-center justify-center rounded-md text-cyber-muted transition-colors hover:bg-white/[0.04] hover:text-cyber-cyan focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan/50 disabled:opacity-50" aria-label="Atualizar status local" title="Atualizar status local">
              <RefreshCw size={13} className={healthLoading ? 'animate-spin' : ''} />
            </button>
          </div>
        </header>

        <div className="mt-5 grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
          <section className="rounded-xl border border-cyber-cyan/10 bg-[#0d1422]/80 px-4">
            <div className="flex items-center justify-between border-b border-cyber-cyan/10 py-3">
              <div>
                <h2 className="text-sm font-semibold text-cyber-text">Runtime local</h2>
                <p className="mt-1 text-[10px] text-cyber-muted">Estado informado pelo backend, sem métricas simuladas.</p>
              </div>
              {backendStatus.checkedAt ? <span className="font-mono text-[8px] text-cyber-muted">verificado {new Date(backendStatus.checkedAt).toLocaleTimeString('pt-BR')}</span> : null}
            </div>
            <RuntimeRow icon={backendStatus.connected ? Wifi : WifiOff} label="FASTAPI" value={backendStatus.connected ? 'healthy · 127.0.0.1' : 'sem resposta'} ok={backendStatus.connected} />
            <RuntimeRow icon={Bot} label="MODELO" value={backendStatus.model} ok={backendStatus.ollama} />
            <RuntimeRow icon={Shield} label="OPERAÇÃO" value={backendStatus.supervisedMode ? 'local_copilot · supervisionado' : backendStatus.mode} ok={backendStatus.supervisedMode} />
            <RuntimeRow icon={Database} label="MENTOR KALI + DEVTOOLS" value={moduleReady ? 'carregado e habilitado' : 'não carregado'} ok={moduleReady} />
          </section>

          <section className="rounded-xl border border-cyber-cyan/10 bg-[#0d1422]/80 p-4">
            <h2 className="text-sm font-semibold text-cyber-text">Contexto ativo</h2>
            <p className="mt-1 text-[10px] text-cyber-muted">Dados reais desta instalação.</p>
            <div className="mt-4 space-y-3">
              <div className="flex items-center gap-3 rounded-lg bg-black/20 p-3">
                <FolderOpen size={15} className="flex-shrink-0 text-cyber-cyan" />
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-[9px] text-cyber-muted">WORKSPACE</p>
                  <p className="mt-0.5 truncate text-[11px] text-cyber-text" title={workspacePath}>{workspaceName || 'Nenhum selecionado'}</p>
                </div>
              </div>
              <div className="flex items-center gap-3 rounded-lg bg-black/20 p-3">
                <MessageSquare size={15} className="flex-shrink-0 text-purple-300" />
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-[9px] text-cyber-muted">CONVERSAS LOCAIS</p>
                  <p className="mt-0.5 text-[11px] text-cyber-text">{chatSessions.length} salvas · {messages.length} mensagens ativas</p>
                </div>
              </div>
              <div className="flex items-center gap-3 rounded-lg bg-black/20 p-3">
                <CheckCircle2 size={15} className="flex-shrink-0 text-cyber-green" />
                <div>
                  <p className="font-mono text-[9px] text-cyber-muted">PRIVACIDADE</p>
                  <p className="mt-0.5 text-[11px] text-cyber-text">{backendStatus.zeroCloudMode ? 'Zero-cloud ativo' : 'Verifique as configurações'}</p>
                </div>
              </div>
            </div>
          </section>
        </div>

        <section className="mt-5">
          <div className="mb-3">
            <h2 className="text-sm font-semibold text-cyber-text">Acesso rápido</h2>
            <p className="mt-1 text-[10px] text-cyber-muted">Continue direto para as ferramentas da Luna.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {quickActions.map(({ icon: Icon, label, description, path, page, accent }) => (
              <Link key={path} to={path} onClick={() => setActivePage(page)} className="group flex min-h-16 items-center gap-3 rounded-xl border border-cyber-cyan/10 bg-[#0d1422]/70 px-4 transition-colors hover:border-cyber-cyan/25 hover:bg-[#10192a] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan/50">
                <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md" style={{ color: accent, background: `${accent}12` }}><Icon size={17} /></span>
                <span><span className="block text-[12px] font-semibold text-cyber-text group-hover:text-cyber-cyan">{label}</span><span className="mt-0.5 block text-[10px] text-cyber-muted">{description}</span></span>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}

export default Dashboard
