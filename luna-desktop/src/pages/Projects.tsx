import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import TopBar from '@components/TopBar'
import { useStore, Project, ProjectMessage } from '@store/appStore'
import {
  FolderKanban, Plus, FolderOpen, Pin, Trash2, Brain,
  ChevronLeft, ChevronRight, Send, Square, X,
} from 'lucide-react'

// ── Helpers ───────────────────────────────────────────────────────────────────

function relativeTime(value: string): string {
  const date = new Date(value)
  if (isNaN(date.getTime())) return '—'
  const diff = Date.now() - date.getTime()
  const sec = Math.max(1, Math.floor(diff / 1000))
  if (sec < 60) return 'há poucos segundos'
  const min = Math.floor(sec / 60)
  if (min < 60) return `há ${min} min`
  const h = Math.floor(min / 60)
  if (h < 24) return `há ${h} h`
  const d = Math.floor(h / 24)
  return `há ${d} dia${d > 1 ? 's' : ''}`
}

const BORDER_COLOR: Record<string, string> = {
  cyan: '#00d4ff', purple: '#7c3aed', green: '#10b981', orange: '#f59e0b', red: '#ef4444',
}

// ── Typing indicator ──────────────────────────────────────────────────────────

const TypingIndicator = () => (
  <div className="flex items-end gap-2 mb-2">
    <div
      className="w-6 h-6 rounded-full flex items-center justify-center text-xs flex-shrink-0"
      style={{ background: 'linear-gradient(135deg, #7c3aed, #00d4ff)' }}
    >
      🌙
    </div>
    <div className="rounded-xl px-3 py-2 border" style={{ background: 'rgba(0,212,255,0.04)', borderColor: 'rgba(0,212,255,0.15)' }}>
      <div className="flex items-center gap-1">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="w-1.5 h-1.5 rounded-full"
            style={{
              background: '#00d4ff',
              animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
              opacity: 0.7,
            }}
          />
        ))}
      </div>
    </div>
  </div>
)

// ── Message bubble ────────────────────────────────────────────────────────────

const MessageBubble = ({ message, isStreaming }: { message: ProjectMessage; isStreaming?: boolean }) => {
  const isUser = message.role === 'user'
  const isSystem = message.role === 'system'
  const border = BORDER_COLOR.cyan

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      {!isUser && !isSystem && (
        <div
          className="w-6 h-6 rounded-full flex items-center justify-center text-xs flex-shrink-0 mr-2 self-end mb-0.5"
          style={{ background: 'linear-gradient(135deg, #7c3aed, #00d4ff)' }}
        >
          🌙
        </div>
      )}
      <div className={`max-w-[85%] ${isSystem ? 'w-full' : ''}`}>
        <div
          className="rounded-xl px-3 py-2 border text-[13px]"
          style={{
            background: isUser
              ? 'rgba(124, 58, 237, 0.18)'
              : isSystem
              ? 'rgba(255,255,255,0.02)'
              : 'rgba(0,212,255,0.04)',
            borderColor: isUser ? 'rgba(124,58,237,0.3)' : 'rgba(0, 212, 255, 0.15)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {message.is_compressed
            ? <span className="text-cyber-muted italic">[Contexto comprimido: {message.original_count} msgs]</span>
            : message.content}
          {isStreaming && !message.content && null}
          {isStreaming && message.content && (
            <span
              className="inline-block w-1.5 h-[1em] ml-0.5 align-text-bottom"
              style={{ background: border, animation: 'pulse 1s ease-in-out infinite' }}
            />
          )}
        </div>
        <div className={`text-[10px] text-cyber-dim mt-0.5 ${isUser ? 'text-right' : 'text-left'}`}>
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
      {isUser && (
        <div
          className="w-6 h-6 rounded-full ml-2 flex items-center justify-center text-xs flex-shrink-0 self-end mb-0.5 font-bold"
          style={{ background: 'rgba(124,58,237,0.3)', border: '1px solid rgba(124,58,237,0.4)', color: '#e2e8f0' }}
        >
          C
        </div>
      )}
    </div>
  )
}

// ── Compression progress bar ──────────────────────────────────────────────────

const CompressBar = ({ progress, message }: { progress: number; message: string }) => (
  <div
    className="mx-4 mb-2 px-3 py-2 rounded-xl text-xs font-mono flex items-center gap-3"
    style={{ background: 'rgba(124,58,237,0.08)', border: '1px solid rgba(124,58,237,0.2)' }}
  >
    <div className="flex-1">
      <div className="text-purple-300 mb-1">{message}</div>
      <div className="h-1 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.08)' }}>
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${progress}%`, background: 'linear-gradient(90deg, #7c3aed, #00d4ff)' }}
        />
      </div>
    </div>
    <span className="text-purple-300">{progress}%</span>
  </div>
)

// ── Main Projects page ────────────────────────────────────────────────────────

const Projects: React.FC = () => {
  const navigate = useNavigate()
  const {
    backendUrl, currentModel, userId, lunaApiToken, zeroCloudMode,
    projects, activeProjectId, projectMessages,
    setProjects, setActiveProject, setProjectMessages, addProjectMessage, updateProjectMessage,
    setWorkspace, setProjectContext, setRightPanelTab, addActiveFile,
  } = useStore()

  const [loading, setLoading]           = useState(false)
  const [sending, setSending]           = useState(false)
  const [input, setInput]               = useState('')
  const [facts, setFacts]               = useState<string[]>([])
  const [contextText, setContextText]   = useState('')
  const [newFact, setNewFact]           = useState('')
  const [showCreate, setShowCreate]     = useState(false)
  const [sidebarOpen, setSidebarOpen]   = useState(true)
  const [fetchError, setFetchError]     = useState<string | null>(null)
  const [compressing, setCompressing]   = useState(false)
  const [compressProgress, setCompressProgress] = useState(0)
  const [compressMsg, setCompressMsg]   = useState('')
  const [streamingMsgId, setStreamingMsgId] = useState<number | null>(null)
  const [createForm, setCreateForm]     = useState({
    name: '', path: '', project_type: 'other', description: '', color: 'cyan',
  })

  const abortRef        = useRef<AbortController | null>(null)
  const toolCounterRef  = useRef(0)
  const messagesEndRef  = useRef<HTMLDivElement>(null)

  const activeProject  = useMemo(
    () => projects.find((p) => p.id === activeProjectId) ?? null,
    [projects, activeProjectId],
  )
  const activeMessages = activeProjectId ? (projectMessages[activeProjectId] ?? []) : []

  // ── Auto-scroll ──────────────────────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [activeMessages.length, sending])

  // ── Cleanup abort on unmount ─────────────────────────────────────────────
  useEffect(() => {
    return () => { abortRef.current?.abort() }
  }, [])

  // ── Data fetchers ────────────────────────────────────────────────────────
  const fetchProjects = useCallback(async () => {
    try {
      setFetchError(null)
      const res = await fetch(`${backendUrl}/api/projects`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setProjects(data.projects ?? [])
    } catch (e: any) {
      setFetchError('Não foi possível carregar projetos. Backend online?')
    }
  }, [backendUrl, setProjects])

  const fetchMessages = useCallback(async (projectId: number) => {
    try {
      const res = await fetch(`${backendUrl}/api/projects/${projectId}/messages`)
      const data = await res.json()
      setProjectMessages(projectId, data.messages ?? [])
    } catch { /* silent */ }
  }, [backendUrl, setProjectMessages])

  const fetchFacts = useCallback(async (projectId: number) => {
    try {
      const res = await fetch(`${backendUrl}/api/projects/${projectId}/facts`)
      const data = await res.json()
      setFacts(data.facts ?? [])
    } catch { /* silent */ }
  }, [backendUrl])

  const fetchContext = useCallback(async (projectId: number) => {
    try {
      const res = await fetch(`${backendUrl}/api/projects/${projectId}/context`)
      const data = await res.json()
      setContextText(data.context ?? '')
    } catch { /* silent */ }
  }, [backendUrl])

  useEffect(() => { fetchProjects() }, [fetchProjects])

  useEffect(() => {
    if (!activeProjectId) {
      setFacts([])
      setContextText('')
      return
    }
    fetchMessages(activeProjectId)
    fetchFacts(activeProjectId)
    fetchContext(activeProjectId)
  }, [activeProjectId, fetchMessages, fetchFacts, fetchContext])

  // ── Create project ───────────────────────────────────────────────────────
  const createProject = async () => {
    if (!createForm.name.trim()) return
    setLoading(true)
    try {
      const res = await fetch(`${backendUrl}/api/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(createForm),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      await fetchProjects()
      setShowCreate(false)
      setCreateForm({ name: '', path: '', project_type: 'other', description: '', color: 'cyan' })
      // Auto-select the new project
      if (data.id) setActiveProject(data.id)
    } catch { /* silent */ }
    finally { setLoading(false) }
  }

  // ── Stop streaming ───────────────────────────────────────────────────────
  const stopStream = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setSending(false)
    setStreamingMsgId(null)
  }, [])

  // ── Send message ─────────────────────────────────────────────────────────
  const sendProjectMessage = useCallback(async () => {
    if (!activeProject || !input.trim() || sending) return
    const content = input.trim()
    setInput('')
    setSending(true)
    toolCounterRef.current = 0

    // Save user message to backend
    let userBackendId: number | undefined
    try {
      const savedUser = await fetch(`${backendUrl}/api/projects/${activeProject.id}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: 'user', content, model: currentModel }),
      }).then((r) => r.json())
      userBackendId = savedUser.id
    } catch { /* continue without persisted ID */ }

    const userMsg: ProjectMessage = {
      id: userBackendId ?? Date.now(),
      project_id: activeProject.id,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
      model: currentModel,
      is_compressed: false,
      original_count: 1,
    }
    addProjectMessage(activeProject.id, userMsg)

    // Luna placeholder
    const lunaId = Date.now() + 1
    setStreamingMsgId(lunaId)
    addProjectMessage(activeProject.id, {
      id: lunaId,
      project_id: activeProject.id,
      role: 'luna',
      content: '',
      timestamp: new Date().toISOString(),
      model: currentModel,
      is_compressed: false,
      original_count: 1,
    })

    try {
      abortRef.current = new AbortController()
      const res = await fetch(`${backendUrl}/chat/agent/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(lunaApiToken ? { 'X-Luna-Token': lunaApiToken } : {}),
        },
        body: JSON.stringify({
          message: content,
          session_id: `project-${activeProject.id}`,
          user_id: userId || undefined,
          model: currentModel,
          workspace_path: activeProject.path || null,
          zero_cloud_mode: zeroCloudMode,
        }),
        signal: abortRef.current.signal,
      })

      if (!res.ok) throw new Error(`Backend error: ${res.status}`)
      const reader = res.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer   = ''
      let fullText = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (!raw || raw === '[DONE]') continue

          try {
            const event = JSON.parse(raw)

            if (event.type === 'tool_start') {
              // count tools but keep it lightweight — no full toolbar in projects
              toolCounterRef.current++
            }

            else if (event.type === 'tool_done') {
              if (event.name === 'save_context' && event.key) {
                setProjectContext(event.key, event.value ?? '')
                setRightPanelTab('context')
              }
            }

            else if (event.type === 'tool_skipped') {
              // Silently handle — tool was skipped by engine guardrail
            }

            else if (event.type === 'text_chunk') {
              fullText += event.text
              updateProjectMessage(activeProject.id, lunaId, { content: fullText })
            }

            else if (event.type === 'done') {
              const finalText = fullText || event.final_text || ''
              updateProjectMessage(activeProject.id, lunaId, { content: finalText })
              setStreamingMsgId(null)
              // Persist Luna response to backend
              try {
                const saved = await fetch(`${backendUrl}/api/projects/${activeProject.id}/messages`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ role: 'luna', content: finalText, model: currentModel }),
                }).then((r) => r.json())
                if (saved.id) updateProjectMessage(activeProject.id, lunaId, { id: saved.id })
              } catch { /* persist failed — message visible in UI regardless */ }
            }

            else if (event.type === 'compressing') {
              const prog = (event.progress as number) ?? 0
              const msg  = (event.message as string)  ?? 'Compactando contexto...'
              setCompressing(prog < 100)
              setCompressProgress(prog)
              setCompressMsg(msg)
              if (prog >= 100) setTimeout(() => setCompressing(false), 1500)
            }

            else if (event.type === 'file_accessed') {
              const filePath: string = event.path ?? ''
              if (filePath) {
                const wp = activeProject.path
                const absPath = (wp && !filePath.startsWith('/') && !filePath.match(/^[A-Za-z]:/))
                  ? `${wp}/${filePath}`.replace(/\/+/g, '/')
                  : filePath
                addActiveFile({ path: absPath, operation: (event.operation ?? 'read'), timestamp: Date.now() })
              }
            }

            else if (event.type === 'dir_access') {
              addProjectMessage(activeProject.id, {
                id: Date.now() + Math.floor(Math.random() * 9999),
                project_id: activeProject.id,
                role: 'system',
                content: `📂 Luna acessou diretório: ${event.path ?? ''} (fora do workspace atual)`,
                timestamp: new Date().toISOString(),
                model: '',
                is_compressed: false,
                original_count: 1,
              })
            }

            else if (event.type === 'frontend_action' && event.__action__ === 'open_workspace_dialog') {
              const api = window.electronAPI?.workspace
              if (api) {
                const result = await api.openFolderDialog()
                if (!result.canceled && result.filePaths[0]) {
                  const path = result.filePaths[0]
                  const name = path.split(/[\\/]/).filter(Boolean).pop() ?? path
                  setWorkspace(path, name)
                  addProjectMessage(activeProject.id, {
                    id: Date.now() + 2,
                    project_id: activeProject.id,
                    role: 'system',
                    content: `✅ Workspace configurado: ${path}`,
                    timestamp: new Date().toISOString(),
                    model: '',
                    is_compressed: false,
                    original_count: 1,
                  })
                }
              }
            }

            else if (event.type === 'frontend_action' && event.__action__ === 'project_context_updated') {
              setRightPanelTab('context')
            }

            else if (event.type === 'error') {
              updateProjectMessage(activeProject.id, lunaId, {
                content: `⚠️ Erro: ${event.message}`,
              })
              setStreamingMsgId(null)
            }
          } catch { /* JSON parse error — ignore */ }
        }
      }
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        updateProjectMessage(activeProject.id, lunaId, {
          content: `⚠️ Erro de conexão com o backend. Verifique se Luna está rodando em ${backendUrl}`,
        })
      }
      setStreamingMsgId(null)
    } finally {
      setSending(false)
      abortRef.current = null
      // Refresh facts and context after response
      fetchFacts(activeProject.id)
      fetchContext(activeProject.id)
    }
  }, [
    activeProject, input, sending, backendUrl, currentModel, lunaApiToken, userId, zeroCloudMode,
    addProjectMessage, updateProjectMessage, setProjectContext, setRightPanelTab, addActiveFile,
    setWorkspace, fetchFacts, fetchContext,
  ])

  // ── Keyboard submit ──────────────────────────────────────────────────────
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendProjectMessage()
    }
  }

  // ── Fact management ──────────────────────────────────────────────────────
  const addFact = async () => {
    if (!activeProjectId || !newFact.trim()) return
    try {
      await fetch(`${backendUrl}/api/projects/${activeProjectId}/facts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fact: newFact.trim() }),
      })
      setNewFact('')
      fetchFacts(activeProjectId)
    } catch { /* silent */ }
  }

  const compressProject = async (projectId: number) => {
    try {
      await fetch(`${backendUrl}/api/projects/${projectId}/compress`, { method: 'POST' })
      fetchMessages(projectId)
      fetchContext(projectId)
    } catch { /* silent */ }
  }

  const deleteProject = async (projectId: number) => {
    try {
      await fetch(`${backendUrl}/api/projects/${projectId}`, { method: 'DELETE' })
      if (activeProjectId === projectId) setActiveProject(null)
      fetchProjects()
    } catch { /* silent */ }
  }

  const togglePin = async (project: Project) => {
    try {
      await fetch(`${backendUrl}/api/projects/${project.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pinned: !project.pinned }),
      })
      fetchProjects()
    } catch { /* silent */ }
  }

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full min-h-0">
      <TopBar title="Projects" />

      <div className="flex flex-1 min-h-0" style={{ background: 'rgba(10, 15, 28, 0.95)' }}>

        {/* ── Left: Project list ─────────────────────────────────────── */}
        <div
          className={`${sidebarOpen ? 'min-w-[220px] max-w-[280px] w-[260px]' : 'w-[52px]'} flex-shrink-0 border-r flex flex-col transition-all duration-200`}
          style={{ borderColor: 'rgba(0, 212, 255, 0.15)' }}
        >
          <div
            className="flex items-center justify-between px-3 py-3 border-b"
            style={{ borderColor: 'rgba(0, 212, 255, 0.15)' }}
          >
            {sidebarOpen && (
              <div className="flex items-center gap-2 text-cyber-cyan font-semibold text-sm">
                <FolderKanban size={15} />
                <span>Projetos</span>
              </div>
            )}
            <div className={`flex items-center gap-1.5 ${sidebarOpen ? '' : 'mx-auto'}`}>
              {sidebarOpen && (
                <button
                  onClick={() => setShowCreate(true)}
                  className="w-6 h-6 rounded-md flex items-center justify-center transition-colors"
                  style={{ background: 'rgba(0,212,255,0.08)', color: '#00d4ff' }}
                  title="Novo projeto"
                >
                  <Plus size={14} />
                </button>
              )}
              <button
                onClick={() => setSidebarOpen((v) => !v)}
                className="w-6 h-6 rounded-md flex items-center justify-center text-cyber-muted transition-colors"
                style={{ background: 'rgba(255,255,255,0.03)' }}
              >
                {sidebarOpen ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
              </button>
            </div>
          </div>

          {fetchError && sidebarOpen && (
            <div className="mx-2 mt-2 px-2 py-1.5 rounded-lg text-[11px] text-red-400" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
              {fetchError}
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
            {projects.length === 0 && sidebarOpen && !fetchError && (
              <div className="text-center py-6 text-cyber-muted text-xs">
                Nenhum projeto ainda.<br />
                <button onClick={() => setShowCreate(true)} className="text-cyber-cyan mt-1">Criar o primeiro</button>
              </div>
            )}
            {projects.map((project) => {
              const active = activeProjectId === project.id
              const border = BORDER_COLOR[project.color] ?? '#00d4ff'
              const msgCount = (projectMessages[project.id] ?? []).length
              return (
                <div
                  key={project.id}
                  onClick={() => setActiveProject(project.id)}
                  className="cursor-pointer rounded-xl border transition-all"
                  style={{
                    background: active ? 'rgba(0,212,255,0.04)' : 'rgba(255,255,255,0.015)',
                    borderColor: active ? 'rgba(0,212,255,0.35)' : 'rgba(0,212,255,0.1)',
                    borderLeft: `3px solid ${border}`,
                    boxShadow: active ? `0 0 16px rgba(0,212,255,0.08)` : 'none',
                  }}
                >
                  {sidebarOpen ? (
                    <div className="p-2.5">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="font-semibold text-[13px] truncate" style={{ color: border }}>
                            {project.name}
                          </div>
                          <div className="text-[11px] text-cyber-muted mt-0.5 capitalize">{project.project_type}</div>
                        </div>
                        <div className="flex gap-1 flex-shrink-0">
                          <button
                            onClick={(e) => { e.stopPropagation(); togglePin(project) }}
                            className="transition-colors"
                            style={{ color: project.pinned ? '#f59e0b' : 'rgba(255,255,255,0.25)' }}
                            title={project.pinned ? 'Desafixar' : 'Fixar'}
                          >
                            <Pin size={12} />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              if (window.confirm(`Excluir "${project.name}"?`)) deleteProject(project.id)
                            }}
                            className="text-red-400 transition-colors"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>
                      {project.path && (
                        <div className="mt-1.5 flex items-center gap-1 text-[10px] text-cyber-dim truncate">
                          <FolderOpen size={10} />
                          <span className="truncate">{project.path}</span>
                        </div>
                      )}
                      <div className="mt-1.5 flex items-center justify-between text-[10px] text-cyber-dim">
                        <span>{relativeTime(project.last_session_at)}</span>
                        <span>{project.session_count} sessões</span>
                      </div>
                      {msgCount > 20 && (
                        <button
                          onClick={(e) => { e.stopPropagation(); compressProject(project.id) }}
                          className="mt-1.5 text-[10px] font-medium transition-colors"
                          style={{ color: '#a78bfa' }}
                        >
                          Comprimir contexto ({msgCount} msgs)
                        </button>
                      )}
                    </div>
                  ) : (
                    <div
                      className="flex items-center justify-center py-3"
                      title={project.name}
                    >
                      <div
                        className="w-2 h-2 rounded-full"
                        style={{ background: border, boxShadow: active ? `0 0 6px ${border}` : 'none' }}
                      />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* ── Center: Chat ───────────────────────────────────────────── */}
        <div className="flex-1 min-w-0 flex flex-col border-r" style={{ borderColor: 'rgba(0, 212, 255, 0.15)', minWidth: '400px' }}>
          {activeProject ? (
            <>
              {/* Header */}
              <div className="px-4 py-3 border-b flex-shrink-0" style={{ borderColor: 'rgba(0, 212, 255, 0.15)' }}>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-cyber-cyan font-semibold text-sm">{activeProject.name}</div>
                    <div className="text-[11px] text-cyber-muted mt-0.5">
                      {activeProject.project_type} · {activeProject.path || 'sem pasta definida'}
                    </div>
                  </div>
                  <div className="text-[11px] text-cyber-dim">{activeMessages.length} msgs</div>
                </div>
              </div>

              {/* Compression progress */}
              {compressing && <CompressBar progress={compressProgress} message={compressMsg} />}

              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-4 pt-4 pb-2">
                {activeMessages.length === 0 && !sending && (
                  <div className="flex items-center justify-center h-full text-center">
                    <div>
                      <FolderKanban size={32} className="mx-auto text-cyber-muted mb-3 opacity-50" />
                      <p className="text-cyber-muted text-sm">Inicie uma conversa com Luna neste projeto.</p>
                      <p className="text-cyber-dim text-xs mt-1">O contexto é isolado e persistente.</p>
                    </div>
                  </div>
                )}
                {activeMessages.map((message) => (
                  <MessageBubble
                    key={message.id}
                    message={message}
                    isStreaming={streamingMsgId === message.id}
                  />
                ))}
                {sending && streamingMsgId === null && <TypingIndicator />}
                <div ref={messagesEndRef} />
              </div>

              {/* Input */}
              <div className="p-3 border-t flex-shrink-0" style={{ borderColor: 'rgba(0, 212, 255, 0.15)' }}>
                <div className="flex gap-2 items-end">
                  <textarea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    rows={2}
                    placeholder="Converse com Luna neste projeto… (Enter envia)"
                    className="flex-1 rounded-xl px-3 py-2 outline-none resize-none text-[13px] text-white"
                    style={{
                      background: 'rgba(0, 212, 255, 0.03)',
                      border: '1px solid rgba(0, 212, 255, 0.15)',
                      minHeight: '60px',
                    }}
                    disabled={sending}
                  />
                  {sending ? (
                    <button
                      onClick={stopStream}
                      className="flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center font-medium transition-colors"
                      style={{ background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444' }}
                      title="Parar"
                    >
                      <Square size={14} />
                    </button>
                  ) : (
                    <button
                      onClick={sendProjectMessage}
                      disabled={!input.trim()}
                      className="flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center font-medium transition-colors disabled:opacity-40"
                      style={{ background: '#00d4ff', color: '#081019' }}
                      title="Enviar (Enter)"
                    >
                      <Send size={14} />
                    </button>
                  )}
                </div>
                <div className="text-[10px] text-cyber-dim mt-1.5 px-1">
                  Sessão: project-{activeProject.id} · modelo: {currentModel}
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-center px-8">
              <div>
                <FolderKanban size={40} className="mx-auto text-cyber-muted mb-4 opacity-40" />
                <h2 className="text-cyber-cyan text-lg font-semibold">Selecione um projeto</h2>
                <p className="text-cyber-muted text-sm mt-2 max-w-sm">
                  Crie ou escolha um projeto para iniciar um chat isolado com memória persistente.
                </p>
                <button
                  onClick={() => setShowCreate(true)}
                  className="mt-4 px-4 py-2 rounded-xl text-sm font-medium"
                  style={{ background: 'rgba(0,212,255,0.08)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.2)' }}
                >
                  + Criar primeiro projeto
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ── Right: Context panel ───────────────────────────────────── */}
        <div className="w-[240px] flex-shrink-0 flex flex-col min-h-0">
          <div className="px-4 py-3 border-b flex-shrink-0" style={{ borderColor: 'rgba(0, 212, 255, 0.15)' }}>
            <div className="flex items-center gap-2 font-semibold text-sm" style={{ color: '#a78bfa' }}>
              <Brain size={15} />
              Contexto
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-4">

            {/* Facts */}
            <div>
              <div className="text-[10px] uppercase tracking-wider text-cyber-dim mb-2">Fatos conhecidos</div>
              {facts.length === 0 ? (
                <div className="text-[12px] text-cyber-dim italic">Nenhum fato ainda.</div>
              ) : (
                <div className="space-y-1.5">
                  {facts.map((fact, idx) => (
                    <div
                      key={`${fact}-${idx}`}
                      className="rounded-lg px-2.5 py-1.5 text-xs"
                      style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(0,212,255,0.12)' }}
                    >
                      {fact}
                    </div>
                  ))}
                </div>
              )}

              {activeProject && (
                <div className="mt-2 space-y-1.5">
                  <input
                    value={newFact}
                    onChange={(e) => setNewFact(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && addFact()}
                    placeholder="Adicionar fato…"
                    className="w-full rounded-lg px-2.5 py-1.5 text-xs outline-none text-white"
                    style={{ background: 'rgba(0,212,255,0.03)', border: '1px solid rgba(0,212,255,0.15)' }}
                  />
                  <div className="flex gap-1.5">
                    <button
                      onClick={addFact}
                      className="flex-1 rounded-lg py-1.5 text-xs font-medium"
                      style={{ background: 'rgba(124,58,237,0.15)', color: '#c4b5fd' }}
                    >
                      Salvar
                    </button>
                    <button
                      onClick={() => activeProjectId && fetchFacts(activeProjectId)}
                      className="flex-1 rounded-lg py-1.5 text-xs font-medium"
                      style={{ background: 'rgba(0,212,255,0.06)', color: '#00d4ff' }}
                    >
                      Atualizar
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Stats */}
            {activeProject && (
              <div>
                <div className="text-[10px] uppercase tracking-wider text-cyber-dim mb-2">Estatísticas</div>
                <div className="space-y-1 text-xs text-cyber-muted">
                  <div className="flex justify-between">
                    <span>Sessões</span>
                    <span className="text-cyber-text">{activeProject.session_count}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Mensagens</span>
                    <span className="text-cyber-text">{activeMessages.length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Última atividade</span>
                    <span className="text-cyber-text">{relativeTime(activeProject.last_session_at)}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Formatted context */}
            <div>
              <div className="text-[10px] uppercase tracking-wider text-cyber-dim mb-2">Contexto formatado</div>
              <div
                className="rounded-lg p-2.5 text-[11px] font-mono whitespace-pre-wrap max-h-[180px] overflow-y-auto"
                style={{ background: 'rgba(255,255,255,0.015)', border: '1px solid rgba(0,212,255,0.1)', color: '#8b949e', lineHeight: '1.5' }}
              >
                {contextText || 'Sem contexto ainda.'}
              </div>
            </div>

          </div>

          {/* Actions */}
          {activeProject && (
            <div className="p-3 border-t flex-shrink-0 space-y-1.5" style={{ borderColor: 'rgba(0,212,255,0.15)' }}>
              <button
                onClick={() => {
                  if (activeProject.path) {
                    const name = activeProject.path.split(/[\\/]/).filter(Boolean).pop() ?? activeProject.path
                    setWorkspace(activeProject.path, name)
                  }
                  navigate('/chat')
                }}
                className="w-full rounded-lg py-2 text-xs font-medium transition-colors"
                style={{ background: 'rgba(0,212,255,0.06)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.15)' }}
              >
                Abrir no Chat principal
              </button>
              <button
                onClick={() => {
                  if (activeProject.path) {
                    const name = activeProject.path.split(/[\\/]/).filter(Boolean).pop() ?? activeProject.path
                    setWorkspace(activeProject.path, name)
                  }
                  navigate('/workspace')
                }}
                className="w-full rounded-lg py-2 text-xs font-medium transition-colors"
                style={{ background: 'rgba(124,58,237,0.1)', color: '#c4b5fd', border: '1px solid rgba(124,58,237,0.2)' }}
              >
                Ver no Workspace
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── Create project modal ─────────────────────────────────────── */}
      {showCreate && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center px-4"
          style={{ background: 'rgba(0,0,0,0.6)' }}
          onClick={(e) => { if (e.target === e.currentTarget) setShowCreate(false) }}
        >
          <div
            className="w-full max-w-md rounded-2xl p-5"
            style={{ background: 'rgba(10, 15, 28, 0.99)', border: '1px solid rgba(0,212,255,0.18)' }}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-cyber-cyan">Novo projeto</h2>
              <button
                onClick={() => setShowCreate(false)}
                className="w-7 h-7 rounded-lg flex items-center justify-center text-cyber-muted transition-colors"
                style={{ background: 'rgba(255,255,255,0.04)' }}
              >
                <X size={14} />
              </button>
            </div>

            <div className="space-y-3">
              <input
                value={createForm.name}
                onChange={(e) => setCreateForm((s) => ({ ...s, name: e.target.value }))}
                placeholder="Nome do projeto *"
                autoFocus
                className="w-full rounded-xl px-3 py-2 text-sm text-white outline-none"
                style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.2)' }}
                onKeyDown={(e) => e.key === 'Enter' && !loading && createForm.name.trim() && createProject()}
              />

              <div className="grid grid-cols-3 gap-1.5">
                {['app', 'bounty', 'solana', 'script', 'research', 'other'].map((type) => (
                  <button
                    key={type}
                    onClick={() => setCreateForm((s) => ({ ...s, project_type: type }))}
                    className="rounded-lg px-2 py-1.5 text-xs font-medium capitalize transition-colors"
                    style={{
                      background: createForm.project_type === type ? 'rgba(0,212,255,0.1)' : 'rgba(255,255,255,0.02)',
                      border: `1px solid ${createForm.project_type === type ? 'rgba(0,212,255,0.3)' : 'rgba(0,212,255,0.1)'}`,
                      color: createForm.project_type === type ? '#00d4ff' : '#8b949e',
                    }}
                  >
                    {type}
                  </button>
                ))}
              </div>

              <input
                value={createForm.path}
                onChange={(e) => setCreateForm((s) => ({ ...s, path: e.target.value }))}
                placeholder="D:\\Dev\\meu-projeto (opcional)"
                className="w-full rounded-xl px-3 py-2 text-sm text-white outline-none font-mono"
                style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.15)' }}
              />

              <textarea
                value={createForm.description}
                onChange={(e) => setCreateForm((s) => ({ ...s, description: e.target.value }))}
                rows={2}
                placeholder="Descrição do projeto (opcional)"
                className="w-full rounded-xl px-3 py-2 text-sm text-white outline-none resize-none"
                style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.15)' }}
              />

              <div>
                <div className="text-[10px] uppercase tracking-wider text-cyber-dim mb-2">Cor</div>
                <div className="flex gap-2.5">
                  {(['cyan', 'purple', 'green', 'orange', 'red'] as const).map((color) => (
                    <button
                      key={color}
                      onClick={() => setCreateForm((s) => ({ ...s, color }))}
                      className="w-6 h-6 rounded-full border-2 transition-all"
                      style={{
                        background: BORDER_COLOR[color],
                        borderColor: createForm.color === color ? '#fff' : 'transparent',
                        transform: createForm.color === color ? 'scale(1.2)' : 'scale(1)',
                      }}
                      title={color}
                    />
                  ))}
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-1">
                <button
                  onClick={() => setShowCreate(false)}
                  className="px-4 py-2 rounded-lg text-sm text-cyber-muted transition-colors"
                  style={{ border: '1px solid rgba(255,255,255,0.08)' }}
                >
                  Cancelar
                </button>
                <button
                  disabled={loading || !createForm.name.trim()}
                  onClick={createProject}
                  className="px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
                  style={{ background: '#00d4ff', color: '#081019' }}
                >
                  {loading ? 'Criando…' : 'Criar projeto'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Projects
