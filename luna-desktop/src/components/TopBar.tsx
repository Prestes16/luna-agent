import React, { useState } from 'react'
import { useStore } from '@store/appStore'
import {
  ChevronDown, PanelRight, Trash2, Zap, Volume2,
  FolderOpen, BookMarked, Terminal, Activity,
} from 'lucide-react'

// ── Model registry ────────────────────────────────────────────────────────────
interface ModelDef {
  id: string
  label: string
  provider: string
  color: string
  cost: 'free' | 'low' | 'mid' | 'high' | 'premium'
  desc?: string
}

const MODELS: ModelDef[] = [
  {
    id: 'auto', label: 'Auto', provider: 'Smart', color: '#00d4ff', cost: 'low',
    desc: 'Roteia por tipo: segurança→Claude · Web3/código→Grok-3 · triage→Llama grátis',
  },
  {
    id: 'grok-3', label: 'Grok-3', provider: 'xAI', color: '#7c3aed', cost: 'high',
    desc: 'Flagship xAI · Web3 · código · 131k contexto',
  },
  {
    id: 'grok-3-mini', label: 'Grok-3 Mini', provider: 'xAI', color: '#7c3aed', cost: 'mid',
    desc: 'Rápido · custo-benefício · raciocínio eficiente',
  },
  {
    id: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6', provider: 'Anthropic', color: '#e040fb', cost: 'high',
    desc: 'Elite security research · bug bounty · 200k contexto',
  },
  {
    id: 'claude-opus-4-6', label: 'Claude Opus 4.6', provider: 'Anthropic', color: '#e040fb', cost: 'premium',
    desc: 'Raciocínio máximo · exploits cirúrgicos · auditoria profunda',
  },
  {
    id: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5', provider: 'Anthropic', color: '#e040fb', cost: 'low',
    desc: 'Ultra-rápido · análise de snippets · custo mínimo',
  },
  {
    id: 'gpt-4o', label: 'GPT-4o', provider: 'OpenAI', color: '#10b981', cost: 'high',
    desc: 'Fallback confiável · visão · multimodal',
  },
  {
    id: 'gpt-4o-mini', label: 'GPT-4o Mini', provider: 'OpenAI', color: '#10b981', cost: 'low',
    desc: 'Tarefas simples · baixo custo',
  },
  {
    id: 'llama-3.3-70b-versatile', label: 'Llama 3.3 70B', provider: 'Groq', color: '#f97316', cost: 'free',
    desc: 'Grátis · consultas gerais · análise rápida',
  },
  {
    id: 'llama-3.1-8b-instant', label: 'Llama 3.1 8B', provider: 'Groq', color: '#f97316', cost: 'free',
    desc: 'Grátis · triage instantâneo · < 200ms',
  },
  {
    id: 'meta-llama/Llama-3.1-405B-Instruct-Turbo', label: 'Llama 3.1 405B', provider: 'Together', color: '#f59e0b', cost: 'mid',
    desc: 'Open-source máximo · 128k · deep audit',
  },
]

const costColors: Record<string, string> = {
  free: '#10b981', low: '#00d4ff', mid: '#f59e0b', high: '#ef4444', premium: '#a855f7',
}
const costLabels: Record<string, string> = {
  free: 'grátis', low: '$', mid: '$$', high: '$$$', premium: '$$$$',
}

interface TopBarProps { title?: string }

const TopBar: React.FC<TopBarProps> = ({ title = 'Chat' }) => {
  const {
    currentModel, setCurrentModel,
    executionPanelVisible, setExecutionPanelVisible,
    clearMessages, isStreaming,
    liveToolEvents, activeToolCount,
    isSpeaking, voiceEnabled,
    activeFiles, workspaceName, workspacePath,
    projectMarkdown, userContext,
  } = useStore()

  const [showModels, setShowModels] = useState(false)

  const current       = MODELS.find((m) => m.id === currentModel) ?? MODELS[0]
  const runningTools  = liveToolEvents.filter((e) => e.status === 'running').length
  const isAuto        = current.id === 'auto'
  const hasContextDoc = !!(workspacePath && projectMarkdown[workspacePath])
  const hasUserCtx    = !!(userContext?.trim())

  return (
    <div
      className="flex-shrink-0 relative"
      style={{
        background: 'rgba(5,8,16,0.97)',
        borderBottom: isStreaming
          ? '1px solid rgba(0,212,255,0.35)'
          : '1px solid rgba(0,212,255,0.1)',
        boxShadow: isStreaming
          ? '0 1px 0 rgba(0,212,255,0.08), 0 2px 20px rgba(0,212,255,0.06)'
          : '0 1px 0 rgba(0,212,255,0.03)',
        transition: 'border-color 0.3s, box-shadow 0.3s',
      }}
    >
      {/* ── Streaming progress line ──────────────────────────────────────── */}
      {isStreaming && (
        <div
          className="absolute bottom-0 left-0 right-0 h-[2px] overflow-hidden"
          style={{ background: 'rgba(0,212,255,0.06)' }}
        >
          <div
            className="h-full"
            style={{
              background: 'linear-gradient(90deg, transparent, #00d4ff, #7c3aed, transparent)',
              animation: 'topbar-scan 2s linear infinite',
              width: '40%',
            }}
          />
        </div>
      )}

      <div className="flex items-center justify-between px-4 h-[52px]">
        {/* ── Left ────────────────────────────────────────────────────── */}
        <div className="flex items-center gap-2 min-w-0">

          {/* Title with V4 badge */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <span
              className="text-sm font-bold font-mono tracking-widest"
              style={{
                color: isStreaming ? '#00d4ff' : '#94a3b8',
                textShadow: isStreaming ? '0 0 12px rgba(0,212,255,0.5)' : 'none',
                transition: 'color 0.3s, text-shadow 0.3s',
              }}
            >
              {title.toUpperCase()}
            </span>
            <span
              className="text-[8px] font-mono px-1 rounded tracking-wider flex-shrink-0"
              style={{ background: 'rgba(0,212,255,0.08)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.15)' }}
            >
              V4
            </span>
          </div>

          {/* Streaming status badge */}
          {isStreaming && (
            <div
              className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono flex-shrink-0"
              style={{
                background: 'rgba(0,212,255,0.08)',
                border: '1px solid rgba(0,212,255,0.25)',
                color: '#00d4ff',
              }}
            >
              <Activity size={8} className="animate-pulse" />
              {runningTools > 0
                ? `${runningTools} tool${runningTools > 1 ? 's' : ''}`
                : 'pensando…'
              }
            </div>
          )}

          {!isStreaming && activeToolCount > 0 && (
            <span className="text-[10px] font-mono text-cyber-dim flex-shrink-0">
              {activeToolCount} ops
            </span>
          )}

          {/* Workspace pill */}
          {workspaceName && (
            <button
              onClick={() => setExecutionPanelVisible(true)}
              className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono transition-all hover:opacity-80 flex-shrink-0 max-w-[130px]"
              style={{
                background: 'rgba(0,212,255,0.06)',
                border: '1px solid rgba(0,212,255,0.13)',
                color: '#64748b',
              }}
              title={workspacePath ?? ''}
            >
              <FolderOpen size={9} className="text-cyber-cyan flex-shrink-0" />
              <span className="truncate">{workspaceName}</span>
              {activeFiles.length > 0 && (
                <span
                  className="ml-0.5 px-1 rounded-full text-[8px] font-bold flex-shrink-0"
                  style={{ background: 'rgba(0,212,255,0.15)', color: '#00d4ff' }}
                >
                  {activeFiles.length}
                </span>
              )}
            </button>
          )}

          {/* Context doc pill */}
          {hasContextDoc && (
            <button
              onClick={() => setExecutionPanelVisible(true)}
              className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono transition-all hover:opacity-80 flex-shrink-0"
              style={{
                background: 'rgba(124,58,237,0.08)',
                border: '1px solid rgba(124,58,237,0.2)',
                color: '#a78bfa',
              }}
              title="Contexto do projeto salvo"
            >
              <BookMarked size={9} />
              <span>Ctx</span>
            </button>
          )}

          {/* User context pill */}
          {hasUserCtx && (
            <div
              className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono flex-shrink-0"
              style={{
                background: 'rgba(29,158,117,0.08)',
                border: '1px solid rgba(29,158,117,0.2)',
                color: '#5DCAA5',
              }}
              title={userContext ?? ''}
            >
              <Terminal size={9} />
              <span>⚡ctx</span>
            </div>
          )}

          {/* Voice speaking indicator */}
          {voiceEnabled && isSpeaking && (
            <div
              className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono flex-shrink-0"
              style={{
                background: 'rgba(0,212,255,0.08)',
                border: '1px solid rgba(0,212,255,0.25)',
                color: '#00d4ff',
              }}
            >
              <Volume2 size={9} className="animate-pulse" />
              <span>Voz</span>
            </div>
          )}
        </div>

        {/* ── Right ───────────────────────────────────────────────────── */}
        <div className="flex items-center gap-2 flex-shrink-0">

          {/* Model selector */}
          <div className="relative">
            <button
              onClick={() => setShowModels((v) => !v)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono transition-all"
              style={{
                background: isAuto ? 'rgba(0,212,255,0.1)' : `${current.color}12`,
                border: `1px solid ${isAuto ? 'rgba(0,212,255,0.4)' : `${current.color}30`}`,
                color: current.color,
                boxShadow: isAuto ? '0 0 8px rgba(0,212,255,0.1)' : 'none',
              }}
            >
              {isAuto && <Zap size={10} />}
              <span>{current.label}</span>
              <ChevronDown size={11} style={{ color: '#64748b' }} />
            </button>

            {showModels && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setShowModels(false)} />
                <div
                  className="absolute top-full right-0 mt-1 z-50 rounded-xl overflow-hidden"
                  style={{
                    background: '#0a0f1e',
                    border: '1px solid rgba(0,212,255,0.18)',
                    boxShadow: '0 16px 48px rgba(0,0,0,0.8), 0 0 0 1px rgba(0,212,255,0.04)',
                    minWidth: 230,
                  }}
                >
                  {[
                    { key: 'Smart',     label: '⚡ Smart Routing' },
                    { key: 'xAI',       label: '✕ xAI · Grok' },
                    { key: 'Anthropic', label: '◈ Anthropic · Claude' },
                    { key: 'OpenAI',    label: '◉ OpenAI' },
                    { key: 'Groq',      label: '▸ Groq · Llama (grátis)' },
                    { key: 'Together',  label: '⬟ Together AI' },
                  ].map(({ key, label }) => {
                    const groupModels = MODELS.filter((m) => m.provider === key)
                    if (groupModels.length === 0) return null
                    return (
                      <div key={key}>
                        <div
                          className="px-3 pt-2.5 pb-1 text-[8px] font-mono uppercase tracking-[0.15em]"
                          style={{ color: '#1e293b' }}
                        >
                          {label}
                        </div>
                        {groupModels.map((m) => (
                          <button
                            key={m.id}
                            onClick={() => { setCurrentModel(m.id); setShowModels(false) }}
                            className="w-full text-left px-3 py-2 flex items-center gap-2.5 transition-colors hover:bg-white/[0.04]"
                            style={{
                              background: m.id === currentModel ? `${m.color}10` : 'transparent',
                            }}
                          >
                            <div
                              style={{
                                width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                                background: m.color,
                                boxShadow: m.id === currentModel ? `0 0 6px ${m.color}` : 'none',
                              }}
                            />
                            <div className="flex-1 min-w-0">
                              <span
                                className="text-[11px] font-mono block"
                                style={{ color: m.id === currentModel ? m.color : '#94a3b8' }}
                              >
                                {m.label}
                              </span>
                              {m.desc && (
                                <p className="text-[9px] truncate mt-0.5" style={{ color: '#334155' }}>
                                  {m.desc}
                                </p>
                              )}
                            </div>
                            <span
                              className="text-[9px] font-mono px-1.5 py-0.5 rounded flex-shrink-0"
                              style={{
                                background: `${costColors[m.cost]}15`,
                                color: costColors[m.cost],
                                border: `1px solid ${costColors[m.cost]}25`,
                              }}
                            >
                              {costLabels[m.cost]}
                            </span>
                          </button>
                        ))}
                      </div>
                    )
                  })}

                  <div
                    className="px-3 py-2.5 mt-1 space-y-0.5"
                    style={{ borderTop: '1px solid rgba(0,212,255,0.06)' }}
                  >
                    <p className="text-[8px] font-mono" style={{ color: '#1e293b' }}>AUTO ROUTING</p>
                    <p className="text-[9px]" style={{ color: '#334155' }}>🔴 Bounty/Segurança → Claude Sonnet</p>
                    <p className="text-[9px]" style={{ color: '#334155' }}>🟣 Web3/Código → Grok-3</p>
                    <p className="text-[9px]" style={{ color: '#334155' }}>🟢 Triage/Chat → Llama grátis</p>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Clear chat */}
          <button
            onClick={clearMessages}
            className="p-1.5 rounded-md transition-colors text-cyber-muted hover:text-cyber-red flex-shrink-0"
            style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.1)' }}
            title="Limpar chat"
          >
            <Trash2 size={13} />
          </button>

          {/* Toggle execution panel */}
          <button
            onClick={() => setExecutionPanelVisible(!executionPanelVisible)}
            className="p-1.5 rounded-md transition-all flex-shrink-0"
            style={{
              background: executionPanelVisible ? 'rgba(0,212,255,0.12)' : 'rgba(0,212,255,0.04)',
              border: `1px solid ${executionPanelVisible ? 'rgba(0,212,255,0.35)' : 'rgba(0,212,255,0.1)'}`,
              color: executionPanelVisible ? '#00d4ff' : '#64748b',
              boxShadow: executionPanelVisible ? '0 0 10px rgba(0,212,255,0.15)' : 'none',
            }}
            title={executionPanelVisible ? 'Ocultar painel de execução' : 'Mostrar painel de execução'}
          >
            <PanelRight size={13} />
          </button>
        </div>
      </div>
    </div>
  )
}

export default TopBar
