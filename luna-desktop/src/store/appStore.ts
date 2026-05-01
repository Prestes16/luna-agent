import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// ── V4: Execution Log ──────────────────────────────────────────────────────
export type ExecCategory = 'BOUNTY' | 'SOLANA' | 'BROWSER' | 'SYSTEM' | 'CHAT'
export type ExecLevel    = 'info' | 'success' | 'warning' | 'error' | 'progress'

export interface ExecutionLogLine {
  id:        string
  timestamp: number
  category:  ExecCategory
  level:     ExecLevel
  text:      string
  toolName?: string
  toolId?:   string        // link para ToolCallEvent correspondente
  progress?: number        // 0-100 (quando level === 'progress')
  imageData?: string       // base64 sem prefixo (browser_screenshot)
  elapsed?:  number        // segundos (quando a tool concluiu)
}

// Deriva categoria a partir do nome da tool
export function toolCategory(name: string): ExecCategory {
  if (name.startsWith('bounty_') || name.startsWith('recon_') || name.startsWith('scan_') || name.startsWith('audit_'))
    return 'BOUNTY'
  if (name.startsWith('solana_') || name.startsWith('rust_') || name.startsWith('cpi_'))
    return 'SOLANA'
  if (name.startsWith('browser_'))
    return 'BROWSER'
  return 'SYSTEM'
}

let _logSeq = 0
export function makeLogId(): string {
  return `log-${Date.now().toString(36)}-${(++_logSeq).toString(36)}`
}

const _MAX_LOG_LINES = 500

export interface Message {
  id: string
  role: 'user' | 'luna' | 'system'
  content: string
  timestamp: number
  model?: string
  toolCalls?: ToolCallEvent[]
  isStreaming?: boolean
  images?: Array<{ dataUrl: string; name: string }>
}

export interface ToolCallEvent {
  id: string
  callNum: number
  name: string
  argsSummary: string
  status: 'running' | 'done' | 'error' | 'skipped'
  resultSummary?: string
  startedAt: number
  doneAt?: number
}

export interface ProjectContext {
  key: string
  value: string
  updatedAt: number
}

export interface ActiveFile {
  path: string
  operation: 'read' | 'write' | 'list'
  timestamp: number
}

export interface LessonStats {
  total_lessons: number
  by_type: Record<string, {
    total: number
    success: number
    partial: number
    failed: number
  }>
}

export interface Project {
  id: number
  name: string
  path: string
  project_type: 'app' | 'bounty' | 'solana' | 'script' | 'research' | 'other'
  description: string
  created_at: string
  updated_at: string
  last_session_at: string
  session_count: number
  color: 'cyan' | 'purple' | 'green' | 'orange' | 'red'
  pinned: boolean
}

export interface ProjectMessage {
  id: number
  project_id: number
  role: 'user' | 'luna' | 'system'
  content: string
  timestamp: string
  model: string
  is_compressed: boolean
  original_count: number
}

export interface BackendStatus {
  connected: boolean
  model: string
  version: string
}

export interface ChatSession {
  id: string          // backend session_id
  title: string       // auto-gerado da primeira mensagem do usuário
  messages: Message[] // histórico completo
  createdAt: number
  updatedAt: number
  workspaceName: string
  model: string
}

export interface AppState {
  sidebarCollapsed: boolean
  rightPanelOpen: boolean
  rightPanelTab: 'tools' | 'context' | 'stats'
  activePage: string

  // ── V4: Split Intelligence ─────────────────────────────────────────────
  splitRatio: number                   // 0.0–1.0, fração da largura do chat (padrão 0.5)
  executionPanelVisible: boolean       // toggle do painel de execução
  executionLog: ExecutionLogLine[]     // stream de logs ao vivo
  executionActiveCategory: ExecCategory | 'ALL'  // filtro ativo no painel

  // ── Chat sessions ──────────────────────────────────────────────────────
  chatSessions: ChatSession[]         // histórico de todas as sessões
  currentChatSessionId: string        // ID da sessão ativa (= sessionId do backend)

  createNewChat: () => void           // salva atual e abre chat limpo
  loadChatSession: (id: string) => void
  deleteChatSession: (id: string) => void
  archiveCurrentChat: () => void      // salva current messages → chatSessions

  messages: Message[]
  isStreaming: boolean
  currentStreamingId: string | null
  liveToolEvents: ToolCallEvent[]
  activeToolCount: number

  sessionId: string
  currentPath: string

  projects: Project[]
  activeProjectId: number | null
  projectMessages: Record<number, ProjectMessage[]>

  projectContexts: ProjectContext[]
  activeFiles: ActiveFile[]
  projectMarkdown: Record<string, string>
  lessonStats: LessonStats | null
  backendStatus: BackendStatus

  apiKey: string
  apiKeys: Record<string, string>
  currentModel: string
  backendUrl: string
  temperature: number
  maxTokens: number
  solanaWalletAddress: string
  locale: string
  workspacePath: string
  workspaceName: string
  voiceEnabled: boolean
  voiceId: string
  voiceSpeed: number
  voiceModel: string
  isSpeaking: boolean
  lunaApiToken: string
  userId: string
  userEmail: string
  zeroCloudMode: boolean

  setSidebarCollapsed: (v: boolean) => void
  setRightPanelOpen: (v: boolean) => void
  setRightPanelTab: (tab: 'tools' | 'context' | 'stats') => void
  setActivePage: (page: string) => void

  // ── V4 actions ────────────────────────────────────────────────────────
  setSplitRatio: (ratio: number) => void
  setExecutionPanelVisible: (v: boolean) => void
  addLogLine: (line: Omit<ExecutionLogLine, 'id' | 'timestamp'>) => void
  updateLogLine: (id: string, patch: Partial<ExecutionLogLine>) => void
  clearExecutionLog: (category?: ExecCategory) => void
  setExecutionActiveCategory: (cat: ExecCategory | 'ALL') => void

  // ── Contexto manual do usuário ────────────────────────────────────────
  userContext: string        // texto livre que o usuário digita para contextualizar Luna
  setUserContext: (v: string) => void

  addMessage: (msg: Message) => void
  updateMessage: (id: string, patch: Partial<Message>) => void
  clearMessages: () => void
  setIsStreaming: (v: boolean) => void
  setCurrentStreamingId: (id: string | null) => void

  addLiveToolEvent: (e: ToolCallEvent) => void
  updateLiveToolEvent: (id: string, patch: Partial<ToolCallEvent>) => void
  commitLiveToolsToMessage: (msgId: string) => void
  clearLiveToolEvents: () => void

  setCurrentPath: (path: string) => void
  setSessionId: (id: string) => void

  setProjects: (projects: Project[]) => void
  setActiveProject: (id: number | null) => void
  addProjectMessage: (projectId: number, msg: ProjectMessage) => void
  updateProjectMessage: (projectId: number, msgId: number, patch: Partial<ProjectMessage>) => void
  setProjectMessages: (projectId: number, msgs: ProjectMessage[]) => void
  clearProjectMessages: (projectId: number) => void

  setProjectContext: (key: string, value: string) => void
  removeProjectContext: (key: string) => void
  addActiveFile: (file: ActiveFile) => void
  clearActiveFiles: () => void
  setProjectMarkdown: (workspacePath: string, content: string) => void
  setLessonStats: (stats: LessonStats) => void
  setBackendStatus: (s: Partial<BackendStatus>) => void

  setApiKey: (provider: string, value: string) => void
  setApiKeys: (keys: Record<string, string>) => void
  setCurrentModel: (model: string) => void
  setBackendUrl: (url: string) => void
  setTemperature: (v: number) => void
  setMaxTokens: (v: number) => void
  setSolanaWalletAddress: (addr: string) => void
  setLocale: (l: string) => void
  setWorkspace: (path: string, name: string) => void
  clearWorkspace: () => void
  setVoiceEnabled: (v: boolean) => void
  setVoiceId: (id: string) => void
  setVoiceSpeed: (v: number) => void
  setVoiceModel: (m: string) => void
  setIsSpeaking: (v: boolean) => void
  setLunaApiToken: (token: string) => void
  setZeroCloudMode: (v: boolean) => void
  setUserId: (id: string) => void
  setUserEmail: (email: string) => void
}

// ── Helpers ────────────────────────────────────────────────────────────────
function _makeChatTitle(messages: Message[]): string {
  const first = messages.find((m) => m.role === 'user')
  if (!first) return 'Nova conversa'
  return first.content.slice(0, 48) + (first.content.length > 48 ? '…' : '')
}

const _INITIAL_SESSION_ID = `session-${Date.now().toString(36)}`
const _MAX_SESSIONS = 40         // máximo de sessões salvas
const _MAX_MSG_PER_SESSION = 200 // máximo de mensagens por sessão

export const useStore = create<AppState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      rightPanelOpen: true,
      rightPanelTab: 'tools',
      activePage: 'chat',

      // V4 Split Intelligence
      splitRatio: 0.5,
      executionPanelVisible: true,
      executionLog: [],
      executionActiveCategory: 'ALL',

      // Contexto manual do usuário
      userContext: '',

      // Chat sessions
      chatSessions: [],
      currentChatSessionId: _INITIAL_SESSION_ID,

      archiveCurrentChat: () => set((s) => {
        const msgs = s.messages.filter((m) => !m.isStreaming)
        if (msgs.length === 0) return {}
        const session: ChatSession = {
          id: s.currentChatSessionId,
          title: _makeChatTitle(msgs),
          messages: msgs.slice(-_MAX_MSG_PER_SESSION),
          createdAt: msgs[0]?.timestamp ?? Date.now(),
          updatedAt: Date.now(),
          workspaceName: s.workspaceName || s.workspacePath.split(/[\\/]/).filter(Boolean).pop() || '',
          model: s.currentModel,
        }
        const existing = s.chatSessions.findIndex((c) => c.id === s.currentChatSessionId)
        const updated = existing >= 0
          ? s.chatSessions.map((c) => c.id === session.id ? session : c)
          : [session, ...s.chatSessions]
        return { chatSessions: updated.slice(0, _MAX_SESSIONS) }
      }),

      createNewChat: () => set((s) => {
        // Arquiva chat atual se tiver mensagens
        const msgs = s.messages.filter((m) => !m.isStreaming)
        let sessions = s.chatSessions
        if (msgs.length > 0) {
          const session: ChatSession = {
            id: s.currentChatSessionId,
            title: _makeChatTitle(msgs),
            messages: msgs.slice(-_MAX_MSG_PER_SESSION),
            createdAt: msgs[0]?.timestamp ?? Date.now(),
            updatedAt: Date.now(),
            workspaceName: s.workspaceName || s.workspacePath.split(/[\\/]/).filter(Boolean).pop() || '',
            model: s.currentModel,
          }
          const existing = sessions.findIndex((c) => c.id === session.id)
          sessions = existing >= 0
            ? sessions.map((c) => c.id === session.id ? session : c)
            : [session, ...sessions]
          sessions = sessions.slice(0, _MAX_SESSIONS)
        }
        const newId = `session-${Date.now().toString(36)}`
        return {
          chatSessions: sessions,
          currentChatSessionId: newId,
          sessionId: newId,
          messages: [],
          liveToolEvents: [],
          isStreaming: false,
          currentStreamingId: null,
        }
      }),

      loadChatSession: (id) => set((s) => {
        const target = s.chatSessions.find((c) => c.id === id)
        if (!target) return {}
        // Arquiva chat atual
        const msgs = s.messages.filter((m) => !m.isStreaming)
        let sessions = s.chatSessions
        if (msgs.length > 0 && s.currentChatSessionId !== id) {
          const cur: ChatSession = {
            id: s.currentChatSessionId,
            title: _makeChatTitle(msgs),
            messages: msgs.slice(-_MAX_MSG_PER_SESSION),
            createdAt: msgs[0]?.timestamp ?? Date.now(),
            updatedAt: Date.now(),
            workspaceName: s.workspaceName || s.workspacePath.split(/[\\/]/).filter(Boolean).pop() || '',
            model: s.currentModel,
          }
          const existing = sessions.findIndex((c) => c.id === cur.id)
          sessions = existing >= 0
            ? sessions.map((c) => c.id === cur.id ? cur : c)
            : [cur, ...sessions]
          sessions = sessions.slice(0, _MAX_SESSIONS)
        }
        return {
          chatSessions: sessions,
          currentChatSessionId: id,
          sessionId: id,
          messages: target.messages,
          liveToolEvents: [],
          isStreaming: false,
          currentStreamingId: null,
        }
      }),

      deleteChatSession: (id) => set((s) => ({
        chatSessions: s.chatSessions.filter((c) => c.id !== id),
      })),

      messages: [],
      isStreaming: false,
      currentStreamingId: null,
      liveToolEvents: [],
      activeToolCount: 0,

      sessionId: _INITIAL_SESSION_ID,
      currentPath: '',

      projects: [],
      activeProjectId: null,
      projectMessages: {},

      projectContexts: [],
      activeFiles: [],
      projectMarkdown: {},
      lessonStats: null,
      backendStatus: { connected: false, model: 'gpt-4o', version: '2.2' },

      apiKey: '',
      apiKeys: {},
      currentModel: 'gpt-4o',
      backendUrl: 'http://localhost:8000',
      temperature: 0.7,
      maxTokens: 4096,
      solanaWalletAddress: '',
      locale: 'pt-BR',
      workspacePath: '',
      workspaceName: '',
      voiceEnabled: false,
      voiceId: 'nova',
      voiceSpeed: 1.0,
      voiceModel: 'tts-1-hd',
      isSpeaking: false,
      lunaApiToken: '',
      userId: '',
      userEmail: '',
      zeroCloudMode: false,

      setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
      setRightPanelOpen: (v) => set({ rightPanelOpen: v }),
      setRightPanelTab: (tab) => set({ rightPanelTab: tab }),
      setActivePage: (page) => set({ activePage: page }),

      addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
      updateMessage: (id, patch) => set((s) => ({ messages: s.messages.map((m) => m.id === id ? { ...m, ...patch } : m) })),
      clearMessages: () => set({ messages: [], liveToolEvents: [] }),
      setIsStreaming: (v) => set({ isStreaming: v }),
      setCurrentStreamingId: (id) => set({ currentStreamingId: id }),

      addLiveToolEvent: (e) => set((s) => {
        // V4: gera log line para o execution panel
        const cat = toolCategory(e.name)
        const logLine: ExecutionLogLine = {
          id:       makeLogId(),
          timestamp: e.startedAt,
          category:  cat,
          level:     'info',
          text:      `▶ ${e.name}${e.argsSummary ? '  ' + e.argsSummary : ''}`,
          toolName:  e.name,
          toolId:    e.id,
        }
        const newLog = [...s.executionLog, logLine].slice(-_MAX_LOG_LINES)
        return {
          liveToolEvents:  [...s.liveToolEvents, e],
          activeToolCount: s.activeToolCount + 1,
          rightPanelOpen:  true,
          rightPanelTab:   'tools',
          executionLog:    newLog,
        }
      }),
      updateLiveToolEvent: (id, patch) => set((s) => {
        const updated = s.liveToolEvents.map((e) => e.id === id ? { ...e, ...patch } : e)
        // V4: quando tool termina, adiciona linha de resultado no log
        let newLog = s.executionLog
        if (patch.status === 'done' || patch.status === 'error') {
          const tool = updated.find((e) => e.id === id)
          if (tool) {
            const elapsed = tool.doneAt ? (tool.doneAt - tool.startedAt) / 1000 : undefined
            const level: ExecLevel = patch.status === 'done' ? 'success' : 'error'
            const text = patch.status === 'done'
              ? `✓ ${tool.name}${tool.resultSummary ? '  ' + tool.resultSummary.slice(0, 120) : ''}`
              : `✗ ${tool.name}${patch.resultSummary ? '  ' + patch.resultSummary.slice(0, 120) : ''}`
            const resultLine: ExecutionLogLine = {
              id:        makeLogId(),
              timestamp: Date.now(),
              category:  toolCategory(tool.name),
              level,
              text,
              toolName:  tool.name,
              toolId:    id,
              elapsed,
            }
            // Se for screenshot, tenta extrair imageData do resultSummary
            if (tool.name === 'browser_screenshot' && patch.resultSummary) {
              const b64match = patch.resultSummary.match(/data:image\/[^;]+;base64,([A-Za-z0-9+/=]+)/)
              if (b64match) resultLine.imageData = b64match[1]
            }
            newLog = [...s.executionLog, resultLine].slice(-_MAX_LOG_LINES)
          }
        }
        return { liveToolEvents: updated, executionLog: newLog }
      }),
      commitLiveToolsToMessage: (msgId) => set((s) => ({
        messages: s.messages.map((m) => m.id === msgId ? { ...m, toolCalls: [...s.liveToolEvents] } : m),
        liveToolEvents: [],
      })),
      clearLiveToolEvents: () => set({ liveToolEvents: [] }),

      // ── V4 actions ───────────────────────────────────────────────────────
      setSplitRatio: (ratio) => set({ splitRatio: Math.min(0.75, Math.max(0.25, ratio)) }),
      setExecutionPanelVisible: (v) => set({ executionPanelVisible: v }),
      addLogLine: (line) => set((s) => ({
        executionLog: [...s.executionLog, { ...line, id: makeLogId(), timestamp: Date.now() }].slice(-_MAX_LOG_LINES),
      })),
      updateLogLine: (id, patch) => set((s) => ({
        executionLog: s.executionLog.map((l) => l.id === id ? { ...l, ...patch } : l),
      })),
      clearExecutionLog: (category) => set((s) => ({
        executionLog: category
          ? s.executionLog.filter((l) => l.category !== category)
          : [],
      })),
      setExecutionActiveCategory: (cat) => set({ executionActiveCategory: cat }),
      setUserContext: (v) => set({ userContext: v }),

      setCurrentPath: (path) => set({ currentPath: path }),
      setSessionId: (id) => set({ sessionId: id }),

      setProjects: (projects) => set({ projects }),
      setActiveProject: (id) => set({ activeProjectId: id }),
      addProjectMessage: (projectId, msg) => set((s) => ({
        projectMessages: { ...s.projectMessages, [projectId]: [...(s.projectMessages[projectId] ?? []), msg] },
      })),
      updateProjectMessage: (projectId, msgId, patch) => set((s) => ({
        projectMessages: {
          ...s.projectMessages,
          [projectId]: (s.projectMessages[projectId] ?? []).map((m) => m.id === msgId ? { ...m, ...patch } : m),
        },
      })),
      setProjectMessages: (projectId, msgs) => set((s) => ({
        projectMessages: { ...s.projectMessages, [projectId]: msgs },
      })),
      clearProjectMessages: (projectId) => set((s) => ({
        projectMessages: { ...s.projectMessages, [projectId]: [] },
      })),

      setProjectContext: (key, value) => set((s) => ({
        projectContexts: [...s.projectContexts.filter((c) => c.key !== key), { key, value, updatedAt: Date.now() }],
      })),
      removeProjectContext: (key) => set((s) => ({ projectContexts: s.projectContexts.filter((c) => c.key !== key) })),
      addActiveFile: (file) => set((s) => ({ activeFiles: [...s.activeFiles.filter((f) => f.path !== file.path), file].slice(-30) })),
      clearActiveFiles: () => set({ activeFiles: [] }),
      setProjectMarkdown: (workspacePath, content) => set((s) => ({ projectMarkdown: { ...s.projectMarkdown, [workspacePath]: content } })),
      setLessonStats: (stats) => set({ lessonStats: stats }),
      setBackendStatus: (status) => set((s) => ({ backendStatus: { ...s.backendStatus, ...status } })),

      setApiKey: (provider, value) => set((s) => ({ apiKeys: { ...s.apiKeys, [provider]: value }, ...(provider === 'openai' ? { apiKey: value } : {}) })),
      setApiKeys: (keys) => set({ apiKeys: keys }),
      setCurrentModel: (model) => set({ currentModel: model }),
      setBackendUrl: (url) => set({ backendUrl: url }),
      setTemperature: (v) => set({ temperature: v }),
      setMaxTokens: (v) => set({ maxTokens: v }),
      setSolanaWalletAddress: (addr) => set({ solanaWalletAddress: addr }),
      setLocale: (l) => set({ locale: l }),
      setWorkspace: (path, name) => set({ workspacePath: path, workspaceName: name }),
      clearWorkspace: () => set({ workspacePath: '', workspaceName: '' }),
      setVoiceEnabled: (v) => set({ voiceEnabled: v }),
      setVoiceId: (id) => set({ voiceId: id }),
      setVoiceSpeed: (v) => set({ voiceSpeed: v }),
      setVoiceModel: (m) => set({ voiceModel: m }),
      setIsSpeaking: (v) => set({ isSpeaking: v }),
      setLunaApiToken: (token) => set({ lunaApiToken: token }),
      setZeroCloudMode: (v) => set({ zeroCloudMode: v }),
      setUserId: (id) => set({ userId: id }),
      setUserEmail: (email) => set({ userEmail: email }),
    }),
    {
      name: 'luna-v4-store',
      partialize: (s) => ({
        sidebarCollapsed: s.sidebarCollapsed,
        rightPanelOpen: s.rightPanelOpen,
        // V4 split
        splitRatio: s.splitRatio,
        executionPanelVisible: s.executionPanelVisible,
        userContext: s.userContext,
        currentModel: s.currentModel,
        backendUrl: s.backendUrl,
        currentPath: s.currentPath,
        projects: s.projects,
        activeProjectId: s.activeProjectId,
        projectContexts: s.projectContexts,
        projectMarkdown: s.projectMarkdown,
        apiKey: s.apiKey,
        temperature: s.temperature,
        maxTokens: s.maxTokens,
        solanaWalletAddress: s.solanaWalletAddress,
        locale: s.locale,
        workspacePath: s.workspacePath,
        workspaceName: s.workspaceName,
        voiceEnabled: s.voiceEnabled,
        voiceId: s.voiceId,
        voiceSpeed: s.voiceSpeed,
        voiceModel: s.voiceModel,
        zeroCloudMode: s.zeroCloudMode,
        userId: s.userId,
        userEmail: s.userEmail,
        // ── Chat history persistence ──────────────────────
        chatSessions: s.chatSessions,
        currentChatSessionId: s.currentChatSessionId,
        messages: s.messages,   // persiste o chat atual também
      }),
    }
  )
)
