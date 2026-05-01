import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useStore } from '@store/appStore'
import { useI18n } from '@i18n/hooks'
import type { TranslationKey } from '@i18n/translations'
import {
  MessageSquare, LayoutDashboard, Shield, Code2,
  Zap, Settings, ChevronLeft, ChevronRight, Circle, Cpu,
  FolderOpen, FileText, Volume2, Brain, Activity, FolderTree, Coins, FolderKanban,
} from 'lucide-react'
import WorkspaceSelector from './WorkspaceSelector'

// Keys only — labels resolved via t() inside the component so locale changes re-render
const NAV_ITEMS: { icon: React.ElementType; key: TranslationKey; path: string; page: string }[] = [
  { icon: MessageSquare,   key: 'nav.chat',         path: '/chat',          page: 'chat' },
  { icon: LayoutDashboard, key: 'nav.dashboard',    path: '/',              page: 'dashboard' },
  { icon: FolderTree,      key: 'nav.workspace',    path: '/workspace',     page: 'workspace' },
  { icon: FolderKanban,    key: 'nav.projects',     path: '/projects',      page: 'projects' },
  { icon: Code2,           key: 'nav.codeAnalyzer', path: '/code-analyzer', page: 'code' },
  { icon: Shield,          key: 'nav.security',     path: '/security',      page: 'security' },
  { icon: Zap,             key: 'nav.blockchain',   path: '/blockchain',    page: 'blockchain' },
  { icon: Coins,           key: 'nav.credits',      path: '/credits',       page: 'credits' },
]

// ── Memory pressure indicator ─────────────────────────────────────────────────
function MemoryBar({ messages }: { messages: number }) {
  // Backend compresses at _max_exchanges=14 (build) / 8 (normal).
  // Visual scale: 30 msgs = 100% so the bar only turns red when context
  // is genuinely overloaded, not on a normal multi-turn conversation.
  const THRESHOLD = 30
  const pct = Math.min(100, Math.round((messages / THRESHOLD) * 100))
  const color = pct >= 85 ? '#ef4444' : pct >= 55 ? '#f59e0b' : '#00d4ff'
  const label = pct >= 85 ? 'Alta' : pct >= 55 ? 'Média' : 'Baixa'

  return (
    <div title={`${messages} mensagens no contexto (máx ~${THRESHOLD})`}>
      <div className="flex justify-between mb-1">
        <span className="text-[9px] font-mono text-cyber-dim uppercase tracking-wider flex items-center gap-1">
          <Brain size={8} style={{ color }} />
          Memória
        </span>
        <span className="text-[9px] font-mono" style={{ color }}>
          {label}
          <span className="text-cyber-dim ml-1">({messages})</span>
        </span>
      </div>
      <div className="h-[3px] rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${color}aa, ${color})`,
            boxShadow: pct >= 55 ? `0 0 4px ${color}88` : 'none',
          }}
        />
      </div>
    </div>
  )
}

const Sidebar: React.FC = () => {
  const location = useLocation()
  const { t } = useI18n()
  const {
    sidebarCollapsed, setSidebarCollapsed, setActivePage,
    backendStatus, currentModel,
    activeFiles, workspacePath, projectMarkdown,
    isSpeaking, voiceEnabled,
    messages, liveToolEvents,
  } = useStore()

  const isActive = (path: string) =>
    path === '/' ? location.pathname === '/' : location.pathname.startsWith(path)

  const runningTools    = liveToolEvents.filter((e) => e.status === 'running').length
  const hasContextDoc   = !!(workspacePath && projectMarkdown[workspacePath])
  const activeFileCount = activeFiles.length

  // Derive model provider label
  const providerOf = (m: string) => {
    if (m === 'auto') return 'Auto'
    if (m.startsWith('gpt'))    return 'OpenAI'
    if (m.startsWith('claude')) return 'Anthropic'
    if (m.startsWith('grok'))   return 'xAI'
    if (m.startsWith('llama') || m.includes('405b')) return 'Llama'
    return ''
  }
  const providerColor: Record<string, string> = {
    Auto: '#00d4ff', OpenAI: '#10b981', Anthropic: '#e040fb',
    xAI: '#7c3aed', Llama: '#f97316',
  }
  const provider = providerOf(currentModel)

  return (
    <div className="flex flex-col h-full select-none">

      {/* ── Logo ─────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2.5 px-3 py-4 border-b border-cyber-border min-h-[60px]">
        <div
          className="flex-shrink-0 w-8 h-8 rounded-lg bg-gradient-to-br from-cyber-purple to-cyber-cyan flex items-center justify-center text-base"
          style={{ boxShadow: '0 0 20px rgba(124,58,237,0.7), 0 0 40px rgba(0,212,255,0.15)' }}
        >
          🌙
        </div>
        {!sidebarCollapsed && (
          <div className="overflow-hidden">
            <p className="text-sm font-bold text-cyber-cyan leading-none" style={{ textShadow: '0 0 10px rgba(0,212,255,0.7)' }}>
              LUNA
            </p>
            <p className="text-[10px] text-cyber-muted font-mono mt-0.5 tracking-widest">ELITE AGENT v4</p>
          </div>
        )}
        {/* Running tools pulse — visible even when collapsed */}
        {runningTools > 0 && (
          <div
            className="ml-auto flex-shrink-0 w-2 h-2 rounded-full animate-pulse"
            style={{ background: '#f59e0b', boxShadow: '0 0 6px #f59e0b' }}
            title={`${runningTools} tool(s) running`}
          />
        )}
      </div>

      {/* ── Nav ──────────────────────────────────────────────────────── */}
      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
        {NAV_ITEMS.map(({ icon: Icon, key, path, page }) => {
          const label = t(key)
          const active = isActive(path)
          // Badge for Chat: unread tool ops indicator
          const showBadge = page === 'chat' && runningTools > 0

          return (
            <Link
              key={path}
              to={path}
              onClick={() => setActivePage(page)}
              className={`sidebar-link ${active ? 'active' : ''}`}
              data-tooltip={sidebarCollapsed ? label : undefined}
            >
              <Icon size={16} className="flex-shrink-0" />
              {!sidebarCollapsed && <span className="flex-1">{label}</span>}
              {showBadge && (
                <span
                  className="flex-shrink-0 text-[8px] font-bold font-mono rounded-full px-1"
                  style={{ background: '#f59e0b', color: '#080b14', minWidth: 14, textAlign: 'center' }}
                >
                  {runningTools}
                </span>
              )}
            </Link>
          )
        })}
      </nav>

      {/* ── Workspace selector ────────────────────────────────────────── */}
      {sidebarCollapsed
        ? <WorkspaceSelector collapsed />
        : <WorkspaceSelector />
      }

      {/* ── Context & Files indicators (expanded only) ────────────────── */}
      {!sidebarCollapsed && (activeFileCount > 0 || hasContextDoc) && (
        <div
          className="mx-2 mb-2 px-2.5 py-2 rounded-md space-y-1.5"
          style={{ background: 'rgba(0,212,255,0.03)', border: '1px solid rgba(0,212,255,0.08)' }}
        >
          {activeFileCount > 0 && (
            <div className="flex items-center gap-1.5">
              <FolderOpen size={10} className="text-cyber-cyan" />
              <span className="text-[10px] font-mono text-cyber-muted flex-1">Arquivos ativos</span>
              <span
                className="text-[9px] font-mono px-1.5 py-0.5 rounded-full"
                style={{ background: 'rgba(0,212,255,0.12)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.2)' }}
              >
                {activeFileCount}
              </span>
            </div>
          )}
          {hasContextDoc && (
            <div className="flex items-center gap-1.5">
              <FileText size={10} className="text-purple-400" />
              <span className="text-[10px] font-mono text-cyber-muted flex-1">Contexto salvo</span>
              <div className="w-1.5 h-1.5 rounded-full bg-purple-400" style={{ boxShadow: '0 0 4px #a78bfa' }} />
            </div>
          )}
        </div>
      )}

      {/* ── Luna Status ───────────────────────────────────────────────── */}
      {!sidebarCollapsed && (
        <div
          className="mx-2 mb-2 px-2.5 py-2 rounded-md space-y-2"
          style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.1)' }}
        >
          {/* Backend + model */}
          <div className="flex items-center gap-1.5">
            <Circle
              size={6}
              className={backendStatus.connected ? 'text-cyber-green fill-cyber-green' : 'text-cyber-red fill-cyber-red'}
            />
            <span className="text-[10px] font-mono text-cyber-muted flex-1">
              {backendStatus.connected ? 'Online' : 'Offline'}
            </span>
            {provider && (
              <span
                className="text-[9px] font-mono px-1 rounded"
                style={{ background: `${providerColor[provider] ?? '#64748b'}18`, color: providerColor[provider] ?? '#64748b' }}
              >
                {provider}
              </span>
            )}
          </div>

          {/* Model name */}
          <div className="flex items-center gap-1.5">
            <Cpu size={10} className="text-cyber-cyan" />
            <span className="text-[10px] font-mono text-cyber-dim truncate">{currentModel}</span>
          </div>

          {/* Voice indicator */}
          {voiceEnabled && (
            <div className="flex items-center gap-1.5">
              <Volume2
                size={10}
                className={isSpeaking ? 'text-cyber-cyan animate-pulse' : 'text-cyber-dim'}
              />
              <span className="text-[10px] font-mono text-cyber-muted flex-1">
                {isSpeaking ? 'Falando...' : 'Voz ativa'}
              </span>
              {isSpeaking && (
                <div className="flex gap-0.5">
                  {[0, 1, 2].map((i) => (
                    <div
                      key={i}
                      className="w-0.5 rounded-full"
                      style={{
                        height: 8,
                        background: '#00d4ff',
                        animation: `voiceBar 0.8s ease-in-out ${i * 0.15}s infinite alternate`,
                        opacity: 0.8,
                      }}
                    />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Memory pressure bar */}
          <MemoryBar messages={messages.length} />
        </div>
      )}

      {/* Collapsed: micro status dots */}
      {sidebarCollapsed && (
        <div className="flex flex-col items-center gap-1.5 py-2">
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{
              background: backendStatus.connected ? '#10b981' : '#ef4444',
              boxShadow: backendStatus.connected ? '0 0 4px #10b981' : 'none',
            }}
            title={backendStatus.connected ? 'Backend online' : 'Backend offline'}
          />
          {isSpeaking && (
            <div
              className="w-1.5 h-1.5 rounded-full animate-pulse"
              style={{ background: '#00d4ff', boxShadow: '0 0 4px #00d4ff' }}
              title="Falando"
            />
          )}
          {activeFileCount > 0 && (
            <div
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: '#7c3aed', boxShadow: '0 0 4px #7c3aed' }}
              title={`${activeFileCount} arquivos ativos`}
            />
          )}
        </div>
      )}

      {/* ── Activity indicator (tools running) ───────────────────────── */}
      {runningTools > 0 && !sidebarCollapsed && (
        <div
          className="mx-2 mb-2 px-2.5 py-1.5 rounded-md flex items-center gap-2"
          style={{ background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)' }}
        >
          <Activity size={10} className="text-amber-400 animate-pulse" />
          <span className="text-[10px] font-mono text-amber-400 flex-1">
            {runningTools} tool{runningTools > 1 ? 's' : ''} ativo{runningTools > 1 ? 's' : ''}
          </span>
        </div>
      )}

      {/* ── Settings + Collapse ───────────────────────────────────────── */}
      <div className="px-2 pb-3 space-y-0.5 border-t border-cyber-border pt-2">
        <Link
          to="/settings"
          onClick={() => setActivePage('settings')}
          className={`sidebar-link ${isActive('/settings') ? 'active' : ''}`}
          data-tooltip={sidebarCollapsed ? t('nav.settings') : undefined}
        >
          <Settings size={16} className="flex-shrink-0" />
          {!sidebarCollapsed && <span>{t('nav.settings')}</span>}
        </Link>

        <button
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          className="sidebar-link w-full"
          data-tooltip={sidebarCollapsed ? t('nav.expand') : undefined}
        >
          {sidebarCollapsed
            ? <ChevronRight size={16} className="flex-shrink-0" />
            : <><ChevronLeft size={16} className="flex-shrink-0" /><span>{t(
'nav.collapse')}</span></>
          }
        </button>
      </div>
    </div>
  )
}

export default Sidebar
