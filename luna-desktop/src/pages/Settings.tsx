/**
 * Luna Agent — Settings
 * Exclusive redesign: tab-based, branded, no raw API key chaos.
 * Sections: Geral · Provedores · Modelo · Workspace · Segurança · Bug Report · Sobre
 */
import React, { useState, useEffect, useCallback } from 'react'
import { useStore } from '@store/appStore'
import {
  Sliders, Cpu, Server, Shield, Bug, Info,
  CheckCircle, XCircle, Wifi, WifiOff,
  Eye, EyeOff, Trash2, Send, RefreshCw, Plus,
  AlertTriangle, AlertCircle, FolderOpen,
  ChevronRight, Circle, Volume2, Mic, User, LogOut, Copy, Check,
} from 'lucide-react'
import { signOut, supabase } from '@services/supabase'
import {
  getBugReports, sendBugReports, clearBugReports,
  deleteBugReport, type BugReport, type BugSeverity,
} from '../services/bugReport'
import { speak, stop, VOICES, type VoiceId } from '../services/voiceService'

// ── Tab definitions ────────────────────────────────────────────────────────────

type TabId = 'conta' | 'geral' | 'provedores' | 'modelo' | 'workspace' | 'voz' | 'seguranca' | 'bugs' | 'sobre'

const TABS: { id: TabId; label: string; icon: React.ElementType }[] = [
  { id: 'conta',      label: 'Minha Conta', icon: User      },
  { id: 'geral',      label: 'Geral',       icon: Sliders   },
  { id: 'provedores', label: 'Provedores', icon: Wifi      },
  { id: 'modelo',     label: 'Modelo IA',  icon: Cpu       },
  { id: 'workspace',  label: 'Workspace',  icon: FolderOpen},
  { id: 'voz',        label: 'Voz',        icon: Volume2   },
  { id: 'seguranca',  label: 'Segurança',  icon: Shield    },
  { id: 'bugs',       label: 'Bug Report', icon: Bug       },
  { id: 'sobre',      label: 'Sobre',      icon: Info      },
]

// ── Provider definitions ───────────────────────────────────────────────────────

const PROVIDERS = [
  {
    id: 'openai', name: 'OpenAI', icon: '⬡', color: '#10b981',
    placeholder: 'sk-proj-...', hint: 'Cria conta em platform.openai.com',
    models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'],
  },
  {
    id: 'claude', name: 'Anthropic Claude', icon: '◈', color: '#e040fb',
    placeholder: 'sk-ant-...', hint: 'Cria conta em console.anthropic.com',
    models: ['claude-sonnet-4-6', 'claude-opus-4-6', 'claude-haiku-4-5-20251001'],
  },
  {
    id: 'groq', name: 'Groq (Llama — grátis)', icon: '⚡', color: '#00d4ff',
    placeholder: 'gsk_...', hint: 'Grátis em console.groq.com',
    models: ['llama-3.3-70b', 'llama-3.1-8b'],
  },
  {
    id: 'grok', name: 'Grok (xAI)', icon: '✕', color: '#7c3aed',
    placeholder: 'xai-...', hint: 'Cria conta em console.x.ai',
    models: ['grok-3', 'grok-3-mini', 'grok-2-1212'],
  },
  {
    id: 'gemini', name: 'Google Gemini', icon: '◆', color: '#f59e0b',
    placeholder: 'AIza...', hint: 'Cria chave em aistudio.google.com',
    models: ['gemini-1.5-pro'],
  },
  {
    id: 'together', name: 'Together AI', icon: '⬟', color: '#f97316',
    placeholder: 'tgp_v1_...', hint: 'Cria conta em api.together.xyz',
    models: ['llama-3.1-405B'],
  },
]

const LOCALES = [
  { id: 'pt-BR', label: 'Português (BR)', flag: '🇧🇷' },
  { id: 'en-US', label: 'English (US)',   flag: '🇺🇸' },
]

// ── Severity badge ─────────────────────────────────────────────────────────────

const SEV_CONFIG: Record<BugSeverity, { label: string; color: string; icon: React.ElementType }> = {
  critical: { label: 'CRÍTICO',   color: '#ef4444', icon: XCircle       },
  error:    { label: 'ERRO',      color: '#f97316', icon: AlertCircle   },
  warning:  { label: 'AVISO',     color: '#f59e0b', icon: AlertTriangle },
  info:     { label: 'INFO',      color: '#00d4ff', icon: Info          },
}

function SeverityBadge({ sev }: { sev: BugSeverity }) {
  const cfg = SEV_CONFIG[sev]
  const Icon = cfg.icon
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono font-bold"
      style={{ background: `${cfg.color}18`, border: `1px solid ${cfg.color}40`, color: cfg.color }}
    >
      <Icon size={9} />
      {cfg.label}
    </span>
  )
}

// ── Generic section card ───────────────────────────────────────────────────────

function Card({ title, children, action }: {
  title: string; children: React.ReactNode; action?: React.ReactNode
}) {
  return (
    <div className="rounded-xl overflow-hidden"
      style={{ background: 'rgba(15,22,36,0.7)', border: '1px solid rgba(0,212,255,0.1)' }}>
      <div className="flex items-center justify-between px-5 py-3 border-b"
        style={{ borderColor: 'rgba(0,212,255,0.08)', background: 'rgba(0,212,255,0.03)' }}>
        <span className="text-[11px] font-mono text-cyber-muted uppercase tracking-[0.12em]">{title}</span>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB: GERAL
// ═══════════════════════════════════════════════════════════════════════════════
// ── Self-Reflection toggle (usado dentro de TabGeral) ─────────────────────────
function SelfReflectionToggle() {
  const { backendUrl, lunaApiToken } = useStore()
  const [enabled, setEnabled] = useState(false)
  const [saving, setSaving] = useState(false)

  const toggle = async (v: boolean) => {
    setSaving(true)
    setEnabled(v)
    try {
      await fetch(`${backendUrl}/api/config`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(lunaApiToken ? { 'X-Luna-Token': lunaApiToken } : {}),
        },
        body: JSON.stringify({ reflection_enabled: v }),
      })
    } catch { /* silent */ } finally {
      setSaving(false)
    }
  }

  return (
    <label className="flex items-start gap-3 cursor-pointer group" onClick={() => toggle(!enabled)}>
      <input
        type="checkbox"
        checked={enabled}
        onChange={() => {}}
        disabled={saving}
        className="mt-0.5 w-3.5 h-3.5 accent-cyber-cyan"
      />
      <div>
        <p className="text-[12px] font-semibold text-cyber-text group-hover:text-cyber-cyan transition-colors">
          Self-Reflection Loop
          {saving && <span className="text-[9px] font-mono text-cyber-dim ml-2">salvando...</span>}
        </p>
        <p className="text-[10px] text-cyber-dim mt-0.5">
          Execute → Critique → Fix (via Groq rápido). Luna revisa a própria resposta antes de entregar. +qualidade, +latência ~2s.
        </p>
      </div>
    </label>
  )
}

function TabGeral() {
  const { locale, setLocale, backendStatus, zeroCloudMode, setZeroCloudMode, backendUrl, lunaApiToken } = useStore()
  const [ollamaStatus, setOllamaStatus] = useState<{ running: boolean; models: Array<{name: string; size_gb: number}> } | null>(null)
  const [ollamaLoading, setOllamaLoading] = useState(false)

  // Carrega status do Ollama ao montar
  useEffect(() => {
    fetch(`${backendUrl}/api/providers/ollama/status`, {
      headers: lunaApiToken ? { 'X-Luna-Token': lunaApiToken } : {},
      signal: AbortSignal.timeout(3000),
    })
      .then(r => r.json())
      .then(d => setOllamaStatus(d))
      .catch(() => setOllamaStatus({ running: false, models: [] }))
  }, [backendUrl, lunaApiToken])

  const toggleZeroCloud = async (v: boolean) => {
    setZeroCloudMode(v)
    // Sincroniza com backend
    try {
      await fetch(`${backendUrl}/api/config`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(lunaApiToken ? { 'X-Luna-Token': lunaApiToken } : {}),
        },
        body: JSON.stringify({ zero_cloud_mode: v }),
      })
    } catch (e) {
      console.warn('[ZeroCloud] sync falhou:', e)
    }
  }

  const handlePullModel = async (model: string) => {
    setOllamaLoading(true)
    try {
      await fetch(`${backendUrl}/api/providers/ollama/pull`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(lunaApiToken ? { 'X-Luna-Token': lunaApiToken } : {}),
        },
        body: JSON.stringify({ model }),
      })
    } finally {
      setOllamaLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card title="Identidade do Agente">
        <div className="flex items-center gap-4 mb-5">
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center text-3xl flex-shrink-0"
            style={{ background: 'linear-gradient(135deg,#7c3aed,#00d4ff)', boxShadow: '0 0 24px rgba(124,58,237,0.5)' }}
          >
            🌙
          </div>
          <div>
            <h2 className="text-base font-bold text-cyber-cyan" style={{ textShadow: '0 0 10px rgba(0,212,255,0.6)' }}>
              LUNA
            </h2>
            <p className="text-[11px] font-mono text-cyber-muted">Elite Autonomous AI Agent · v4.0.0</p>
            <div className="flex items-center gap-1.5 mt-1">
              <Circle
                size={7}
                className={backendStatus.connected ? 'text-cyber-green fill-cyber-green' : 'text-cyber-red fill-cyber-red'}
              />
              <span className="text-[10px] font-mono text-cyber-dim">
                {backendStatus.connected
                  ? `Backend online · ${backendStatus.model} · v${backendStatus.version}`
                  : 'Backend offline — reinicie o servidor'}
              </span>
            </div>
          </div>
        </div>
        <p className="text-[11px] font-mono text-cyber-dim leading-relaxed">
          Luna é uma agente autônoma especializada em segurança Web3, desenvolvimento Solana/Anchor,
          bug bounty (Immunefi, HackerOne) e IA aplicada. Opera em modo Cowork autônomo com acesso
          ao sistema de arquivos e à internet.
        </p>
      </Card>

      <Card title="Idioma da Interface">
        <p className="text-[11px] text-cyber-dim font-mono mb-3">
          Selecione o idioma padrão da interface e das respostas de Luna.
        </p>
        <div className="flex gap-2">
          {LOCALES.map(({ id, label, flag }) => (
            <button
              key={id}
              onClick={() => setLocale(id)}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-[12px] font-mono transition-all"
              style={locale === id
                ? { background: 'rgba(0,212,255,0.14)', border: '1px solid rgba(0,212,255,0.5)', color: '#00d4ff' }
                : { background: 'rgba(0,212,255,0.03)', border: '1px solid rgba(0,212,255,0.1)', color: '#64748b' }}
            >
              <span className="text-base">{flag}</span>
              <span>{label}</span>
            </button>
          ))}
        </div>
      </Card>

      <Card title="Modo de Operação">
        <div className="space-y-3">
          {[
            { label: 'Modo Cowork Autônomo',   desc: 'Luna executa tarefas sem pedir confirmação a cada passo',    on: true  },
            { label: 'Auto-iniciar Backend',    desc: 'Inicia o servidor Python automaticamente com o app',         on: true  },
            { label: 'Notificações de Tarefa',  desc: 'Notifica quando Luna conclui uma operação longa',            on: true  },
            { label: 'Histórico Persistente',   desc: 'Mantém o histórico de conversas entre sessões',              on: false },
          ].map(({ label, desc, on }) => (
            <label key={label} className="flex items-start gap-3 cursor-pointer group">
              <input type="checkbox" defaultChecked={on} className="mt-0.5 w-3.5 h-3.5 accent-cyber-cyan" />
              <div>
                <p className="text-[12px] font-semibold text-cyber-text group-hover:text-cyber-cyan transition-colors">{label}</p>
                <p className="text-[10px] text-cyber-dim mt-0.5">{desc}</p>
              </div>
            </label>
          ))}
          {/* Self-Reflection toggle */}
          <SelfReflectionToggle />
        </div>
      </Card>

      {/* ── Zero-Cloud Mode ─────────────────────────────────────────────────── */}
      <Card title="🦙 Modo Zero-Cloud (Ollama Local)">
        {/* Toggle principal */}
        <div
          className="flex items-center justify-between p-3 rounded-xl mb-3"
          style={{
            background: zeroCloudMode
              ? 'rgba(124,58,237,0.12)'
              : 'rgba(0,212,255,0.04)',
            border: zeroCloudMode
              ? '1px solid rgba(124,58,237,0.4)'
              : '1px solid rgba(0,212,255,0.1)',
          }}
        >
          <div>
            <p className="text-[12px] font-semibold" style={{ color: zeroCloudMode ? '#a78bfa' : '#94a3b8' }}>
              {zeroCloudMode ? '🔒 Modo Zero-Cloud ATIVO' : 'Modo Zero-Cloud'}
            </p>
            <p className="text-[10px] font-mono text-cyber-dim mt-0.5">
              {zeroCloudMode
                ? 'Todas as chamadas vão para Ollama local — nenhum dado sai do dispositivo'
                : 'Quando ativo, força todos os modelos para Ollama. Sem internet necessária.'}
            </p>
          </div>
          <button
            onClick={() => toggleZeroCloud(!zeroCloudMode)}
            className="relative w-11 h-6 rounded-full transition-all flex-shrink-0"
            style={{
              background: zeroCloudMode ? '#7c3aed' : 'rgba(0,212,255,0.15)',
              border: zeroCloudMode ? '1px solid #7c3aed' : '1px solid rgba(0,212,255,0.2)',
            }}
          >
            <span
              className="absolute top-0.5 w-5 h-5 rounded-full transition-all"
              style={{
                background: zeroCloudMode ? '#fff' : '#64748b',
                left: zeroCloudMode ? 'calc(100% - 22px)' : '2px',
                boxShadow: zeroCloudMode ? '0 0 8px rgba(124,58,237,0.6)' : 'none',
              }}
            />
          </button>
        </div>

        {/* Status do Ollama */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 mb-2">
            <div
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{
                background: ollamaStatus?.running ? '#22c55e' : '#ef4444',
                boxShadow: ollamaStatus?.running ? '0 0 6px #22c55e' : 'none',
              }}
            />
            <span className="text-[11px] font-mono text-cyber-muted">
              {ollamaStatus === null
                ? 'Verificando Ollama...'
                : ollamaStatus.running
                  ? `Ollama rodando — ${ollamaStatus.models.length} modelo(s) instalado(s)`
                  : 'Ollama não detectado — instale em ollama.ai'}
            </span>
          </div>

          {/* Modelos instalados */}
          {ollamaStatus?.running && ollamaStatus.models.length > 0 && (
            <div className="space-y-1">
              {ollamaStatus.models.map(m => (
                <div
                  key={m.name}
                  className="flex items-center justify-between px-2.5 py-1.5 rounded-lg"
                  style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.08)' }}
                >
                  <span className="text-[11px] font-mono text-cyber-cyan">🦙 {m.name}</span>
                  <span className="text-[10px] font-mono text-cyber-dim">{m.size_gb} GB</span>
                </div>
              ))}
            </div>
          )}

          {/* Modelos recomendados para baixar */}
          {ollamaStatus?.running && (
            <div className="mt-3">
              <p className="text-[10px] font-mono text-cyber-dim mb-1.5">Modelos recomendados:</p>
              <div className="flex flex-wrap gap-1.5">
                {['llama3.3:70b', 'qwen2.5:72b', 'phi4', 'deepseek-r1'].map(m => {
                  const installed = ollamaStatus.models.some(installed => installed.name === m || installed.name.startsWith(m.split(':')[0]))
                  return (
                    <button
                      key={m}
                      onClick={() => !installed && handlePullModel(m)}
                      disabled={installed || ollamaLoading}
                      className="px-2 py-1 rounded text-[10px] font-mono transition-all"
                      style={{
                        background: installed ? 'rgba(34,197,94,0.1)' : 'rgba(0,212,255,0.06)',
                        border: installed ? '1px solid rgba(34,197,94,0.3)' : '1px solid rgba(0,212,255,0.15)',
                        color: installed ? '#22c55e' : '#00d4ff',
                        cursor: installed ? 'default' : 'pointer',
                      }}
                    >
                      {installed ? '✓ ' : '↓ '}{m}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {!ollamaStatus?.running && (
            <div
              className="p-2.5 rounded-lg text-[10px] font-mono text-cyber-dim mt-2"
              style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.15)' }}
            >
              Para usar o modo local:<br />
              1. Instale em <span className="text-cyber-cyan">ollama.ai</span><br />
              2. Execute: <span className="text-cyber-cyan">ollama pull llama3.3:70b</span><br />
              3. Reabra as Settings — Ollama será detectado automaticamente
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB: PROVEDORES
// ═══════════════════════════════════════════════════════════════════════════════
function TabProvedores() {
  const { setApiKey, lunaApiToken, backendUrl } = useStore()
  const [showKeys, setShowKeys]     = useState<Record<string, boolean>>({})
  const [localKeys, setLocalKeys]   = useState<Record<string, string>>({})
  const [connected, setConnected]   = useState<Record<string, boolean>>({})
  const [saved, setSaved]           = useState<string | null>(null)
  const [loading, setLoading]       = useState(true)

  const keysAPI = window.electronAPI?.keys

  // Carrega keys do safeStorage na montagem do componente
  useEffect(() => {
    const load = async () => {
      if (!keysAPI) {
        setLoading(false)
        return
      }
      const list = await keysAPI.list()
      const loadedConnected: Record<string, boolean> = {}
      const loadedKeys: Record<string, string> = {}
      for (const name of list) {
        const res = await keysAPI.get(name)
        if (res?.value) {
          loadedConnected[name] = true
          loadedKeys[name] = res.value
          // Mantém o store em sync (para uso em Chat.tsx e outros)
          setApiKey(name, res.value)
        }
      }
      setConnected(loadedConnected)
      setLocalKeys(loadedKeys)
      setLoading(false)
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const toggle = (id: string) => setShowKeys(p => ({ ...p, [id]: !p[id] }))

  const save = async (id: string) => {
    const val = (localKeys[id] ?? '').trim()
    if (!val) return

    // 1. Salva no safeStorage
    if (keysAPI) {
      const res = await keysAPI.set(id, val)
      if (!res.ok) {
        console.warn('[Settings] safeStorage write failed:', res.error)
      }
    }

    // 2. Atualiza o store local
    setApiKey(id, val)
    setConnected(p => ({ ...p, [id]: true }))

    // 3. Envia ao backend em tempo real (se token disponível)
    if (lunaApiToken) {
      fetch(`${backendUrl}/api/config/keys`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Luna-Token': lunaApiToken,
        },
        body: JSON.stringify({ keys: { [id]: val } }),
      }).catch(e => console.warn('[Settings] backend key sync failed:', e))
    }

    setSaved(id)
    setTimeout(() => setSaved(null), 2500)
  }

  const clear = async (id: string) => {
    // 1. Remove do safeStorage
    if (keysAPI) await keysAPI.delete(id)
    // 2. Limpa store e estado local
    setLocalKeys(p => ({ ...p, [id]: '' }))
    setApiKey(id, '')
    setConnected(p => ({ ...p, [id]: false }))
    // 3. Remove do backend
    if (lunaApiToken) {
      fetch(`${backendUrl}/api/config/keys/${id}`, {
        method: 'DELETE',
        headers: { 'X-Luna-Token': lunaApiToken },
      }).catch(() => {})
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="w-5 h-5 rounded-full border-2 border-cyber-cyan border-t-transparent animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-[11px] font-mono text-cyber-dim mb-4 leading-relaxed">
        Conecte os provedores de IA que Luna usará. Adicione pelo menos um para ativar o chat.
        As chaves são armazenadas com {keysAPI ? 'criptografia do sistema operacional (Keychain/DPAPI)' : 'armazenamento local no dispositivo'} — nunca enviadas para servidores externos.
      </p>

      {PROVIDERS.map(({ id, name, icon, color, placeholder, hint, models }) => {
        const key      = localKeys[id] ?? ''
        const isConn   = connected[id] ?? false
        const isSaved  = saved === id

        return (
          <div
            key={id}
            className="rounded-xl overflow-hidden transition-all"
            style={{
              border: isConn
                ? `1px solid ${color}35`
                : '1px solid rgba(0,212,255,0.08)',
              background: isConn
                ? `rgba(15,22,36,0.8)`
                : 'rgba(15,22,36,0.5)',
            }}
          >
            {/* Provider header */}
            <div
              className="flex items-center gap-3 px-4 py-3"
              style={{ borderBottom: '1px solid rgba(0,212,255,0.06)' }}
            >
              <span className="text-lg" style={{ color }}>{icon}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[12px] font-semibold text-cyber-text">{name}</span>
                  {isConn ? (
                    <span
                      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono"
                      style={{ background: `${color}18`, border: `1px solid ${color}40`, color }}
                    >
                      <CheckCircle size={8} /> Conectado
                    </span>
                  ) : (
                    <span className="text-[9px] font-mono text-cyber-dim px-1.5 py-0.5 rounded"
                      style={{ border: '1px solid rgba(0,212,255,0.1)' }}>
                      Não configurado
                    </span>
                  )}
                </div>
                <p className="text-[9px] font-mono text-cyber-dim mt-0.5">{models.join(' · ')}</p>
              </div>
              {isConn && (
                <button
                  onClick={() => clear(id)}
                  className="text-cyber-dim hover:text-cyber-red transition-colors"
                  title="Remover chave"
                >
                  <Trash2 size={13} />
                </button>
              )}
            </div>

            {/* Key input */}
            <div className="px-4 py-3">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <input
                    type={showKeys[id] ? 'text' : 'password'}
                    value={key}
                    onChange={e => setLocalKeys(p => ({ ...p, [id]: e.target.value }))}
                    onKeyDown={e => e.key === 'Enter' && save(id)}
                    placeholder={isConn ? '••••••••••••••••••••' : placeholder}
                    className="input-cyber w-full text-[11px] font-mono pr-8"
                    style={{ borderColor: isConn ? `${color}30` : undefined }}
                  />
                  <button
                    onClick={() => toggle(id)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-cyber-dim hover:text-cyber-muted transition-colors"
                  >
                    {showKeys[id] ? <EyeOff size={12} /> : <Eye size={12} />}
                  </button>
                </div>
                <button
                  onClick={() => save(id)}
                  disabled={!key.trim()}
                  className="px-3 rounded-lg text-[11px] font-mono font-semibold transition-all flex items-center gap-1.5"
                  style={{
                    background: key.trim() ? `${color}18` : 'rgba(0,212,255,0.04)',
                    border: key.trim() ? `1px solid ${color}45` : '1px solid rgba(0,212,255,0.1)',
                    color: key.trim() ? color : '#64748b',
                  }}
                >
                  {isSaved ? <CheckCircle size={11} /> : <Plus size={11} />}
                  {isSaved ? 'Salvo!' : 'Salvar'}
                </button>
              </div>
              <p className="text-[9px] font-mono text-cyber-dim mt-1.5">
                💡 {hint}
              </p>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB: MODELO IA
// ═══════════════════════════════════════════════════════════════════════════════
function TabModelo() {
  const { currentModel, setCurrentModel, temperature, setTemperature, maxTokens, setMaxTokens } = useStore()
  const [localTemp, setLocalTemp]     = useState(temperature ?? 0.7)
  const [localTokens, setLocalTokens] = useState(maxTokens ?? 4096)

  const MODELS = [
    { value: 'auto',                    label: 'Auto (Roteamento Inteligente)', provider: 'Luna',      cost: '⚡ baixo',   desc: 'Seleciona o melhor modelo por tipo de tarefa automaticamente' },
    { value: 'grok-3',                  label: 'Grok-3',                        provider: 'xAI',       cost: '💰 alto',    desc: 'Modelo flagship do xAI — excelente para raciocínio e código' },
    { value: 'grok-3-mini',             label: 'Grok-3 Mini',                   provider: 'xAI',       cost: '💰 médio',   desc: 'Versão eficiente do Grok-3 — velocidade e custo balanceados' },
    { value: 'claude-sonnet-4-6',       label: 'Claude Sonnet 4.6',             provider: 'Anthropic', cost: '💰 alto',    desc: 'Excelente para security research, análise de contratos e código' },
    { value: 'claude-opus-4-6',         label: 'Claude Opus 4.6',               provider: 'Anthropic', cost: '💰 premium', desc: 'Modelo mais poderoso da Anthropic — raciocínio profundo' },
    { value: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5',            provider: 'Anthropic', cost: '💰 baixo',   desc: 'Ultra-rápido para tarefas simples — custo mínimo' },
    { value: 'gpt-4o',                  label: 'GPT-4o',                        provider: 'OpenAI',    cost: '💰 alto',    desc: 'Melhor para código complexo e raciocínio geral' },
    { value: 'gpt-4o-mini',             label: 'GPT-4o Mini',                   provider: 'OpenAI',    cost: '💰 médio',   desc: 'Rápido e barato para tarefas simples' },
    { value: 'llama-3.3-70b',           label: 'Llama 3.3 70B',                 provider: 'Groq',      cost: '🆓 grátis',  desc: 'Rápido e grátis para consultas gerais' },
    { value: 'llama-3.1-8b',            label: 'Llama 3.1 8B',                  provider: 'Groq',      cost: '🆓 grátis',  desc: 'Ultra-rápido para respostas curtas' },
    { value: 'llama-3.1-405b',          label: 'Llama 3.1 405B',                provider: 'Together',  cost: '💰 médio',   desc: 'Modelo de código aberto mais potente disponível' },
  ]

  return (
    <div className="space-y-4">
      <Card title="Modelo Padrão">
        <div className="space-y-2">
          {MODELS.map(({ value, label, provider, cost, desc }) => (
            <label
              key={value}
              className="flex items-start gap-3 p-3 rounded-lg cursor-pointer transition-all"
              style={currentModel === value
                ? { background: 'rgba(0,212,255,0.08)', border: '1px solid rgba(0,212,255,0.3)' }
                : { background: 'rgba(0,212,255,0.02)', border: '1px solid rgba(0,212,255,0.06)' }}
            >
              <input
                type="radio"
                name="model"
                value={value}
                checked={currentModel === value}
                onChange={() => setCurrentModel(value)}
                className="mt-0.5 accent-cyber-cyan"
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`text-[12px] font-semibold ${currentModel === value ? 'text-cyber-cyan' : 'text-cyber-text'}`}>
                    {label}
                  </span>
                  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded"
                    style={{ background: 'rgba(0,212,255,0.06)', border: '1px solid rgba(0,212,255,0.12)', color: '#64748b' }}>
                    {provider}
                  </span>
                  <span className="text-[9px] font-mono text-cyber-dim">{cost}</span>
                </div>
                <p className="text-[10px] text-cyber-dim mt-0.5">{desc}</p>
              </div>
              {currentModel === value && <CheckCircle size={13} className="text-cyber-cyan flex-shrink-0 mt-0.5" />}
            </label>
          ))}
        </div>
      </Card>

      <Card title="Parâmetros de Geração">
        <div className="space-y-5">
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-[11px] font-mono text-cyber-muted">Temperature</label>
              <span className="text-[12px] font-mono font-bold text-cyber-cyan">{localTemp.toFixed(1)}</span>
            </div>
            <input type="range" min="0" max="1" step="0.1"
              value={localTemp}
              onChange={e => { const v = parseFloat(e.target.value); setLocalTemp(v); setTemperature(v) }}
              className="w-full accent-cyber-cyan"
            />
            <div className="flex justify-between text-[9px] font-mono text-cyber-dim mt-1">
              <span>🎯 Focado (0.0)</span><span>🎨 Criativo (1.0)</span>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-[11px] font-mono text-cyber-muted">Max Tokens</label>
              <span className="text-[12px] font-mono font-bold text-cyber-cyan">{localTokens.toLocaleString()}</span>
            </div>
            <input type="range" min="512" max="32768" step="512"
              value={localTokens}
              onChange={e => { const v = parseInt(e.target.value); setLocalTokens(v); setMaxTokens(v) }}
              className="w-full accent-cyber-cyan"
            />
            <div className="flex justify-between text-[9px] font-mono text-cyber-dim mt-1">
              <span>512 tokens</span><span>32k tokens</span>
            </div>
          </div>
        </div>
      </Card>

      <Card title="Roteamento Automático">
        <div className="space-y-2 font-mono">
          {[
            { trigger: 'security · blockchain · audit · bounty',  model: 'Claude 3.5 Sonnet', icon: '🔐' },
            { trigger: 'implement · build · refactor · debug',    model: 'GPT-4o',            icon: '💻' },
            { trigger: 'mensagem curta (< 25 palavras)',           model: 'Llama 3.3 70B',     icon: '⚡' },
            { trigger: 'padrão',                                   model: 'Melhor disponível', icon: '🤖' },
          ].map(({ trigger, model, icon }) => (
            <div key={trigger} className="flex items-center gap-3 px-3 py-2 rounded"
              style={{ background: 'rgba(0,212,255,0.03)', border: '1px solid rgba(0,212,255,0.07)' }}>
              <span className="text-sm">{icon}</span>
              <div className="flex-1 min-w-0">
                <p className="text-[10px] text-cyber-dim truncate">{trigger}</p>
              </div>
              <ChevronRight size={10} className="text-cyber-dim" />
              <span className="text-[10px] text-cyber-cyan font-semibold flex-shrink-0">{model}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB: WORKSPACE
// ═══════════════════════════════════════════════════════════════════════════════
function TabWorkspace() {
  const { workspacePath, workspaceName, setWorkspace, clearWorkspace, backendUrl, setBackendUrl } = useStore()
  const [localUrl, setLocalUrl] = useState(backendUrl)
  const [urlSaved, setUrlSaved] = useState(false)
  const api = window.electronAPI?.workspace

  const handleSelect = async () => {
    if (!api) return
    const result = await api.openFolderDialog()
    if (!result.canceled && result.filePaths[0]) {
      const p = result.filePaths[0]
      setWorkspace(p, p.split(/[\\/]/).filter(Boolean).pop() ?? p)
    }
  }

  const saveUrl = () => {
    setBackendUrl(localUrl)
    setUrlSaved(true)
    setTimeout(() => setUrlSaved(false), 2500)
  }

  return (
    <div className="space-y-4">
      <Card title="Pasta de Trabalho">
        <p className="text-[11px] text-cyber-dim font-mono mb-4 leading-relaxed">
          Luna opera dentro desta pasta. Ela pode ler, criar e editar arquivos aqui.
          Selecione um repositório ou pasta de projeto para trabalho autônomo.
        </p>
        {workspacePath ? (
          <div className="mb-4 p-3 rounded-lg flex items-start gap-3"
            style={{ background: 'rgba(16,185,129,0.07)', border: '1px solid rgba(16,185,129,0.25)' }}>
            <CheckCircle size={14} className="text-cyber-green mt-0.5 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-[11px] font-semibold text-cyber-green">{workspaceName}</p>
              <p className="text-[9px] font-mono text-cyber-dim truncate mt-0.5">{workspacePath}</p>
            </div>
            <button onClick={clearWorkspace} className="text-cyber-dim hover:text-cyber-red transition-colors">
              <Trash2 size={13} />
            </button>
          </div>
        ) : (
          <div className="mb-4 p-3 rounded-lg flex items-center gap-3"
            style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.12)' }}>
            <WifiOff size={14} className="text-cyber-muted" />
            <p className="text-[11px] font-mono text-cyber-dim">Nenhuma pasta selecionada</p>
          </div>
        )}
        <div className="flex gap-2">
          <button onClick={handleSelect}
            className="btn-cyber flex items-center gap-2 flex-1 justify-center">
            <FolderOpen size={13} />
            {workspacePath ? 'Trocar pasta' : 'Selecionar pasta'}
          </button>
        </div>
      </Card>

      <Card title="Permissões de Arquivo">
        <div className="space-y-3">
          {[
            { label: 'Leitura de arquivos',      desc: 'Luna pode ler arquivos do workspace',          on: true,  locked: true  },
            { label: 'Escrita de arquivos',       desc: 'Luna pode criar e editar arquivos',            on: true,  locked: false },
            { label: 'Criar diretórios',          desc: 'Luna pode criar novas pastas',                 on: true,  locked: false },
            { label: 'Deletar arquivos',          desc: 'Luna pode excluir arquivos (pede confirmação)',on: false, locked: false },
            { label: 'Executar scripts',          desc: 'Luna pode rodar scripts Python/Node no backend',on: false,locked: false },
          ].map(({ label, desc, on, locked }) => (
            <label key={label} className={`flex items-start gap-3 ${locked ? 'opacity-60' : 'cursor-pointer'} group`}>
              <input type="checkbox" defaultChecked={on} disabled={locked} className="mt-0.5 w-3.5 h-3.5 accent-cyber-cyan" />
              <div>
                <p className="text-[12px] font-semibold text-cyber-text group-hover:text-cyber-cyan transition-colors">
                  {label} {locked && <span className="text-[9px] text-cyber-dim ml-1">(sempre ativo)</span>}
                </p>
                <p className="text-[10px] text-cyber-dim mt-0.5">{desc}</p>
              </div>
            </label>
          ))}
        </div>
      </Card>

      <Card title="Servidor Backend">
        <div>
          <label className="block text-[11px] font-mono text-cyber-muted mb-2">URL do Backend (FastAPI)</label>
          <div className="flex gap-2">
            <input
              type="text" value={localUrl}
              onChange={e => setLocalUrl(e.target.value)}
              className="input-cyber text-[12px] font-mono flex-1"
              placeholder="http://localhost:8000"
            />
            <button onClick={saveUrl}
              className="px-3 rounded-lg text-[11px] font-mono font-semibold flex items-center gap-1.5 transition-all"
              style={{
                background: urlSaved ? 'rgba(16,185,129,0.1)' : 'rgba(0,212,255,0.08)',
                border: urlSaved ? '1px solid rgba(16,185,129,0.4)' : '1px solid rgba(0,212,255,0.25)',
                color: urlSaved ? '#10b981' : '#00d4ff',
              }}>
              {urlSaved ? <CheckCircle size={11} /> : <Server size={11} />}
              {urlSaved ? 'Salvo' : 'Salvar'}
            </button>
          </div>
          <p className="mt-1.5 text-[9px] text-cyber-dim font-mono">
            Padrão: http://localhost:8000 — altere apenas se usar backend remoto ou porta diferente
          </p>
        </div>
      </Card>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB: VOZ
// ═══════════════════════════════════════════════════════════════════════════════
function TabVoz() {
  const {
    voiceEnabled, setVoiceEnabled,
    voiceId, setVoiceId,
    voiceSpeed, setVoiceSpeed,
    voiceModel, setVoiceModel,
    backendUrl,
  } = useStore()

  const [testing, setTesting]     = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    const res = await speak(
      'Olá! Eu sou Luna, sua agente autônoma de IA. Estou pronta para trabalhar com você.',
      backendUrl,
      { voice: voiceId as VoiceId, speed: voiceSpeed, model: voiceModel as any },
    )
    setTesting(false)
    setTestResult(res.ok
      ? { ok: true, msg: `Voz "${voiceId}" reproduzida com sucesso (${res.duration ?? 0}ms)` }
      : { ok: false, msg: res.error ?? 'Erro desconhecido' }
    )
    setTimeout(() => setTestResult(null), 5000)
  }

  const handleStop = () => {
    stop()
    setTesting(false)
  }

  const VOICE_GROUPS = [
    {
      label: 'Vozes Femininas',
      voices: VOICES.filter(v => v.feminine),
    },
    {
      label: 'Vozes Masculinas / Neutras',
      voices: VOICES.filter(v => !v.feminine),
    },
  ]

  return (
    <div className="space-y-4">
      {/* Auto-speak toggle */}
      <Card title="Resposta por Voz">
        <div className="space-y-4">
          <label className="flex items-start gap-3 cursor-pointer group">
            <div className="relative mt-0.5 flex-shrink-0">
              <input
                type="checkbox"
                className="sr-only"
                checked={voiceEnabled}
                onChange={e => setVoiceEnabled(e.target.checked)}
              />
              <div
                className="w-9 h-5 rounded-full transition-all duration-200 pointer-events-none"
                style={{
                  background: voiceEnabled
                    ? 'linear-gradient(90deg, #7c3aed, #00d4ff)'
                    : 'rgba(0,212,255,0.1)',
                  border: voiceEnabled ? 'none' : '1px solid rgba(0,212,255,0.2)',
                  boxShadow: voiceEnabled ? '0 0 12px rgba(0,212,255,0.4)' : 'none',
                }}
              >
                <div
                  className="absolute top-0.5 w-4 h-4 rounded-full transition-all duration-200"
                  style={{
                    left: voiceEnabled ? '18px' : '2px',
                    background: voiceEnabled ? '#fff' : 'rgba(0,212,255,0.5)',
                  }}
                />
              </div>
            </div>
            <div>
              <p className="text-[12px] font-semibold text-cyber-text group-hover:text-cyber-cyan transition-colors">
                Auto-falar respostas de Luna
              </p>
              <p className="text-[10px] text-cyber-dim mt-0.5">
                Luna lerá automaticamente cada resposta ao terminar de escrever.
                Ideal para uso mãos-livres.
              </p>
            </div>
          </label>

          <div className="text-[10px] font-mono text-cyber-dim px-3 py-2 rounded-lg"
            style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.1)' }}>
            💡 Use o ícone <Volume2 size={10} className="inline" /> em cada mensagem para ouvir individualmente,
            mesmo com auto-falar desativado.
          </div>
        </div>
      </Card>

      {/* Voice selection */}
      <Card title="Voz de Luna">
        {VOICE_GROUPS.map(({ label, voices }) => (
          <div key={label} className="mb-4">
            <p className="text-[9px] font-mono text-cyber-dim uppercase tracking-wider mb-2">{label}</p>
            <div className="space-y-1.5">
              {voices.map(({ id, label: vLabel, style, feminine }) => (
                <button
                  key={id}
                  onClick={() => setVoiceId(id)}
                  className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all"
                  style={voiceId === id
                    ? { background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.4)' }
                    : { background: 'rgba(0,212,255,0.02)', border: '1px solid rgba(0,212,255,0.07)' }}
                >
                  <div
                    className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-sm"
                    style={{
                      background: voiceId === id
                        ? 'linear-gradient(135deg,#7c3aed,#00d4ff)'
                        : 'rgba(0,212,255,0.08)',
                    }}
                  >
                    {feminine ? '♀' : '♂'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-[12px] font-semibold ${voiceId === id ? 'text-cyber-cyan' : 'text-cyber-text'}`}>
                        {vLabel}
                      </span>
                      {id === 'nova' && (
                        <span className="text-[8px] font-mono px-1 py-0.5 rounded"
                          style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.3)', color: '#00d4ff' }}>
                          PADRÃO
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] text-cyber-dim">{style}</p>
                  </div>
                  {voiceId === id && <CheckCircle size={13} className="text-cyber-cyan flex-shrink-0" />}
                </button>
              ))}
            </div>
          </div>
        ))}
      </Card>

      {/* Speed + Model */}
      <Card title="Parâmetros de Áudio">
        <div className="space-y-5">
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-[11px] font-mono text-cyber-muted">Velocidade de Fala</label>
              <span className="text-[12px] font-mono font-bold text-cyber-cyan">{voiceSpeed.toFixed(1)}x</span>
            </div>
            <input
              type="range" min="0.5" max="2.0" step="0.1"
              value={voiceSpeed}
              onChange={e => setVoiceSpeed(parseFloat(e.target.value))}
              className="w-full accent-cyber-cyan"
            />
            <div className="flex justify-between text-[9px] font-mono text-cyber-dim mt-1">
              <span>🐢 Lento (0.5x)</span>
              <span>1.0x Normal</span>
              <span>⚡ Rápido (2.0x)</span>
            </div>
          </div>

          <div>
            <label className="block text-[11px] font-mono text-cyber-muted mb-2">Modelo TTS</label>
            <div className="flex gap-2">
              {[
                { id: 'tts-1',    label: 'TTS-1',    desc: 'Mais rápido, menor latência' },
                { id: 'tts-1-hd', label: 'TTS-1 HD', desc: 'Maior qualidade de áudio' },
              ].map(({ id, label: mLabel, desc }) => (
                <button
                  key={id}
                  onClick={() => setVoiceModel(id)}
                  className="flex-1 p-2.5 rounded-lg text-center transition-all"
                  style={voiceModel === id
                    ? { background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.4)' }
                    : { background: 'rgba(0,212,255,0.02)', border: '1px solid rgba(0,212,255,0.08)' }}
                >
                  <p className={`text-[11px] font-semibold ${voiceModel === id ? 'text-cyber-cyan' : 'text-cyber-text'}`}>
                    {mLabel}
                  </p>
                  <p className="text-[9px] font-mono text-cyber-dim mt-0.5">{desc}</p>
                </button>
              ))}
            </div>
          </div>
        </div>
      </Card>

      {/* Test */}
      <Card title="Testar Voz">
        <p className="text-[11px] font-mono text-cyber-dim mb-4">
          Clique para ouvir como Luna vai soar com as configurações atuais.
          O backend precisa estar online com chave OpenAI configurada.
        </p>

        {testResult && (
          <div
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-[11px] font-mono mb-3"
            style={{
              background: testResult.ok ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
              border: `1px solid ${testResult.ok ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`,
              color: testResult.ok ? '#10b981' : '#ef4444',
            }}
          >
            {testResult.ok ? <CheckCircle size={12} /> : <XCircle size={12} />}
            {testResult.msg}
          </div>
        )}

        <div className="flex gap-2">
          <button
            onClick={testing ? handleStop : handleTest}
            disabled={false}
            className="btn-cyber flex items-center gap-2 flex-1 justify-center"
            style={testing
              ? { borderColor: 'rgba(239,68,68,0.5)', color: '#ef4444' }
              : undefined}
          >
            {testing
              ? <><Volume2 size={13} className="animate-pulse" /> Parar</>
              : <><Volume2 size={13} /> Testar voz de Luna</>
            }
          </button>
        </div>
      </Card>

      {/* STT info */}
      <Card title="Entrada por Voz (STT)">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
            style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.25)' }}>
            <Mic size={15} className="text-cyber-cyan" />
          </div>
          <div>
            <p className="text-[12px] font-semibold text-cyber-text">Reconhecimento de Fala</p>
            <p className="text-[10px] text-cyber-dim mt-1 leading-relaxed">
              Use o botão <Mic size={9} className="inline" /> no chat para falar diretamente com Luna.
              Usa a API nativa do browser — sem custo, sem chave necessária.
              Compatível com Chrome e Edge.
            </p>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2">
          {[
            { label: 'Motor STT',   value: 'Web Speech API' },
            { label: 'Idioma',      value: 'Português (BR)' },
            { label: 'Custo',       value: 'Gratuito' },
            { label: 'Privacidade', value: 'Local / Browser' },
          ].map(({ label, value }) => (
            <div key={label} className="flex items-center gap-2 px-2 py-1.5 rounded"
              style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.09)' }}>
              <span className="text-[9px] font-mono text-cyber-dim">{label}:</span>
              <span className="text-[10px] font-mono text-cyber-cyan font-semibold">{value}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB: SEGURANÇA
// ═══════════════════════════════════════════════════════════════════════════════
function TabSeguranca() {
  const hasElectron = !!window.electronAPI?.keys

  return (
    <div className="space-y-4">
      <Card title="Proteções Ativas">
        <div className="space-y-3">
          {[
            {
              label: 'API Keys — Criptografia do SO',
              desc: hasElectron
                ? 'Chaves armazenadas com Keychain (macOS) / DPAPI (Windows) / libsecret (Linux). Zero texto plano em disco.'
                : 'Chaves salvas localmente no dispositivo via Electron. Nunca enviadas para servidores externos.',
              on: true, locked: true,
            },
            {
              label: 'IPC Auth Token',
              desc: 'Token aleatório de 32 bytes gerado no startup. Electron → Python. Valida cada requisição via X-Luna-Token.',
              on: hasElectron, locked: true,
            },
            {
              label: 'Rate Limiting',
              desc: 'Sliding window: 120 req/min geral, 30 req/min no chat, 10 req/min em keys. Por IP.',
              on: true, locked: true,
            },
            {
              label: 'Audit Log',
              desc: 'Log JSONL estruturado de todas as requisições e tool calls. Auto-rotação a cada 10MB.',
              on: true, locked: true,
            },
            {
              label: 'Path Traversal Guard',
              desc: 'Electron IPC + backend Python bloqueiam acesso a arquivos fora do workspace. Normcase para Windows.',
              on: true, locked: true,
            },
            {
              label: 'SSRF Protection',
              desc: 'Bloqueia fetch para IPs internos (127.x, 10.x, 172.16.x, 192.168.x, 169.254.x, metadata AWS/GCP).',
              on: true, locked: true,
            },
            {
              label: 'CORS Restrito',
              desc: 'Backend só aceita requests de localhost:5173 e localhost:3000.',
              on: true, locked: true,
            },
            {
              label: 'CSP Ativa',
              desc: 'Content Security Policy rígida no Electron. Produção: sem unsafe-eval, sem unsafe-inline.',
              on: true, locked: true,
            },
            {
              label: 'Security Headers',
              desc: 'X-Content-Type-Options, X-Frame-Options: DENY, Permissions-Policy restrito em todas as respostas.',
              on: true, locked: true,
            },
            {
              label: 'Modo Sandbox (código)',
              desc: 'Isola execução de código em ambiente controlado.',
              on: false, locked: false,
            },
          ].map(({ label, desc, on, locked }) => (
            <label key={label} className={`flex items-start gap-3 ${locked ? 'opacity-70' : 'cursor-pointer'} group`}>
              <input type="checkbox" defaultChecked={on} disabled={locked} className="mt-0.5 w-3.5 h-3.5 accent-cyber-cyan" />
              <div>
                <p className="text-[12px] font-semibold text-cyber-text group-hover:text-cyber-cyan transition-colors">
                  {label}
                  {locked && <span className="text-[9px] font-mono text-cyber-dim ml-2">(imutável)</span>}
                </p>
                <p className="text-[10px] text-cyber-dim mt-0.5">{desc}</p>
              </div>
            </label>
          ))}
        </div>
      </Card>

      <Card title="Política de Dados">
        <div className="space-y-2 text-[11px] font-mono text-cyber-dim leading-relaxed">
          <p>🔒 <strong className="text-cyber-text">API Keys:</strong> Armazenadas com criptografia do sistema operacional (Keychain/DPAPI/libsecret). Nunca em texto plano em disco ou localStorage.</p>
          <p>💬 <strong className="text-cyber-text">Conversas:</strong> Mantidas em memória durante a sessão. Histórico persistente opcional.</p>
          <p>📁 <strong className="text-cyber-text">Arquivos:</strong> Luna só acessa arquivos dentro do workspace selecionado. Path traversal bloqueado no backend e no IPC.</p>
          <p>🌐 <strong className="text-cyber-text">Web:</strong> Buscas e fetches passam pelo backend Python local. IPs internos bloqueados por SSRF guard.</p>
          <p>🐛 <strong className="text-cyber-text">Bug Reports:</strong> Opcionais, anônimos, enviados apenas quando você confirmar.</p>
        </div>
      </Card>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB: BUG REPORT
// ═══════════════════════════════════════════════════════════════════════════════
function TabBugReport() {
  const { backendUrl } = useStore()
  const [reports, setReports]         = useState<BugReport[]>([])
  const [selected, setSelected]       = useState<Set<string>>(new Set())
  const [webhookUrl, setWebhookUrl]   = useState(
    localStorage.getItem('luna-webhook-url') ?? ''
  )
  const [userNote, setUserNote]       = useState('')
  const [sending, setSending]         = useState(false)
  const [status, setStatus]           = useState<{ ok: boolean; msg: string } | null>(null)
  const [filterSev, setFilterSev]     = useState<BugSeverity | 'all'>('all')
  const [showDetails, setShowDetails] = useState<string | null>(null)

  const reload = useCallback(() => {
    setReports(getBugReports().reverse())
    setSelected(new Set())
  }, [])

  useEffect(() => { reload() }, [reload])

  const toggleSelect = (id: string) =>
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const selectAll = () => setSelected(new Set(filtered.map(r => r.id)))
  const deselectAll = () => setSelected(new Set())

  const handleDelete = (id: string) => { deleteBugReport(id); reload() }
  const handleClearAll = () => { clearBugReports(); reload() }

  const handleSend = async () => {
    const toSend = reports.filter(r => selected.has(r.id))
    if (!toSend.length) return
    setSending(true)
    setStatus(null)
    localStorage.setItem('luna-webhook-url', webhookUrl)
    const result = await sendBugReports(toSend, backendUrl, webhookUrl, userNote)
    setStatus({ ok: result.ok, msg: result.message })
    setSending(false)
    if (result.ok) reload()
  }

  const filtered = filterSev === 'all' ? reports : reports.filter(r => r.severity === filterSev)

  const counts = reports.reduce((acc, r) => {
    acc[r.severity] = (acc[r.severity] ?? 0) + 1; return acc
  }, {} as Record<string, number>)

  const unsent = reports.filter(r => !r.sent).length

  return (
    <div className="space-y-4">
      {/* Summary row */}
      <div className="grid grid-cols-4 gap-3">
        {(['critical', 'error', 'warning', 'info'] as BugSeverity[]).map(sev => {
          const cfg = SEV_CONFIG[sev]
          const Icon = cfg.icon
          return (
            <button
              key={sev}
              onClick={() => setFilterSev(prev => prev === sev ? 'all' : sev)}
              className="rounded-xl p-3 text-center transition-all"
              style={{
                background: filterSev === sev ? `${cfg.color}14` : 'rgba(15,22,36,0.6)',
                border: filterSev === sev ? `1px solid ${cfg.color}45` : '1px solid rgba(0,212,255,0.08)',
              }}
            >
              <Icon size={18} className="mx-auto mb-1" style={{ color: cfg.color }} />
              <p className="text-[18px] font-bold" style={{ color: cfg.color }}>{counts[sev] ?? 0}</p>
              <p className="text-[9px] font-mono text-cyber-dim">{cfg.label}</p>
            </button>
          )
        })}
      </div>

      {/* Webhook config */}
      <Card title="Envio para Desenvolvedor"
        action={
          <span className="text-[9px] font-mono text-cyber-dim">
            {unsent > 0 ? `${unsent} não enviado(s)` : '✓ Tudo enviado'}
          </span>
        }
      >
        <div className="space-y-3">
          <div>
            <label className="block text-[10px] font-mono text-cyber-muted mb-1.5">
              Discord/Slack Webhook URL (opcional)
            </label>
            <input
              type="text"
              value={webhookUrl}
              onChange={e => setWebhookUrl(e.target.value)}
              placeholder="https://discord.com/api/webhooks/..."
              className="input-cyber text-[11px] font-mono w-full"
            />
            <p className="text-[9px] font-mono text-cyber-dim mt-1">
              Configure um webhook Discord ou Slack para receber os relatórios diretamente.
              Se deixar vazio, os relatórios serão salvos no servidor backend.
            </p>
          </div>
          <div>
            <label className="block text-[10px] font-mono text-cyber-muted mb-1.5">
              Nota adicional (aparece no relatório)
            </label>
            <textarea
              value={userNote}
              onChange={e => setUserNote(e.target.value)}
              placeholder="Descreva o que estava fazendo quando o erro ocorreu..."
              rows={2}
              className="input-cyber text-[11px] font-mono w-full resize-none"
            />
          </div>

          {status && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-[11px] font-mono"
              style={{
                background: status.ok ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
                border: `1px solid ${status.ok ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`,
                color: status.ok ? '#10b981' : '#ef4444',
              }}>
              {status.ok ? <CheckCircle size={12} /> : <XCircle size={12} />}
              {status.msg}
            </div>
          )}

          <div className="flex gap-2">
            <button
              onClick={handleSend}
              disabled={selected.size === 0 || sending}
              className="btn-cyber flex items-center gap-2 flex-1 justify-center"
            >
              {sending ? <RefreshCw size={12} className="animate-spin" /> : <Send size={12} />}
              {sending ? 'Enviando...' : `Enviar selecionados (${selected.size})`}
            </button>
          </div>
        </div>
      </Card>

      {/* Report list */}
      <Card
        title={`Relatórios Capturados (${filtered.length})`}
        action={
          <div className="flex items-center gap-2">
            <button onClick={reload} className="text-cyber-dim hover:text-cyber-cyan transition-colors">
              <RefreshCw size={12} />
            </button>
            {filtered.length > 0 && (
              <>
                <button onClick={selectAll}
                  className="text-[9px] font-mono text-cyber-muted hover:text-cyber-cyan transition-colors">
                  Selecionar tudo
                </button>
                <button onClick={deselectAll}
                  className="text-[9px] font-mono text-cyber-muted hover:text-cyber-cyan transition-colors">
                  Limpar
                </button>
                <button onClick={handleClearAll}
                  className="text-[9px] font-mono text-cyber-red hover:text-red-400 transition-colors flex items-center gap-1">
                  <Trash2 size={10} /> Apagar tudo
                </button>
              </>
            )}
          </div>
        }
      >
        {filtered.length === 0 ? (
          <div className="text-center py-8">
            <Bug size={28} className="text-cyber-dim mx-auto mb-2" />
            <p className="text-[12px] font-mono text-cyber-muted">Nenhum relatório de erro capturado.</p>
            <p className="text-[10px] font-mono text-cyber-dim mt-1">Luna monitora erros automaticamente em segundo plano.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map(r => {
              const cfg    = SEV_CONFIG[r.severity]
              const isOpen = showDetails === r.id
              return (
                <div
                  key={r.id}
                  className="rounded-lg overflow-hidden transition-all"
                  style={{
                    background: selected.has(r.id) ? `${cfg.color}0a` : 'rgba(15,22,36,0.5)',
                    border: selected.has(r.id)
                      ? `1px solid ${cfg.color}35`
                      : '1px solid rgba(0,212,255,0.07)',
                  }}
                >
                  {/* Row */}
                  <div className="flex items-center gap-2.5 px-3 py-2.5">
                    <input
                      type="checkbox"
                      checked={selected.has(r.id)}
                      onChange={() => toggleSelect(r.id)}
                      className="accent-cyber-cyan w-3 h-3"
                    />
                    <SeverityBadge sev={r.severity} />
                    <p className="flex-1 text-[11px] text-cyber-text truncate font-mono" title={r.title}>
                      {r.title}
                    </p>
                    <span className="text-[9px] font-mono text-cyber-dim flex-shrink-0">
                      {new Date(r.timestamp).toLocaleString('pt-BR', { hour12: false })}
                    </span>
                    {r.sent && <CheckCircle size={11} className="text-cyber-green flex-shrink-0" />}
                    <button
                      onClick={() => setShowDetails(isOpen ? null : r.id)}
                      className="text-cyber-dim hover:text-cyber-cyan transition-colors"
                    >
                      <ChevronRight size={13} style={{ transform: isOpen ? 'rotate(90deg)' : undefined, transition: 'transform 0.15s' }} />
                    </button>
                    <button
                      onClick={() => handleDelete(r.id)}
                      className="text-cyber-dim hover:text-cyber-red transition-colors"
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>

                  {/* Details */}
                  {isOpen && (
                    <div className="px-3 pb-3 space-y-2 border-t" style={{ borderColor: 'rgba(0,212,255,0.08)' }}>
                      <p className="text-[10px] font-mono text-cyber-dim pt-2">{r.message}</p>
                      {r.context && Object.keys(r.context).length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {Object.entries(r.context).map(([k, v]) => (
                            <span key={k} className="text-[9px] font-mono px-1.5 py-0.5 rounded"
                              style={{ background: 'rgba(0,212,255,0.06)', border: '1px solid rgba(0,212,255,0.12)', color: '#64748b' }}>
                              {k}: {v}
                            </span>
                          ))}
                        </div>
                      )}
                      {r.stack && (
                        <pre className="text-[9px] font-mono text-cyber-dim bg-black/30 p-2 rounded overflow-x-auto max-h-32">
                          {r.stack.split('\n').slice(0, 8).join('\n')}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </Card>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB: SOBRE
// ═══════════════════════════════════════════════════════════════════════════════
function TabSobre() {
  return (
    <div className="space-y-4">
      <Card title="Luna Agent">
        <div className="flex items-center gap-4 mb-5">
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center text-4xl flex-shrink-0"
            style={{ background: 'linear-gradient(135deg,#7c3aed,#00d4ff)', boxShadow: '0 0 30px rgba(0,212,255,0.3)' }}
          >🌙</div>
          <div>
            <h2 className="text-lg font-bold text-cyber-cyan glow-text-cyan">LUNA</h2>
            <p className="text-[11px] font-mono text-cyber-muted">Elite Autonomous AI Agent</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-y-2 gap-x-4 font-mono text-[11px]">
          {[
            ['App',      'Luna Desktop v4.0.0'],
            ['Engine',   'Luna Elite Agent v2.2'],
            ['Runtime',  'Electron 27 + React 18 + Vite 5'],
            ['Backend',  'FastAPI + Python 3.13'],
            ['Foco',     'Web3 · Solana · Bug Bounty · IA'],
            ['Dev',      'Cleiton Prestes (@cleitonprestes)'],
          ].map(([k, v]) => (
            <div key={k} className="flex items-center gap-2">
              <span className="text-cyber-muted w-14 flex-shrink-0">{k}</span>
              <span className="text-cyber-text text-[10px]">{v}</span>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Stack Técnica">
        <div className="grid grid-cols-3 gap-2">
          {[
            { name: 'React 18',         role: 'UI',             color: '#61dafb' },
            { name: 'TypeScript 5',     role: 'Tipagem',        color: '#3178c6' },
            { name: 'Electron 27',      role: 'Desktop',        color: '#47848f' },
            { name: 'Vite 5',           role: 'Build',          color: '#646cff' },
            { name: 'Zustand',          role: 'Estado',         color: '#ffb74d' },
            { name: 'FastAPI',          role: 'Backend',        color: '#009688' },
            { name: 'OpenAI SDK',       role: 'IA',             color: '#10b981' },
            { name: 'Anthropic SDK',    role: 'IA',             color: '#e040fb' },
            { name: 'Tailwind CSS',     role: 'Estilo',         color: '#38bdf8' },
          ].map(({ name, role, color }) => (
            <div key={name} className="p-2 rounded-lg text-center"
              style={{ background: `${color}0d`, border: `1px solid ${color}25` }}>
              <p className="text-[11px] font-bold" style={{ color }}>{name}</p>
              <p className="text-[9px] font-mono text-cyber-dim">{role}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Licença e Créditos">
        <p className="text-[10px] font-mono text-cyber-dim leading-relaxed">
          Luna Agent é um projeto privado desenvolvido por Cleiton Prestes.
          Foco em automação de segurança Web3, bug bounty e desenvolvimento Solana.
          Todos os direitos reservados © 2025.
        </p>
      </Card>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB: CONTA
// ═══════════════════════════════════════════════════════════════════════════════
function TabConta() {
  const { userId, userEmail } = useStore()
  const [avatarUrl, setAvatarUrl]     = useState<string | null>(null)
  const [displayName, setDisplayName] = useState<string>('')
  const [provider, setProvider]       = useState<string>('')
  const [copiedId, setCopiedId]       = useState(false)
  const [loggingOut, setLoggingOut]   = useState(false)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      const user = data.session?.user
      if (!user) return
      setAvatarUrl(user.user_metadata?.avatar_url ?? null)
      setDisplayName(user.user_metadata?.full_name ?? user.user_metadata?.name ?? '')
      const id = user.app_metadata?.provider ?? user.identities?.[0]?.provider ?? ''
      setProvider(id)
    })
  }, [])

  const handleSignOut = async () => {
    setLoggingOut(true)
    try {
      await signOut()
      await window.electronAPI?.auth?.clearSession?.()
      window.location.reload()
    } catch {
      setLoggingOut(false)
    }
  }

  const copyId = () => {
    navigator.clipboard.writeText(userId)
    setCopiedId(true)
    setTimeout(() => setCopiedId(false), 2000)
  }

  const providerLabel = provider === 'google' ? 'Google' : provider === 'twitter' ? 'X (Twitter)' : provider || 'Desconhecido'
  const providerColor = provider === 'google' ? '#ea4335' : provider === 'twitter' ? '#fff' : '#00d4ff'

  return (
    <div className="space-y-4">

      {/* ── Perfil ── */}
      <Card title="Perfil">
        <div className="flex items-center gap-4">
          {/* Avatar */}
          <div className="relative flex-shrink-0">
            {avatarUrl
              ? <img src={avatarUrl} alt="avatar" className="w-16 h-16 rounded-full object-cover" style={{ border: '2px solid rgba(0,212,255,0.3)' }} />
              : (
                <div className="w-16 h-16 rounded-full flex items-center justify-center text-2xl" style={{ background: 'linear-gradient(135deg,#7c3aed,#00d4ff)', border: '2px solid rgba(0,212,255,0.3)' }}>
                  🌙
                </div>
              )
            }
            {/* Badge do provider */}
            <div className="absolute -bottom-1 -right-1 w-5 h-5 rounded-full flex items-center justify-center text-[8px] font-bold" style={{ background: '#080b14', border: '1px solid rgba(0,212,255,0.3)', color: providerColor }}>
              {provider === 'google' ? 'G' : provider === 'twitter' ? 'X' : '?'}
            </div>
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0">
            <p className="text-[14px] font-semibold text-cyber-text truncate">{displayName || 'Usuário Luna'}</p>
            <p className="text-[11px] font-mono text-cyber-muted truncate">{userEmail}</p>
            <div className="flex items-center gap-1.5 mt-1">
              <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#10b981' }} />
              <span className="text-[10px] font-mono text-cyber-dim">via {providerLabel}</span>
            </div>
          </div>
        </div>
      </Card>

      {/* ── Detalhes da Conta ── */}
      <Card title="Detalhes da Conta">
        <div className="space-y-3">

          {/* Account ID */}
          <div>
            <p className="text-[10px] font-mono text-cyber-muted uppercase tracking-widest mb-1">Account ID</p>
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(0,212,255,0.12)' }}>
              <code className="text-[10px] font-mono text-cyber-cyan flex-1 truncate select-all">{userId || '—'}</code>
              <button
                onClick={copyId}
                className="flex items-center gap-1 px-2 py-1 rounded text-[9px] font-mono transition-all flex-shrink-0"
                style={{
                  background: copiedId ? 'rgba(16,185,129,0.15)' : 'rgba(0,212,255,0.08)',
                  border: `1px solid ${copiedId ? 'rgba(16,185,129,0.3)' : 'rgba(0,212,255,0.2)'}`,
                  color: copiedId ? '#10b981' : '#00d4ff',
                }}
              >
                {copiedId ? <><Check size={9} /> Copiado</> : <><Copy size={9} /> Copiar</>}
              </button>
            </div>
            <p className="text-[9px] font-mono text-cyber-dim mt-1">Este ID vincula seus Grains à conta — funciona em qualquer dispositivo.</p>
          </div>

          {/* Email */}
          <div>
            <p className="text-[10px] font-mono text-cyber-muted uppercase tracking-widest mb-1">Email</p>
            <div className="px-3 py-2 rounded-lg" style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(0,212,255,0.12)' }}>
              <span className="text-[11px] font-mono text-cyber-text">{userEmail || '—'}</span>
            </div>
          </div>

          {/* Provedor */}
          <div>
            <p className="text-[10px] font-mono text-cyber-muted uppercase tracking-widest mb-1">Método de login</p>
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(0,212,255,0.12)' }}>
              <span className="text-[13px] font-bold" style={{ color: providerColor }}>
                {provider === 'google' ? 'G' : provider === 'twitter' ? '𝕏' : '?'}
              </span>
              <span className="text-[11px] font-mono text-cyber-text">{providerLabel}</span>
              <span className="ml-auto text-[9px] font-mono px-1.5 py-0.5 rounded" style={{ background: 'rgba(16,185,129,0.1)', color: '#10b981', border: '1px solid rgba(16,185,129,0.2)' }}>
                Conectado
              </span>
            </div>
          </div>
        </div>
      </Card>

      {/* ── Sessão ── */}
      <Card title="Sessão">
        <div className="space-y-3">
          <p className="text-[11px] font-mono text-cyber-muted">
            Sua sessão fica salva de forma segura via criptografia do sistema operacional (DPAPI/Keychain). Você permanece logado entre reinicializações.
          </p>
          <button
            onClick={handleSignOut}
            disabled={loggingOut}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-[11px] font-mono font-semibold transition-all hover:opacity-90 disabled:opacity-50"
            style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', color: '#ef4444' }}
          >
            <LogOut size={13} />
            {loggingOut ? 'Saindo...' : 'Sair da conta'}
          </button>
          <p className="text-[9px] font-mono text-cyber-dim">
            Sair não apaga seus Grains. Eles continuam vinculados ao seu Account ID e são recuperados no próximo login.
          </p>
        </div>
      </Card>

      {/* ── Segurança da conta ── */}
      <Card title="Segurança">
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: 'Tokens cifrados',    desc: 'DPAPI/Keychain do SO', ok: true },
            { label: 'Senha armazenada',   desc: 'Nunca — login via OAuth', ok: true },
            { label: 'Sessão persistente', desc: 'safeStorage Electron', ok: true },
            { label: '2FA',                desc: 'Via Google/Twitter', ok: true },
          ].map(({ label, desc, ok }) => (
            <div key={label} className="flex items-start gap-2 p-2.5 rounded-lg" style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(0,212,255,0.06)' }}>
              <div className="w-4 h-4 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5" style={{ background: ok ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)' }}>
                <div className="w-1.5 h-1.5 rounded-full" style={{ background: ok ? '#10b981' : '#ef4444' }} />
              </div>
              <div>
                <p className="text-[10px] font-mono text-cyber-text">{label}</p>
                <p className="text-[9px] font-mono text-cyber-dim">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

const TAB_COMPONENTS: Record<TabId, React.FC> = {
  conta:      TabConta,
  geral:      TabGeral,
  provedores: TabProvedores,
  modelo:     TabModelo,
  workspace:  TabWorkspace,
  voz:        TabVoz,
  seguranca:  TabSeguranca,
  bugs:       TabBugReport,
  sobre:      TabSobre,
}

const Settings: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('geral')
  const TabContent = TAB_COMPONENTS[activeTab]

  return (
    <div className="flex h-full overflow-hidden">

      {/* ── Left tab rail ──────────────────────────────────────────────────── */}
      <div
        className="flex-shrink-0 w-44 flex flex-col py-4 border-r"
        style={{ background: 'rgba(8,11,20,0.5)', borderColor: 'rgba(0,212,255,0.08)' }}
      >
        {/* Header */}
        <div className="px-4 mb-4">
          <div className="flex items-center gap-2 mb-0.5">
            <Sliders size={13} className="text-cyber-cyan" />
            <span className="text-[12px] font-bold text-cyber-cyan" style={{ textShadow: '0 0 8px rgba(0,212,255,0.5)' }}>
              SETTINGS
            </span>
          </div>
          <p className="text-[9px] font-mono text-cyber-dim">Luna Agent v4.0</p>
        </div>

        {/* Tab list */}
        <nav className="flex-1 px-2 space-y-0.5">
          {TABS.map(({ id, label, icon: Icon }) => {
            const isActive = activeTab === id
            return (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-left transition-all text-[11px] font-mono"
                style={isActive
                  ? {
                      background: 'rgba(0,212,255,0.1)',
                      border: '1px solid rgba(0,212,255,0.3)',
                      color: '#00d4ff',
                    }
                  : {
                      background: 'transparent',
                      border: '1px solid transparent',
                      color: '#64748b',
                    }}
              >
                <Icon size={13} style={{ color: isActive ? '#00d4ff' : '#475569' }} />
                {label}
                {id === 'bugs' && (() => {
                  const n = getBugReports().filter(r => !r.sent).length
                  return n > 0 ? (
                    <span className="ml-auto text-[8px] font-bold px-1 py-0.5 rounded-full"
                      style={{ background: 'rgba(239,68,68,0.2)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.4)' }}>
                      {n}
                    </span>
                  ) : null
                })()}
              </button>
            )
          })}
        </nav>
      </div>

      {/* ── Content area ───────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-2xl mx-auto">
          <TabContent />
        </div>
      </div>
    </div>
  )
}

export default Settings
