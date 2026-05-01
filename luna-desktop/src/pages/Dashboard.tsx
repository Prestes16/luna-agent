import React, { useEffect, useState, useCallback } from 'react'
import { useStore } from '@store/appStore'
import { Link } from 'react-router-dom'
import {
  MessageSquare, Shield, Code2, Zap,
  Brain, Wifi, WifiOff, Terminal,
  Clock, Cpu, CheckCircle2,
} from 'lucide-react'

interface BackendInfo {
  model?: string
  mode?: string
  version?: string
  status?: string
}

// ── Animated status dot ──────────────────────────────────────────────────────
const StatusDot = ({ online }: { online: boolean }) => (
  <span className="relative flex h-2.5 w-2.5">
    {online && (
      <span className="absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping"
        style={{ background: '#10b981' }} />
    )}
    <span className="relative inline-flex rounded-full h-2.5 w-2.5"
      style={{ background: online ? '#10b981' : '#ef4444', boxShadow: online ? '0 0 8px #10b981' : 'none' }} />
  </span>
)

// ── Stat card V4 ─────────────────────────────────────────────────────────────
const StatCard = ({
  icon: Icon, label, value, sub, accent, delay = 0,
}: {
  icon: React.ElementType; label: string; value: string; sub: string; accent: string; delay?: number
}) => (
  <div
    className="stat-card group relative overflow-hidden"
    style={{ animationDelay: `${delay}ms` }}
  >
    {/* Accent top border */}
    <div className="absolute top-0 left-0 right-0 h-[2px]"
      style={{ background: `linear-gradient(90deg, transparent, ${accent}80, transparent)` }} />
    {/* Corner glow */}
    <div className="absolute -top-6 -right-6 w-20 h-20 rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-500"
      style={{ background: `radial-gradient(circle, ${accent}18 0%, transparent 70%)` }} />

    <div className="flex items-center justify-between mb-3">
      <span className="text-[9px] font-mono text-cyber-muted uppercase tracking-[0.18em]">{label}</span>
      <div className="w-7 h-7 rounded-lg flex items-center justify-center transition-all duration-200 group-hover:scale-110"
        style={{ background: `${accent}15`, border: `1px solid ${accent}35`, boxShadow: `0 0 12px ${accent}10` }}>
        <Icon size={13} style={{ color: accent }} />
      </div>
    </div>

    <p className="text-2xl font-bold font-mono leading-none tracking-tight"
      style={{ color: accent, textShadow: `0 0 16px ${accent}60` }}>
      {value}
    </p>
    <p className="text-[10px] text-cyber-dim mt-2 font-mono">{sub}</p>
  </div>
)

// ── Action card V4 ───────────────────────────────────────────────────────────
const ActionCard = ({
  icon: Icon, label, path, page, desc, accent, setActivePage, delay = 0,
}: {
  icon: React.ElementType; label: string; path: string; page: string
  desc: string; accent: string; setActivePage: (p: string) => void; delay?: number
}) => (
  <Link
    to={path}
    onClick={() => setActivePage(page)}
    className="card-v4 group relative p-5 cursor-pointer block transition-all duration-200"
    style={{ animationDelay: `${delay}ms` }}
    onMouseEnter={(e) => {
      const el = e.currentTarget as HTMLElement
      el.style.borderColor = `${accent}45`
      el.style.transform = 'translateY(-2px)'
      el.style.boxShadow = `0 12px 32px ${accent}12, 0 4px 12px rgba(0,0,0,0.4)`
    }}
    onMouseLeave={(e) => {
      const el = e.currentTarget as HTMLElement
      el.style.borderColor = 'rgba(0,212,255,0.1)'
      el.style.transform = 'translateY(0)'
      el.style.boxShadow = 'none'
    }}
  >
    {/* Background glow */}
    <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 rounded-xl"
      style={{ background: `radial-gradient(ellipse at 30% 30%, ${accent}08 0%, transparent 65%)` }} />

    <div className="relative">
      <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-4 transition-all duration-200 group-hover:scale-110"
        style={{
          background: `linear-gradient(135deg, ${accent}18, ${accent}08)`,
          border: `1px solid ${accent}30`,
          boxShadow: `0 0 16px ${accent}12`,
        }}>
        <Icon size={18} style={{ color: accent }} />
      </div>
      <p className="text-[13px] font-bold text-cyber-text leading-none tracking-wide mb-1.5">{label}</p>
      <p className="text-[11px] font-mono leading-relaxed" style={{ color: '#475569' }}>{desc}</p>
    </div>

    {/* Arrow indicator */}
    <div className="absolute bottom-4 right-4 opacity-0 group-hover:opacity-100 transition-all duration-200 translate-x-1 group-hover:translate-x-0">
      <span className="text-[10px] font-mono" style={{ color: accent }}>→</span>
    </div>
  </Link>
)

// ── Main Dashboard ───────────────────────────────────────────────────────────
const Dashboard: React.FC = () => {
  const { backendUrl, lessonStats, backendStatus, setBackendStatus, setLessonStats, setActivePage } = useStore()
  const [info, setInfo]     = useState<BackendInfo>({})
  const [uptime, setUptime] = useState(0)
  const [startTime]         = useState(Date.now())

  useEffect(() => {
    const t = setInterval(() => setUptime(Math.floor((Date.now() - startTime) / 1000)), 1000)
    return () => clearInterval(t)
  }, [startTime])

  const checkHealth = useCallback(() => {
    fetch(`${backendUrl}/health`, { signal: AbortSignal.timeout(3000) })
      .then((r) => r.json())
      .then((d) => { setBackendStatus({ connected: true, model: d.model ?? 'gpt-4o' }); setInfo(d) })
      .catch(() => setBackendStatus({ connected: false }))
  }, [backendUrl])

  useEffect(() => {
    checkHealth()
    fetch(`${backendUrl}/lessons`, { signal: AbortSignal.timeout(3000) })
      .then((r) => r.json()).then(setLessonStats).catch(() => {})
  }, [backendUrl])

  const formatUptime = (s: number) => {
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    const sec = s % 60
    if (h > 0) return `${h}h ${m}m`
    if (m > 0) return `${m}m ${sec}s`
    return `${sec}s`
  }

  const total        = lessonStats?.total_lessons ?? 0
  const successCount = lessonStats?.by_type
    ? Object.values(lessonStats.by_type).reduce((acc: number, t: any) => acc + (t.success ?? 0), 0) : 0
  const successRate  = total > 0 ? Math.round((successCount / total) * 100) : 0
  const isOnline     = backendStatus.connected

  const quickActions = [
    { icon: MessageSquare, label: 'Chat',          path: '/chat',          page: 'chat',       desc: 'Conversar com Luna',     accent: '#00d4ff' },
    { icon: Shield,        label: 'Security Scan', path: '/security',      page: 'security',   desc: 'Auditoria de segurança',  accent: '#10b981' },
    { icon: Code2,         label: 'Code Analyzer', path: '/code-analyzer', page: 'code',       desc: 'Analisar código',         accent: '#7c3aed' },
    { icon: Zap,           label: 'Blockchain',    path: '/blockchain',    page: 'blockchain', desc: 'Solana / Web3',           accent: '#f59e0b' },
  ]

  return (
    <div className="flex flex-col h-full overflow-y-auto dashboard-bg">

      {/* ── Hero header ──────────────────────────────────────────────────────── */}
      <div className="relative px-6 pt-6 pb-5 flex-shrink-0">
        {/* Background hero glow */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          <div className="absolute -top-20 left-1/4 w-96 h-48 rounded-full opacity-30"
            style={{ background: 'radial-gradient(ellipse, rgba(124,58,237,0.15) 0%, transparent 70%)', filter: 'blur(40px)' }} />
        </div>

        <div className="relative flex items-start justify-between">
          <div>
            {/* Breadcrumb */}
            <div className="flex items-center gap-1.5 mb-2">
              <Terminal size={11} className="text-cyber-cyan opacity-70" />
              <span className="text-[9px] font-mono text-cyber-dim uppercase tracking-[0.2em]">Luna Agent</span>
              <span className="text-[9px] text-cyber-dim opacity-40">/</span>
              <span className="text-[9px] font-mono uppercase tracking-[0.2em]" style={{ color: '#00d4ff' }}>Dashboard</span>
            </div>

            {/* Title */}
            <h1 className="text-2xl font-black font-mono tracking-tight leading-none mb-2">
              <span className="text-cyber-text">LUNA </span>
              <span className="hero-glow" style={{ color: '#00d4ff' }}>ELITE</span>
              <span className="text-cyber-text"> AGENT</span>
            </h1>

            {/* Pipeline indicator */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {['Think', 'Plan', 'Act', 'Reflect'].map((step, i) => (
                <React.Fragment key={step}>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded"
                    style={{ background: 'rgba(0,212,255,0.06)', color: '#64748b', border: '1px solid rgba(0,212,255,0.1)' }}>
                    {step}
                  </span>
                  {i < 3 && <span className="text-[9px]" style={{ color: 'rgba(0,212,255,0.3)' }}>→</span>}
                </React.Fragment>
              ))}
            </div>
          </div>

          {/* Status badge */}
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl flex-shrink-0"
            style={{
              background: isOnline ? 'rgba(16,185,129,0.07)' : 'rgba(239,68,68,0.07)',
              border: `1px solid ${isOnline ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'}`,
              boxShadow: isOnline ? '0 0 16px rgba(16,185,129,0.08)' : 'none',
            }}>
            <StatusDot online={isOnline} />
            <div>
              <p className="text-[11px] font-mono font-bold leading-none mb-0.5"
                style={{ color: isOnline ? '#10b981' : '#ef4444' }}>
                {isOnline ? 'Backend Online' : 'Offline'}
              </p>
              {isOnline && info.model && (
                <p className="text-[9px] font-mono text-cyber-dim leading-none">{info.model}</p>
              )}
            </div>
            {isOnline ? <Wifi size={12} style={{ color: '#10b981' }} /> : <WifiOff size={12} style={{ color: '#ef4444' }} />}
          </div>
        </div>

        {/* Divider */}
        <div className="accent-line-cyan mt-4 opacity-30" />
      </div>

      <div className="flex-1 px-6 pb-6 space-y-5 overflow-y-auto">

        {/* ── Stat cards ───────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard
            icon={isOnline ? Wifi : WifiOff}
            label="Backend"
            value={isOnline ? 'Online' : 'Offline'}
            sub={info.model ?? 'Sem conexão'}
            accent={isOnline ? '#10b981' : '#ef4444'}
            delay={0}
          />
          <StatCard icon={Brain}  label="Lições"   value={total.toString()} sub={`${successRate}% sucesso`} accent="#00d4ff" delay={60}  />
          <StatCard icon={Clock}  label="Uptime"   value={formatUptime(uptime)} sub="sessão atual"          accent="#7c3aed" delay={120} />
          <StatCard icon={Cpu}    label="Modo"     value={info.mode ?? 'agent'} sub={`v${info.version ?? '4.0'}`} accent="#f59e0b" delay={180} />
        </div>

        {/* ── Quick actions ─────────────────────────────────────────────── */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <div className="w-1 h-3 rounded-full" style={{ background: '#00d4ff', boxShadow: '0 0 6px #00d4ff' }} />
            <h2 className="text-[10px] font-mono text-cyber-muted uppercase tracking-[0.18em]">Acesso Rápido</h2>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {quickActions.map(({ icon, label, path, page, desc, accent }, i) => (
              <ActionCard
                key={path} icon={icon} label={label} path={path} page={page}
                desc={desc} accent={accent} setActivePage={setActivePage} delay={i * 60}
              />
            ))}
          </div>
        </div>

        {/* ── Lesson breakdown ───────────────────────────────────────────── */}
        {lessonStats?.by_type && total > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <div className="w-1 h-3 rounded-full" style={{ background: '#7c3aed', boxShadow: '0 0 6px #7c3aed' }} />
              <h2 className="text-[10px] font-mono text-cyber-muted uppercase tracking-[0.18em]">Aprendizado por Tipo</h2>
            </div>
            <div className="space-y-2">
              {Object.entries(lessonStats.by_type).map(([type, data]: [string, any]) => {
                const pct = data.total > 0 ? Math.round((data.success / data.total) * 100) : 0
                const barColor = pct >= 80 ? '#10b981' : pct >= 50 ? '#00d4ff' : '#f59e0b'
                return (
                  <div key={type} className="stat-card py-3">
                    <div className="flex items-center justify-between mb-2.5">
                      <div className="flex items-center gap-2">
                        <div className="w-1.5 h-1.5 rounded-full" style={{ background: barColor, boxShadow: `0 0 4px ${barColor}` }} />
                        <span className="text-[11px] font-mono text-cyber-text capitalize">
                          {type.replace(/_/g, ' ')}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-[10px] font-mono">
                        <span className="flex items-center gap-1" style={{ color: '#10b981' }}>
                          <CheckCircle2 size={9} />{data.success ?? 0}
                        </span>
                        <span className="text-cyber-dim">{data.total} total</span>
                        <span className="font-bold tabular-nums" style={{ color: barColor }}>{pct}%</span>
                      </div>
                    </div>
                    <div className="h-[3px] rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.05)' }}>
                      <div className="h-full rounded-full transition-all duration-700"
                        style={{ width: `${pct}%`, background: `linear-gradient(90deg, ${barColor}99, ${barColor})`, boxShadow: `0 0 6px ${barColor}60` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* ── Offline hint ───────────────────────────────────────────────── */}
        {!isOnline && (
          <div className="rounded-xl p-4 flex items-start gap-3"
            style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.15)' }}>
            <WifiOff size={14} className="mt-0.5 flex-shrink-0" style={{ color: '#ef4444' }} />
            <div>
              <p className="text-[12px] font-semibold text-cyber-text mb-1">Backend offline</p>
              <p className="text-[11px] text-cyber-muted leading-relaxed">
                Inicie o servidor Python:{' '}
                <code className="text-cyber-cyan font-mono">python run.py</code>
              </p>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}

export default Dashboard
