import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useStore } from '@store/appStore'
import {
  Bot, Check, CheckCircle2, Cpu, Database, FolderOpen, HardDrive,
  Info, LockKeyhole, Monitor, Palette, RefreshCw, Server, Shield,
  Sliders, Terminal, XCircle, RotateCcw, PanelRight,
} from 'lucide-react'
import { EXECUTION_PANEL_DEFAULT_WIDTH } from '@/config/layout'

type TabId = 'local' | 'workspace' | 'modules' | 'appearance' | 'security' | 'about'

interface OllamaStatus {
  running: boolean
  base_url?: string
  models: Array<{ name: string; size_gb: number; modified?: string }>
}

const TABS: Array<{ id: TabId; label: string; icon: React.ElementType }> = [
  { id: 'local', label: 'Local AI', icon: Cpu },
  { id: 'workspace', label: 'Workspace', icon: FolderOpen },
  { id: 'modules', label: 'Modules', icon: Database },
  { id: 'appearance', label: 'Interface', icon: Palette },
  { id: 'security', label: 'Segurança', icon: Shield },
  { id: 'about', label: 'Sobre', icon: Info },
]

const LOCAL_MODELS = [
  { id: 'luna-cyber-fast', name: 'Luna Cyber Fast', description: 'Modelo principal otimizado para o copiloto local.', color: '#14f195' },
  { id: 'qwen3.5:4b', name: 'Qwen 3.5 4B', description: 'Fallback local leve e compatível.', color: '#00d4ff' },
] as const

function Section({ title, description, action, children }: {
  title: string
  description?: string
  action?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-cyber-cyan/10 bg-[#0d1422]/85">
      <div className="flex items-start justify-between gap-4 border-b border-cyber-cyan/10 px-5 py-3.5">
        <div>
          <h2 className="text-sm font-semibold text-cyber-text">{title}</h2>
          {description ? <p className="mt-1 text-[11px] leading-relaxed text-cyber-muted">{description}</p> : null}
        </div>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </section>
  )
}

function StatusRow({ label, detail, ok, pending = false }: {
  label: string
  detail: string
  ok: boolean
  pending?: boolean
}) {
  const color = pending ? '#94a3b8' : ok ? '#14f195' : '#f87171'
  return (
    <div className="flex min-h-11 items-center gap-3 border-b border-white/[0.04] py-2.5 last:border-b-0">
      <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md" style={{ background: `${color}12`, color }} aria-hidden="true">
        {pending ? <RefreshCw size={12} className="animate-spin" /> : ok ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[12px] font-medium text-cyber-text">{label}</p>
        <p className="mt-0.5 truncate font-mono text-[10px] text-cyber-muted" title={detail}>{detail}</p>
      </div>
    </div>
  )
}

function LocalAITab() {
  const {
    backendUrl, lunaApiToken, backendStatus, healthLoading, refreshBackendHealth,
    currentModel, setCurrentModel, maxTokens, setMaxTokens,
  } = useStore()
  const [ollama, setOllama] = useState<OllamaStatus | null>(null)
  const [detailsLoading, setDetailsLoading] = useState(true)
  const [pulling, setPulling] = useState(false)
  const [error, setError] = useState('')
  const initialRefreshStarted = useRef(false)

  const refresh = useCallback(async () => {
    setDetailsLoading(true)
    setError('')
    const headers = lunaApiToken ? { 'X-Luna-Token': lunaApiToken } : undefined
    try {
      await refreshBackendHealth(true)
      const currentHealth = useStore.getState().backendStatus
      if (!currentHealth.connected) throw new Error(currentHealth.error || 'Runtime local indisponível')
      const ollamaData = await fetch(`${backendUrl}/api/providers/ollama/status`, {
        headers,
        signal: AbortSignal.timeout(10000),
      }).then(async (response) => {
        if (!response.ok) return null
        return response.json() as Promise<OllamaStatus>
      }).catch(() => null)
      setOllama(ollamaData ?? {
        running: currentHealth.ollama,
        base_url: 'http://localhost:11434/v1',
        models: currentHealth.availableModels.map((name) => ({ name, size_gb: 0 })),
      })
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : 'Falha ao consultar o runtime local')
      setOllama({ running: false, models: [] })
    } finally {
      setDetailsLoading(false)
    }
  }, [backendUrl, lunaApiToken, refreshBackendHealth])

  useEffect(() => {
    if (initialRefreshStarted.current) return
    initialRefreshStarted.current = true
    void refresh()
  }, [refresh])

  const pullFallback = async () => {
    setPulling(true)
    setError('')
    try {
      const response = await fetch(`${backendUrl}/api/providers/ollama/pull`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(lunaApiToken ? { 'X-Luna-Token': lunaApiToken } : {}),
        },
        body: JSON.stringify({ model: 'qwen3.5:4b' }),
      })
      if (!response.ok) throw new Error(`Download recusado: HTTP ${response.status}`)
      await refresh()
    } catch (pullError) {
      setError(pullError instanceof Error ? pullError.message : 'Falha ao solicitar o modelo')
    } finally {
      setPulling(false)
    }
  }

  const syncMaxTokens = async () => {
    try {
      await fetch(`${backendUrl}/api/config`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(lunaApiToken ? { 'X-Luna-Token': lunaApiToken } : {}),
        },
        body: JSON.stringify({ max_tokens: maxTokens }),
      })
    } catch { /* keep the local preference */ }
  }

  const installed = new Set((ollama?.models ?? []).map((model) => model.name.replace(':latest', '')))
  const loading = healthLoading || detailsLoading

  return (
    <div className="space-y-4">
      <Section
        title="Runtime local"
        description="Diagnóstico real do FastAPI e do Ollama nesta máquina."
        action={(
          <button type="button" onClick={() => void refresh()} disabled={loading} className="inline-flex min-h-8 items-center gap-1.5 rounded-md border border-cyber-cyan/20 bg-cyber-cyan/5 px-2.5 font-mono text-[10px] text-cyber-cyan transition-colors hover:bg-cyber-cyan/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan/50 disabled:opacity-50">
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Atualizar
          </button>
        )}
      >
        {error ? <div className="mb-3 rounded-lg border border-red-400/20 bg-red-400/5 px-3 py-2 text-[11px] text-red-300" role="alert">{error}. Confirme o backend em <code className="font-mono">{backendUrl}</code> e o Ollama em <code className="font-mono">localhost:11434</code>.</div> : null}
        <StatusRow label="FastAPI" detail={backendStatus.connected ? backendUrl : 'Backend local não respondeu'} ok={backendStatus.connected} pending={loading} />
        <StatusRow label="Ollama" detail={ollama?.base_url ?? 'http://localhost:11434/v1'} ok={Boolean(ollama?.running)} pending={loading} />
        <StatusRow label="Zero-cloud" detail="Nenhum provedor externo é necessário" ok={backendStatus.zeroCloudMode} pending={loading} />
        <StatusRow label="Supervisão" detail="A execução permanece sob controle do operador" ok={backendStatus.supervisedMode} pending={loading} />
      </Section>

      <Section title="Modelo" description="A lista mostra apenas modelos compatíveis com esta edição local.">
        <div className="space-y-2">
          {LOCAL_MODELS.map((model) => {
            const selected = currentModel === model.id
            const available = installed.has(model.id) || installed.has(model.id.split(':')[0]) || (model.id === 'luna-cyber-fast' && backendStatus.model.startsWith('luna-cyber-fast'))
            return (
              <button type="button" key={model.id} onClick={() => setCurrentModel(model.id)} className="flex w-full items-center gap-3 rounded-lg border px-3 py-3 text-left transition-colors hover:bg-white/[0.025] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan/50" style={{ borderColor: selected ? `${model.color}55` : 'rgba(0,212,255,0.08)', background: selected ? `${model.color}0d` : 'rgba(0,0,0,0.12)' }} aria-pressed={selected}>
                <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md" style={{ color: model.color, background: `${model.color}12` }}><Bot size={16} /></span>
                <span className="min-w-0 flex-1"><span className="block text-[12px] font-semibold text-cyber-text">{model.name}</span><span className="mt-0.5 block text-[10px] text-cyber-muted">{model.description}</span></span>
                <span className="font-mono text-[9px]" style={{ color: available ? '#14f195' : '#94a3b8' }}>{available ? 'INSTALADO' : 'NÃO DETECTADO'}</span>
                {selected ? <Check size={13} style={{ color: model.color }} /> : null}
              </button>
            )
          })}
        </div>
        {!installed.has('qwen3.5:4b') && ollama?.running ? (
          <button type="button" onClick={() => void pullFallback()} disabled={pulling} className="mt-3 inline-flex min-h-9 items-center gap-2 rounded-md border border-cyber-cyan/25 bg-cyber-cyan/5 px-3 font-mono text-[10px] text-cyber-cyan transition-colors hover:bg-cyber-cyan/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan/50 disabled:opacity-50">
            <HardDrive size={12} /> {pulling ? 'Solicitando download…' : 'Baixar fallback qwen3.5:4b'}
          </button>
        ) : null}
      </Section>

      <Section title="Limite de resposta" description="Métrica técnica local; não representa valor monetário.">
        <div className="flex items-center gap-4">
          <input type="range" min={64} max={4096} step={64} value={maxTokens} onChange={(event) => setMaxTokens(Number(event.target.value))} onBlur={() => void syncMaxTokens()} className="min-w-0 flex-1 accent-cyber-cyan" aria-label="Limite máximo de tokens da resposta" />
          <output className="w-20 rounded-md border border-cyber-cyan/15 bg-black/20 px-2 py-1.5 text-center font-mono text-[11px] text-cyber-cyan">{maxTokens.toLocaleString('pt-BR')}</output>
        </div>
      </Section>
    </div>
  )
}

function WorkspaceTab() {
  const { backendUrl, setBackendUrl, workspacePath, workspaceName, setWorkspace, clearWorkspace } = useStore()
  const [urlDraft, setUrlDraft] = useState(backendUrl)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const saveBackendUrl = () => {
    try {
      const parsed = new URL(urlDraft)
      if (parsed.protocol !== 'http:' || !['localhost', '127.0.0.1'].includes(parsed.hostname)) throw new Error('Use somente um endereço HTTP de loopback')
      const normalized = parsed.toString().replace(/\/$/, '')
      setBackendUrl(normalized)
      setUrlDraft(normalized)
      setMessage('Backend local atualizado.')
    } catch (urlError) {
      setMessage(urlError instanceof Error ? urlError.message : 'URL inválida')
    }
  }

  const chooseWorkspace = async () => {
    const api = window.electronAPI?.workspace
    if (!api) { setMessage('A seleção de pasta está disponível no aplicativo Electron.'); return }
    setBusy(true)
    setMessage('')
    try {
      const result = await api.openFolderDialog()
      const selectedPath = result.filePaths[0]
      if (result.canceled || !selectedPath) return
      const name = selectedPath.split(/[\\/]/).filter(Boolean).pop() ?? selectedPath
      await api.setWorkspace(selectedPath)
      setWorkspace(selectedPath, name)
      setMessage('Workspace selecionado; o caminho será validado e enviado ao backend em cada operação.')
    } catch (workspaceError) {
      setMessage(workspaceError instanceof Error ? workspaceError.message : 'Falha ao selecionar o workspace')
    } finally { setBusy(false) }
  }

  const removeWorkspace = async () => {
    await window.electronAPI?.workspace?.setWorkspace?.(null)
    clearWorkspace()
    setMessage('Workspace removido do contexto ativo.')
  }

  return (
    <div className="space-y-4">
      <Section title="Workspace ativo" description="A Luna só acessa arquivos dentro da pasta explicitamente selecionada.">
        <div className="flex items-center gap-3 rounded-lg border border-cyber-cyan/10 bg-black/20 p-3">
          <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-cyber-cyan/10 text-cyber-cyan"><FolderOpen size={17} /></span>
          <div className="min-w-0 flex-1"><p className="text-[12px] font-semibold text-cyber-text">{workspaceName || 'Nenhuma pasta selecionada'}</p><p className="mt-0.5 truncate font-mono text-[10px] text-cyber-muted" title={workspacePath}>{workspacePath || 'Selecione uma pasta para habilitar contexto de projeto.'}</p></div>
          <button type="button" onClick={() => void chooseWorkspace()} disabled={busy} className="min-h-9 rounded-md border border-cyber-cyan/25 bg-cyber-cyan/5 px-3 font-mono text-[10px] text-cyber-cyan hover:bg-cyber-cyan/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan/50 disabled:opacity-50">{busy ? 'Abrindo…' : workspacePath ? 'Trocar' : 'Selecionar'}</button>
        </div>
        {workspacePath ? <button type="button" onClick={() => void removeWorkspace()} className="mt-3 text-[10px] text-cyber-muted underline-offset-4 hover:text-red-300 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/50">Remover workspace ativo</button> : null}
      </Section>
      <Section title="Backend FastAPI" description="A edição local aceita somente localhost ou 127.0.0.1.">
        <label htmlFor="backend-url" className="mb-2 block font-mono text-[10px] text-cyber-muted">Endereço local</label>
        <div className="flex gap-2"><input id="backend-url" value={urlDraft} onChange={(event) => setUrlDraft(event.target.value)} className="input-cyber min-w-0 flex-1" spellCheck={false} /><button type="button" onClick={saveBackendUrl} className="min-h-10 rounded-md border border-cyber-cyan/25 bg-cyber-cyan/5 px-4 font-mono text-[10px] text-cyber-cyan hover:bg-cyber-cyan/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan/50">Salvar</button></div>
        {message ? <p className="mt-2 text-[10px] text-cyber-muted" role="status">{message}</p> : null}
      </Section>
    </div>
  )
}

function ModulesTab() {
  const { backendStatus } = useStore()
  const mentor = backendStatus.modules?.mentor_kali_devtools
  const available = Boolean(mentor?.found && mentor?.loaded && mentor?.enabled)
  return (
    <Section title="Módulos externos" description="Conteúdo carregado em modo read-only a partir da configuração local.">
      <div className="flex items-start gap-3 rounded-lg border border-cyber-cyan/10 bg-black/20 p-4">
        <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-purple-400/10 text-purple-300"><Database size={17} /></span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><h3 className="text-[12px] font-semibold text-cyber-text">Mentor Kali + DevTools</h3><span className={`rounded-full border px-2 py-0.5 font-mono text-[8px] ${available ? 'border-cyber-green/25 bg-cyber-green/10 text-cyber-green' : 'border-red-400/20 bg-red-400/5 text-red-300'}`}>{available ? 'LOADED' : 'INDISPONÍVEL'}</span></div>
          <p className="mt-1 text-[10px] leading-relaxed text-cyber-muted">Trechos relevantes são inseridos dinamicamente; o arquivo completo não é copiado para o histórico.</p>
          <code className="mt-3 block truncate rounded-md bg-black/30 px-2.5 py-2 font-mono text-[9px] text-cyber-cyan" title="D:\LunaCyber\config\modules">D:\LunaCyber\config\modules</code>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        {([['Encontrado', mentor?.found], ['Carregado', mentor?.loaded], ['Habilitado', mentor?.enabled]] as const).map(([label, value]) => (
          <div key={label} className="rounded-lg border border-white/[0.05] bg-black/15 px-3 py-2 text-center"><p className="font-mono text-[9px] text-cyber-muted">{label}</p><p className={`mt-1 text-[10px] font-semibold ${value ? 'text-cyber-green' : 'text-red-300'}`}>{value ? 'Sim' : 'Não'}</p></div>
        ))}
      </div>
    </Section>
  )
}

function AppearanceTab() {
  const {
    locale, setLocale, sidebarCollapsed, executionPanelVisible,
    executionPanelWidth, resetLayout,
  } = useStore()
  const [layoutReset, setLayoutReset] = useState(false)
  const layoutResetTimerRef = useRef<number | null>(null)
  const locales = [{ id: 'pt-BR', label: 'Português (Brasil)', short: 'PT' }, { id: 'en-US', label: 'English (US)', short: 'EN' }]

  useEffect(() => () => {
    if (layoutResetTimerRef.current !== null) {
      window.clearTimeout(layoutResetTimerRef.current)
    }
  }, [])

  return (
    <div className="space-y-4">
      <Section title="Idioma" description="Altera os rótulos traduzidos sem afetar o conteúdo técnico do workspace.">
        <div className="flex flex-wrap gap-2">{locales.map((option) => { const selected = locale === option.id; return <button type="button" key={option.id} onClick={() => setLocale(option.id)} aria-pressed={selected} className="flex min-h-11 items-center gap-3 rounded-lg border px-3 text-left transition-colors hover:bg-white/[0.025] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan/50" style={{ borderColor: selected ? 'rgba(0,212,255,0.4)' : 'rgba(0,212,255,0.1)', background: selected ? 'rgba(0,212,255,0.08)' : 'rgba(0,0,0,0.12)' }}><span className="font-mono text-[10px] font-semibold text-cyber-cyan">{option.short}</span><span className="text-[11px] text-cyber-text">{option.label}</span>{selected ? <Check size={12} className="text-cyber-green" /> : null}</button> })}</div>
      </Section>
      <Section title="Aparência" description="A identidade lunar/cyber permanece dark-first e otimizada para uso prolongado.">
        <div className="flex items-center gap-3 rounded-lg border border-cyber-cyan/10 bg-black/20 p-3"><Monitor size={17} className="text-cyber-cyan" /><div><p className="text-[12px] font-medium text-cyber-text">Tema Luna Dark</p><p className="mt-0.5 text-[10px] text-cyber-muted">Contraste reforçado, foco visível e movimento reduzido conforme a preferência do sistema.</p></div></div>
      </Section>
      <Section title="Layout" description="A largura e a visibilidade dos painéis ficam salvas somente nesta máquina.">
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="flex items-center gap-3 rounded-lg border border-white/[0.05] bg-black/15 p-3"><Sliders size={15} className="text-cyber-cyan" /><div><p className="font-mono text-[9px] text-cyber-muted">SIDEBAR</p><p className="mt-0.5 text-[11px] text-cyber-text">{sidebarCollapsed ? 'Recolhida' : 'Expandida'}</p></div></div>
          <div className="flex items-center gap-3 rounded-lg border border-white/[0.05] bg-black/15 p-3"><PanelRight size={15} className="text-purple-300" /><div><p className="font-mono text-[9px] text-cyber-muted">PAINEL DIREITO</p><p className="mt-0.5 text-[11px] text-cyber-text">{executionPanelVisible ? `${executionPanelWidth}px` : 'Oculto'}</p></div></div>
        </div>
        <button
          type="button"
          onClick={() => {
            resetLayout()
            setLayoutReset(true)
            if (layoutResetTimerRef.current !== null) {
              window.clearTimeout(layoutResetTimerRef.current)
            }
            layoutResetTimerRef.current = window.setTimeout(() => {
              setLayoutReset(false)
              layoutResetTimerRef.current = null
            }, 2_000)
          }}
          className="mt-3 inline-flex min-h-9 items-center gap-2 rounded-md border border-cyber-cyan/20 bg-cyber-cyan/5 px-3 font-mono text-[10px] text-cyber-cyan transition-colors hover:bg-cyber-cyan/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan/50"
        >
          <RotateCcw size={12} /> {layoutReset ? 'Layout restaurado' : `Restaurar layout (${EXECUTION_PANEL_DEFAULT_WIDTH}px)`}
        </button>
      </Section>
    </div>
  )
}

function SecurityTab() {
  const { backendStatus, backendUrl, workspacePath } = useStore()
  const electronBridge = Boolean(window.electronAPI)
  return (
    <div className="space-y-4">
      <Section title="Proteções locais" description="A autenticação comercial foi removida; estas camadas técnicas continuam obrigatórias.">
        <StatusRow label="Token Electron ↔ FastAPI" detail="X-Luna-Token gerado localmente" ok={electronBridge} />
        <StatusRow label="Context isolation e sandbox" detail={electronBridge ? 'Bridge restrita via preload' : 'Disponível somente no aplicativo Electron'} ok={electronBridge} />
        <StatusRow label="Backend em loopback" detail={backendUrl} ok={backendUrl.includes('localhost') || backendUrl.includes('127.0.0.1')} />
        <StatusRow label="Ollama local" detail={backendStatus.model} ok={backendStatus.ollama} />
        <StatusRow label="Workspace validado" detail={workspacePath || 'Nenhum workspace selecionado'} ok={Boolean(workspacePath)} />
      </Section>
      <Section title="Modelo operacional"><div className="flex items-start gap-3 rounded-lg border border-cyber-green/15 bg-cyber-green/5 p-4"><LockKeyhole size={18} className="mt-0.5 flex-shrink-0 text-cyber-green" /><div><p className="text-[12px] font-semibold text-cyber-text">Copiloto supervisionado</p><p className="mt-1 max-w-[68ch] text-[10px] leading-relaxed text-cyber-muted">A Luna analisa e orienta, mas o operador mantém controle sobre comandos, arquivos e ações sensíveis. O frontend não cria sessões remotas nem credenciais fictícias.</p></div></div></Section>
    </div>
  )
}

function AboutTab() {
  const stack = [
    { icon: Monitor, label: 'Desktop', value: 'Electron 27 + React 18' },
    { icon: Server, label: 'Backend', value: 'FastAPI em 127.0.0.1' },
    { icon: Cpu, label: 'Inferência', value: 'Ollama /v1' },
    { icon: Terminal, label: 'Modo', value: 'local_copilot' },
  ]
  return (
    <div className="space-y-4">
      <Section title="Luna Cyber"><div className="flex items-center gap-4"><div className="flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-xl border border-purple-400/25 bg-purple-400/10 text-3xl">🌙</div><div><h2 className="text-base font-bold text-cyber-cyan">Local AI Copilot</h2><p className="mt-1 text-[11px] text-cyber-muted">Cybersecurity, desenvolvimento e análise técnica no seu dispositivo.</p><span className="mt-2 inline-flex rounded-full border border-cyber-green/20 bg-cyber-green/10 px-2 py-0.5 font-mono text-[8px] text-cyber-green">LOCAL EDITION</span></div></div></Section>
      <Section title="Stack local"><div className="grid gap-2 sm:grid-cols-2">{stack.map(({ icon: Icon, label, value }) => <div key={label} className="flex items-center gap-3 rounded-lg border border-white/[0.05] bg-black/15 p-3"><Icon size={15} className="text-cyber-cyan" /><div><p className="font-mono text-[9px] text-cyber-muted">{label}</p><p className="mt-0.5 text-[11px] text-cyber-text">{value}</p></div></div>)}</div></Section>
    </div>
  )
}

const TAB_COMPONENTS: Record<TabId, React.FC> = {
  local: LocalAITab,
  workspace: WorkspaceTab,
  modules: ModulesTab,
  appearance: AppearanceTab,
  security: SecurityTab,
  about: AboutTab,
}

const Settings: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('local')
  const ActiveTab = TAB_COMPONENTS[activeTab]
  return (
    <div className="settings-shell flex h-full min-w-0 overflow-hidden">
      <aside className="settings-rail flex w-48 flex-shrink-0 flex-col border-r border-cyber-cyan/10 bg-[#080d17]/80 py-4">
        <div className="px-4 pb-4"><div className="flex items-center gap-2"><Sliders size={14} className="text-cyber-cyan" /><h1 className="text-[12px] font-semibold tracking-[0.08em] text-cyber-text">SETTINGS</h1></div><p className="mt-1 font-mono text-[9px] text-cyber-muted">Local-first configuration</p></div>
        <nav className="settings-tabs flex-1 space-y-1 px-2" aria-label="Seções das configurações">
          {TABS.map(({ id, label, icon: Icon }) => { const selected = activeTab === id; return <button type="button" key={id} onClick={() => setActiveTab(id)} className="settings-tab flex min-h-10 w-full items-center gap-2.5 rounded-md border px-3 text-left font-mono text-[11px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan/50" style={{ background: selected ? 'rgba(0,212,255,0.08)' : 'transparent', borderColor: selected ? 'rgba(0,212,255,0.25)' : 'transparent', color: selected ? '#00d4ff' : '#94a3b8' }} aria-current={selected ? 'page' : undefined}><Icon size={14} className="flex-shrink-0" /><span>{label}</span></button> })}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto p-6"><div className="mx-auto max-w-3xl"><ActiveTab /></div></main>
    </div>
  )
}

export default Settings
