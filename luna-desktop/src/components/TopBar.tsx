import React, { useState } from 'react'
import { useStore } from '@store/appStore'
import {
  Activity,
  BookMarked,
  ChevronDown,
  Circle,
  FolderOpen,
  PanelRight,
  ShieldCheck,
  Terminal,
  Trash2,
  Volume2,
} from 'lucide-react'

interface ModelDef {
  id: 'luna-cyber-fast' | 'qwen3.5:4b'
  label: string
  description: string
  accent: string
}

const LOCAL_MODELS: ModelDef[] = [
  {
    id: 'luna-cyber-fast',
    label: 'Luna Cyber Fast',
    description: 'Modelo local principal',
    accent: '#14f195',
  },
  {
    id: 'qwen3.5:4b',
    label: 'Qwen 3.5 4B',
    description: 'Fallback local compatível',
    accent: '#00d4ff',
  },
]

interface TopBarProps {
  title?: string
}

const TopBar: React.FC<TopBarProps> = ({ title = 'Chat' }) => {
  const {
    currentModel,
    setCurrentModel,
    backendStatus,
    executionPanelVisible,
    executionPanelAutoCollapsed,
    setExecutionPanelVisible,
    clearMessages,
    isStreaming,
    liveToolEvents,
    isSpeaking,
    voiceEnabled,
    activeFiles,
    workspaceName,
    workspacePath,
    projectMarkdown,
    userContext,
  } = useStore()
  const [showModels, setShowModels] = useState(false)
  const showChatControls = title.toLocaleLowerCase('pt-BR') === 'chat'

  const current = LOCAL_MODELS.find((model) => model.id === currentModel) ?? LOCAL_MODELS[0]
  const runningTools = liveToolEvents.filter((event) => event.status === 'running').length
  const hasContextDoc = Boolean(workspacePath && projectMarkdown[workspacePath])
  const hasUserContext = Boolean(userContext.trim())
  const normalizedModels = backendStatus.availableModels.map((model) => model.replace(':latest', ''))
  const currentModelAvailable = normalizedModels.length === 0
    || normalizedModels.includes(currentModel.replace(':latest', ''))
  const runtimeOnline = backendStatus.connected && backendStatus.ollama && currentModelAvailable
  const runtimeLabel = !backendStatus.connected
    ? 'Backend'
    : !backendStatus.ollama
      ? 'Ollama'
      : currentModelAvailable
        ? 'Ollama'
        : 'Modelo ausente'
  const runtimeTitle = !backendStatus.connected
    ? backendStatus.error || 'Backend local indisponível'
    : !backendStatus.ollama
      ? 'Ollama indisponível em localhost:11434'
      : currentModelAvailable
        ? `${current.label} disponível no Ollama local`
        : `${current.label} não foi encontrado no Ollama local`
  const panelEffectivelyVisible = executionPanelVisible && !executionPanelAutoCollapsed

  return (
    <header
      className="topbar-local relative flex-shrink-0"
      style={{
        background: 'rgba(5,8,16,0.97)',
        borderBottom: isStreaming
          ? '1px solid rgba(0,212,255,0.35)'
          : '1px solid rgba(0,212,255,0.1)',
        boxShadow: isStreaming
          ? '0 2px 12px rgba(0,212,255,0.06)'
          : '0 1px 0 rgba(0,212,255,0.03)',
      }}
    >
      {isStreaming ? (
        <div className="absolute inset-x-0 bottom-0 h-px overflow-hidden" aria-hidden="true">
          <div className="h-full w-2/5 bg-gradient-to-r from-transparent via-cyber-cyan to-transparent [animation:topbar-scan_2s_linear_infinite]" />
        </div>
      ) : null}

      <div className="flex h-[54px] items-center justify-between gap-3 px-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="topbar-title flex-shrink-0 font-mono text-sm font-semibold tracking-[0.12em] text-cyber-text">
            {title.toUpperCase()}
          </span>
          <span className="inline-flex flex-shrink-0 items-center gap-1 rounded-full border border-cyber-green/25 bg-cyber-green/10 px-2 py-0.5 font-mono text-[9px] font-semibold text-cyber-green">
            <ShieldCheck size={10} />
            LOCAL
          </span>

          <div
            className="topbar-status inline-flex flex-shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-[10px]"
            style={{
              borderColor: runtimeOnline ? 'rgba(20,241,149,0.2)' : 'rgba(239,68,68,0.22)',
              background: runtimeOnline ? 'rgba(20,241,149,0.06)' : 'rgba(239,68,68,0.06)',
              color: runtimeOnline ? '#14f195' : '#f87171',
            }}
            title={runtimeTitle}
          >
            <Circle size={7} fill="currentColor" />
            <span>{runtimeLabel}</span>
          </div>

          {isStreaming ? (
            <div className="inline-flex flex-shrink-0 items-center gap-1.5 rounded-full border border-cyber-cyan/25 bg-cyber-cyan/10 px-2 py-0.5 font-mono text-[10px] text-cyber-cyan">
              <Activity size={9} className="animate-pulse" />
              {runningTools > 0 ? `${runningTools} operação${runningTools > 1 ? 'ões' : ''}` : 'gerando'}
            </div>
          ) : null}

          {workspaceName ? (
            <button
              type="button"
              onClick={() => setExecutionPanelVisible(true)}
              className="topbar-workspace inline-flex max-w-[150px] flex-shrink items-center gap-1.5 rounded-md border border-cyber-cyan/15 bg-cyber-cyan/5 px-2 py-1 font-mono text-[10px] text-cyber-muted transition-colors hover:border-cyber-cyan/30 hover:text-cyber-cyan focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan/50"
              title={workspacePath}
            >
              <FolderOpen size={10} className="flex-shrink-0" />
              <span className="truncate">{workspaceName}</span>
              {activeFiles.length > 0 ? (
                <span className="rounded-full bg-cyber-cyan/15 px-1 text-[8px] text-cyber-cyan">
                  {activeFiles.length}
                </span>
              ) : null}
            </button>
          ) : null}

          {hasContextDoc ? (
            <button
              type="button"
              onClick={() => setExecutionPanelVisible(true)}
              className="topbar-context rounded-md border border-purple-400/20 bg-purple-400/10 p-1 text-purple-300 transition-colors hover:border-purple-400/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/50"
              aria-label="Abrir contexto do workspace"
              title="Contexto do workspace carregado"
            >
              <BookMarked size={11} />
            </button>
          ) : null}

          {hasUserContext ? (
            <span
              className="topbar-context inline-flex items-center gap-1 rounded-md border border-emerald-400/20 bg-emerald-400/5 px-1.5 py-1 font-mono text-[9px] text-emerald-300"
              title={userContext}
            >
              <Terminal size={9} /> contexto
            </span>
          ) : null}

          {voiceEnabled && isSpeaking ? (
            <span className="topbar-context text-cyber-cyan" title="Resposta em áudio">
              <Volume2 size={12} className="animate-pulse" />
            </span>
          ) : null}
        </div>

        <div className="flex flex-shrink-0 items-center gap-2">
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowModels((visible) => !visible)}
              className="inline-flex min-h-8 items-center gap-2 rounded-md border px-2.5 py-1 font-mono text-[11px] transition-colors hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan/50"
              style={{
                borderColor: `${current.accent}40`,
                background: `${current.accent}0d`,
                color: current.accent,
              }}
              aria-haspopup="listbox"
              aria-expanded={showModels}
            >
              <span className="topbar-model-label">{current.label}</span>
              <ChevronDown size={12} />
            </button>

            {showModels ? (
              <>
                <button
                  type="button"
                  className="fixed inset-0 z-40 cursor-default"
                  onClick={() => setShowModels(false)}
                  aria-label="Fechar seletor de modelo"
                />
                <div
                  className="absolute right-0 top-full z-50 mt-1 w-64 overflow-hidden rounded-xl border border-cyber-cyan/20 bg-[#0a0f1e] shadow-lg shadow-black/50"
                  role="listbox"
                  aria-label="Modelos locais"
                >
                  <div className="border-b border-cyber-cyan/10 px-3 py-2">
                    <p className="font-mono text-[9px] font-semibold text-cyber-cyan">MODELOS LOCAIS</p>
                    <p className="mt-0.5 text-[9px] text-cyber-muted">Sem custo por mensagem e sem API key</p>
                  </div>
                  {LOCAL_MODELS.map((model) => (
                    <button
                      type="button"
                      key={model.id}
                      role="option"
                      aria-selected={model.id === current.id}
                      onClick={() => {
                        setCurrentModel(model.id)
                        setShowModels(false)
                      }}
                      className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-white/[0.04] focus-visible:outline-none focus-visible:bg-white/[0.06]"
                      style={{ background: model.id === current.id ? `${model.accent}0d` : undefined }}
                    >
                      <span
                        className="h-1.5 w-1.5 flex-shrink-0 rounded-full"
                        style={{ background: model.accent, boxShadow: model.id === current.id ? `0 0 6px ${model.accent}` : undefined }}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block font-mono text-[11px] text-cyber-text">{model.label}</span>
                        <span className="mt-0.5 block text-[9px] text-cyber-muted">{model.description}</span>
                      </span>
                      {model.id === current.id ? (
                        <span className="font-mono text-[8px] text-cyber-green">ATIVO</span>
                      ) : null}
                    </button>
                  ))}
                </div>
              </>
            ) : null}
          </div>

          {showChatControls ? <button
            type="button"
            onClick={clearMessages}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-red-400/10 bg-red-400/5 text-cyber-muted transition-colors hover:border-red-400/25 hover:text-red-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/50"
            aria-label="Limpar conversa"
            title="Limpar conversa"
          >
            <Trash2 size={13} />
          </button> : null}

          {showChatControls ? <button
            type="button"
            onClick={() => setExecutionPanelVisible(!executionPanelVisible)}
            className="inline-flex h-8 items-center justify-center gap-1.5 rounded-md border px-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan/50"
            style={{
              background: panelEffectivelyVisible ? 'rgba(0,212,255,0.12)' : 'rgba(0,212,255,0.04)',
              borderColor: panelEffectivelyVisible ? 'rgba(0,212,255,0.35)' : 'rgba(0,212,255,0.1)',
              color: panelEffectivelyVisible ? '#00d4ff' : '#64748b',
            }}
            aria-label={executionPanelAutoCollapsed ? 'Painel de execução recolhido automaticamente' : executionPanelVisible ? 'Ocultar painel de execução' : 'Mostrar painel de execução'}
            title={executionPanelAutoCollapsed ? 'Painel recolhido automaticamente nesta largura' : executionPanelVisible ? 'Ocultar painel de execução' : 'Mostrar painel de execução'}
          >
            <PanelRight size={13} />
            <span className="topbar-panel-label font-mono text-[9px]">Execução</span>
          </button> : null}
        </div>
      </div>
    </header>
  )
}

export default TopBar
