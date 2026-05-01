import React, { useRef, useEffect, useState, useCallback } from 'react'
import {
  useStore,
  ExecutionLogLine,
  ExecCategory,
} from '@store/appStore'
import {
  Terminal, FolderOpen, BookOpen, Trash2, ChevronDown,
  ChevronRight, Loader2,
  PanelRightClose, Filter, BarChart2, RefreshCw,
  FileCode, FileJson, FileType, Folder, FileText, Edit3, Save, X,
} from 'lucide-react'
import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

// ── Constantes ────────────────────────────────────────────────────────────────
const CATEGORY_COLORS: Record<ExecCategory, { border: string; bg: string; text: string; label: string }> = {
  BOUNTY:  { border: '#D85A30', bg: 'rgba(216,90,48,0.08)',   text: '#F0997B', label: 'BOUNTY'  },
  SOLANA:  { border: '#378ADD', bg: 'rgba(55,138,221,0.08)',  text: '#85B7EB', label: 'SOLANA'  },
  BROWSER: { border: '#7F77DD', bg: 'rgba(127,119,221,0.08)', text: '#AFA9EC', label: 'BROWSER' },
  SYSTEM:  { border: '#1D9E75', bg: 'rgba(29,158,117,0.08)',  text: '#5DCAA5', label: 'SYSTEM'  },
  CHAT:    { border: '#888780', bg: 'rgba(136,135,128,0.08)', text: '#B4B2A9', label: 'CHAT'    },
}

const LEVEL_COLORS: Record<string, string> = {
  info:     '#85B7EB',
  success:  '#5DCAA5',
  warning:  '#EF9F27',
  error:    '#E24B4A',
  progress: '#AFA9EC',
}

const TOOL_ICONS: Record<string, string> = {
  scan_project: '🔍', read_file: '📄', read_many: '📚',
  write_file: '✏️', patch_file: '🩹', run_command: '⚡',
  grep_file: '🔎', search_files: '🗂️', web_search: '🌐',
  list_dir: '📁', list_directory: '📁', fetch_url: '🌐',
  bounty_scope_check: '🛡️', bounty_recon_subdomains: '🕵️',
  bounty_recon_live: '📶', bounty_crawl: '🕸️',
  bounty_scan_nuclei: '🎯', bounty_scan_dalfox: '💉',
  bounty_audit_jwt: '🔐', bounty_audit_graphql: '🧬',
  solana_parse_idl: '🧭', solana_rust_scan: '🦀',
  solana_decode_tx: '🔗', solana_cpi_graph: '🕳️',
  browser_navigate: '🌐', browser_extract: '🧲',
  browser_eval: '⚙️', browser_fill_submit: '⌨️',
  browser_screenshot: '📸',
}

function toolIcon(name: string): string {
  return TOOL_ICONS[name] ?? '🔧'
}

// ── File icon (Context tab) ───────────────────────────────────────────────────
function FileIcon({ path, size = 12 }: { path: string; size?: number }) {
  const ext = path.split('.').pop()?.toLowerCase() ?? ''
  if (['ts', 'tsx', 'js', 'jsx', 'mjs'].includes(ext))
    return <FileCode size={size} className="text-yellow-400 flex-shrink-0" />
  if (['py', 'rs', 'go', 'rb', 'java'].includes(ext))
    return <FileCode size={size} className="text-blue-400 flex-shrink-0" />
  if (['json', 'yaml', 'yml', 'toml', 'env'].includes(ext))
    return <FileJson size={size} className="text-green-400 flex-shrink-0" />
  if (['md', 'txt'].includes(ext))
    return <FileType size={size} className="text-cyber-muted flex-shrink-0" />
  if (!path.includes('.'))
    return <Folder size={size} className="text-cyber-cyan flex-shrink-0" />
  return <FileText size={size} className="text-cyber-dim flex-shrink-0" />
}

// ── Single log line ───────────────────────────────────────────────────────────
const LogLine: React.FC<{ line: ExecutionLogLine }> = React.memo(({ line }) => {
  const [imgOpen, setImgOpen] = useState(false)
  const cat   = CATEGORY_COLORS[line.category]
  const color = LEVEL_COLORS[line.level] ?? '#85B7EB'

  const ts = new Date(line.timestamp).toLocaleTimeString('pt-BR', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })

  return (
    <div
      className="group flex flex-col gap-0.5 px-2.5 py-1 rounded-sm text-[10px] font-mono leading-relaxed"
      style={{ borderLeft: `2px solid ${cat.border}22` }}
    >
      <div className="flex items-center gap-1.5">
        {/* Timestamp */}
        <span className="text-[9px] opacity-30 flex-shrink-0 tabular-nums">{ts}</span>

        {/* Category badge */}
        <span
          className="text-[8px] font-bold px-1 rounded-sm flex-shrink-0"
          style={{ background: cat.bg, color: cat.text }}
        >
          {cat.label}
        </span>

        {/* Tool icon */}
        {line.toolName && (
          <span className="text-[11px] leading-none flex-shrink-0">
            {toolIcon(line.toolName)}
          </span>
        )}

        {/* Message */}
        <span className="flex-1 truncate" style={{ color }}>
          {line.text}
        </span>

        {/* Elapsed */}
        {line.elapsed !== undefined && (
          <span className="text-[9px] opacity-40 flex-shrink-0 tabular-nums">
            {line.elapsed.toFixed(1)}s
          </span>
        )}

        {/* Screenshot toggle */}
        {line.imageData && (
          <button
            onClick={() => setImgOpen(!imgOpen)}
            className="text-[9px] px-1.5 py-0.5 rounded-sm flex-shrink-0 transition-colors"
            style={{ background: 'rgba(127,119,221,0.2)', color: '#AFA9EC' }}
          >
            {imgOpen ? '▲ fechar' : '▼ ver screenshot'}
          </button>
        )}
      </div>

      {/* Progress bar */}
      {line.level === 'progress' && line.progress !== undefined && (
        <div
          className="ml-6 h-1 rounded-full overflow-hidden"
          style={{ background: 'rgba(255,255,255,0.06)' }}
        >
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{ width: `${line.progress}%`, background: cat.text }}
          />
        </div>
      )}

      {/* Screenshot preview */}
      {line.imageData && imgOpen && (
        <div className="mt-1.5 ml-6">
          <img
            src={`data:image/png;base64,${line.imageData}`}
            alt="browser screenshot"
            className="rounded border max-w-full"
            style={{ border: '1px solid rgba(127,119,221,0.3)', maxHeight: 200, objectFit: 'contain' }}
          />
        </div>
      )}
    </div>
  )
})

// ── Category section header ────────────────────────────────────────────────────
const CategorySection: React.FC<{
  category: ExecCategory
  lines: ExecutionLogLine[]
  onClear: () => void
}> = ({ category, lines, onClear }) => {
  const [collapsed, setCollapsed] = useState(false)
  const cat = CATEGORY_COLORS[category]
  const runningCount = lines.filter((l) => l.level === 'info').length

  return (
    <div className="mb-1">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-1.5 px-2 py-1 rounded-sm text-[9px] font-mono font-bold tracking-wider transition-colors"
        style={{ background: cat.bg, color: cat.text }}
      >
        {collapsed
          ? <ChevronRight size={10} />
          : <ChevronDown size={10} />
        }
        <span>{cat.label}</span>
        <span className="opacity-50 font-normal">{lines.length} linhas</span>
        {runningCount > 0 && (
          <span
            className="ml-1 px-1 rounded-sm"
            style={{ background: cat.border + '33', color: cat.text }}
          >
            {runningCount} ativos
          </span>
        )}
        <button
          onClick={(e) => { e.stopPropagation(); onClear() }}
          className="ml-auto opacity-0 group-hover:opacity-100 hover:opacity-100 transition-opacity"
          title="Limpar seção"
        >
          <Trash2 size={9} />
        </button>
      </button>
      {!collapsed && (
        <div className="mt-0.5 space-y-px">
          {lines.map((line) => <LogLine key={line.id} line={line} />)}
        </div>
      )}
    </div>
  )
}

// ── Stats tab ─────────────────────────────────────────────────────────────────
const StatsTab: React.FC = () => {
  const { lessonStats } = useStore()

  if (!lessonStats?.by_type) {
    return (
      <div className="flex flex-col items-center justify-center h-40 gap-2 mt-8">
        <BarChart2 size={24} className="text-cyber-dim" />
        <p className="text-[11px] text-cyber-muted text-center">
          Nenhuma lição registrada ainda.
        </p>
      </div>
    )
  }

  const chartData = Object.entries(lessonStats.by_type).map(([type, data]) => ({
    name: type.replace('_', ' ').slice(0, 10),
    total: data.total,
    success: data.success,
  }))

  return (
    <div className="space-y-4 p-2">
      <div className="stat-card">
        <p className="text-[10px] text-cyber-muted font-mono mb-1">TOTAL DE LIÇÕES</p>
        <p className="text-2xl font-bold text-cyber-cyan" style={{ textShadow: '0 0 10px rgba(0,212,255,0.5)' }}>
          {lessonStats.total_lessons}
        </p>
      </div>
      {chartData.length > 0 && (
        <div>
          <p className="text-[10px] text-cyber-muted font-mono mb-2 uppercase tracking-wider">Por tipo</p>
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={chartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <XAxis dataKey="name" tick={{ fontSize: 8, fill: '#64748b', fontFamily: 'monospace' }} />
              <Tooltip
                contentStyle={{ background: '#0d1117', border: '1px solid rgba(0,212,255,0.2)', borderRadius: 6, fontSize: 10 }}
                labelStyle={{ color: '#00d4ff' }}
                itemStyle={{ color: '#e2e8f0' }}
              />
              <Bar dataKey="success" radius={[2, 2, 0, 0]}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill={i % 2 === 0 ? '#00d4ff' : '#7c3aed'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="space-y-1.5">
        {Object.entries(lessonStats.by_type).map(([type, data]) => {
          const pct = data.total > 0 ? Math.round((data.success / data.total) * 100) : 0
          return (
            <div key={type}>
              <div className="flex justify-between mb-0.5">
                <span className="text-[10px] font-mono text-cyber-text">{type.replace('_', ' ')}</span>
                <span className="text-[10px] font-mono text-cyber-muted">{pct}%</span>
              </div>
              <div className="progress-cyber">
                <div className="progress-cyber-fill" style={{ width: `${pct}%` }} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Context tab ───────────────────────────────────────────────────────────────
const ContextTab: React.FC = () => {
  const {
    activeFiles, clearActiveFiles,
    workspacePath, projectMarkdown, setProjectMarkdown,
    userContext, setUserContext,
  } = useStore()
  const [editMode, setEditMode] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [contextDraft, setContextDraft] = useState(userContext)
  const [contextSaved, setContextSaved] = useState(false)
  const markdown = workspacePath ? (projectMarkdown[workspacePath] ?? '') : ''
  const sorted   = [...activeFiles].sort((a, b) => b.timestamp - a.timestamp)

  const saveUserContext = () => {
    setUserContext(contextDraft)
    setContextSaved(true)
    setTimeout(() => setContextSaved(false), 2000)
  }

  const getFileName = (p: string) => p.split(/[/\\]/).pop() ?? p
  const getRelPath  = (p: string) => {
    if (!workspacePath) return p
    return p.startsWith(workspacePath) ? p.slice(workspacePath.length).replace(/^[/\\]/, '') : p
  }

  return (
    <div className="space-y-3 p-2">
      {/* Active files */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[9px] font-mono text-cyber-muted uppercase tracking-wider">
            Arquivos Ativos ({sorted.length})
          </span>
          {sorted.length > 0 && (
            <button
              onClick={clearActiveFiles}
              className="flex items-center gap-1 text-[9px] text-cyber-dim hover:text-cyber-red transition-colors"
            >
              <Trash2 size={9} /><span>Limpar</span>
            </button>
          )}
        </div>
        {sorted.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-4 gap-1.5 rounded-md"
            style={{ background: 'rgba(15,22,36,0.4)', border: '1px dashed rgba(0,212,255,0.08)' }}>
            <FolderOpen size={18} className="text-cyber-dim" />
            <p className="text-[10px] text-cyber-muted text-center">
              Nenhum arquivo acessado ainda.
            </p>
          </div>
        ) : (
          <div className="space-y-0.5">
            {sorted.map((f, i) => (
              <div key={`${f.path}-${i}`}
                className="flex items-center gap-1.5 px-2 py-1 rounded"
                style={{ background: 'rgba(15,22,36,0.5)', border: '1px solid rgba(0,212,255,0.06)' }}>
                <FileIcon path={f.path} size={11} />
                <div className="flex-1 min-w-0">
                  <div className="text-[10px] font-mono text-cyber-text truncate">{getFileName(f.path)}</div>
                  <div className="text-[9px] text-cyber-dim truncate">{getRelPath(f.path)}</div>
                </div>
                <span
                  className="text-[9px] font-bold font-mono rounded px-1"
                  style={{
                    background: f.operation === 'write' ? 'rgba(124,58,237,0.2)' : 'rgba(0,212,255,0.15)',
                    color:      f.operation === 'write' ? '#a78bfa' : '#00d4ff',
                  }}
                >
                  {f.operation === 'read' ? 'R' : f.operation === 'write' ? 'W' : 'L'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* User context textarea */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[9px] font-mono text-cyber-muted uppercase tracking-wider">
            Contexto Manual
          </span>
          <div className="flex items-center gap-1">
            {contextDraft.trim() !== userContext.trim() && (
              <button
                onClick={saveUserContext}
                className="flex items-center gap-1 text-[9px] text-cyber-green hover:opacity-80 transition-opacity"
              >
                <Save size={9} /><span>Salvar</span>
              </button>
            )}
            {contextSaved && (
              <span className="text-[9px] text-cyber-green opacity-70">✓ Salvo</span>
            )}
            {contextDraft.trim() !== '' && (
              <button
                onClick={() => { setContextDraft(''); setUserContext('') }}
                className="flex items-center gap-1 text-[9px] text-cyber-dim hover:text-cyber-red transition-colors ml-1"
                title="Limpar contexto"
              >
                <X size={9} />
              </button>
            )}
          </div>
        </div>
        <textarea
          value={contextDraft}
          onChange={(e) => setContextDraft(e.target.value)}
          onBlur={saveUserContext}
          placeholder="Descreva o contexto atual para a Luna usar nas respostas… Ex: 'Estou auditando o contrato X, foco em reentrância'"
          className="w-full font-mono text-[10px] text-cyber-text bg-black/40 rounded p-2 resize-none outline-none placeholder-cyber-dim"
          style={{
            border: contextDraft.trim()
              ? '1px solid rgba(0,212,255,0.25)'
              : '1px solid rgba(0,212,255,0.08)',
            minHeight: 72,
            lineHeight: 1.5,
            transition: 'border-color 0.2s',
          }}
          spellCheck={false}
        />
        {userContext.trim() && (
          <p className="mt-1 text-[9px] text-cyber-green opacity-60 font-mono">
            ⚡ Contexto ativo · {userContext.length} chars
          </p>
        )}
      </div>

      {/* Project context doc */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[9px] font-mono text-cyber-muted uppercase tracking-wider">Contexto do Projeto</span>
          <div className="flex items-center gap-1">
            {!editMode ? (
              <button onClick={() => { setEditContent(markdown); setEditMode(true) }}
                className="flex items-center gap-1 text-[9px] text-cyber-dim hover:text-cyber-cyan transition-colors">
                <Edit3 size={9} /><span>Editar</span>
              </button>
            ) : (
              <>
                <button onClick={() => { if (workspacePath) setProjectMarkdown(workspacePath, editContent); setEditMode(false) }}
                  className="flex items-center gap-1 text-[9px] text-cyber-green hover:opacity-80 transition-opacity">
                  <Save size={9} /><span>Salvar</span>
                </button>
                <button onClick={() => setEditMode(false)}
                  className="flex items-center gap-1 text-[9px] text-cyber-dim hover:text-cyber-red transition-colors ml-1">
                  <X size={9} />
                </button>
              </>
            )}
          </div>
        </div>
        {editMode ? (
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            className="w-full font-mono text-[10px] text-cyber-text bg-black/40 rounded p-2 resize-none outline-none"
            style={{ border: '1px solid rgba(0,212,255,0.2)', minHeight: 200, lineHeight: 1.5 }}
            spellCheck={false}
          />
        ) : markdown ? (
          <div className="rounded-md p-2.5 overflow-y-auto text-[10px] font-mono text-cyber-muted"
            style={{ background: 'rgba(15,22,36,0.5)', border: '1px solid rgba(0,212,255,0.1)', maxHeight: 300 }}>
            {markdown}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-5 gap-1.5 rounded-md"
            style={{ background: 'rgba(15,22,36,0.4)', border: '1px dashed rgba(0,212,255,0.08)' }}>
            <RefreshCw size={18} className="text-cyber-dim" />
            <p className="text-[10px] text-cyber-muted text-center leading-relaxed">
              Nenhum contexto salvo ainda.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main ExecutionPanel ───────────────────────────────────────────────────────
const ExecutionPanel: React.FC = () => {
  const {
    executionLog,
    executionActiveCategory,
    clearExecutionLog,
    setExecutionActiveCategory,
    setExecutionPanelVisible,
    liveToolEvents,
    activeFiles,
  } = useStore()

  const [tab, setTab] = useState<'exec' | 'context' | 'stats'>('exec')
  const scrollRef = useRef<HTMLDivElement>(null)
  const isAtBottom = useRef(true)

  // Auto-scroll apenas se já estava no fundo
  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    isAtBottom.current = scrollHeight - scrollTop - clientHeight < 40
  }, [])

  useEffect(() => {
    if (tab === 'exec' && isAtBottom.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [executionLog.length, tab])

  // Linhas filtradas
  const filtered = executionActiveCategory === 'ALL'
    ? executionLog
    : executionLog.filter((l) => l.category === executionActiveCategory)

  // Agrupar por categoria para renderização em seções
  const grouped = filtered.reduce<Record<ExecCategory, ExecutionLogLine[]>>(
    (acc, l) => { acc[l.category] = [...(acc[l.category] ?? []), l]; return acc },
    {} as Record<ExecCategory, ExecutionLogLine[]>
  )

  // Contadores
  const runningTools = liveToolEvents.filter((e) => e.status === 'running').length
  const contextBadge = activeFiles.length

  const CATEGORIES: ExecCategory[] = ['BOUNTY', 'SOLANA', 'BROWSER', 'SYSTEM', 'CHAT']

  return (
    <div className="flex flex-col h-full" style={{ background: '#080b14' }}>

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div
        className="flex-shrink-0 flex items-center gap-1 px-2 py-1.5 border-b"
        style={{ borderColor: 'rgba(0,212,255,0.1)', background: 'rgba(5,8,16,0.95)' }}
      >
        {/* Tabs */}
        {(
          [
            { id: 'exec',    label: 'Execução', icon: Terminal,   badge: runningTools },
            { id: 'context', label: 'Context',  icon: FolderOpen, badge: contextBadge },
            { id: 'stats',   label: 'Stats',    icon: BookOpen,   badge: 0 },
          ] as const
        ).map(({ id, label, icon: Icon, badge }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`tab-cyber flex items-center gap-1 ${tab === id ? 'active' : ''}`}
          >
            <Icon size={10} />
            <span>{label}</span>
            {badge > 0 && (
              <span
                className="ml-0.5 rounded-full px-1 text-[8px] font-bold"
                style={{
                  background: id === 'exec' ? '#f59e0b' : 'rgba(0,212,255,0.2)',
                  color:      id === 'exec' ? '#080b14' : '#00d4ff',
                  minWidth: 14, textAlign: 'center',
                }}
              >
                {badge}
              </span>
            )}
          </button>
        ))}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Clear all */}
        {tab === 'exec' && executionLog.length > 0 && (
          <button
            onClick={() => clearExecutionLog()}
            title="Limpar log"
            className="text-cyber-dim hover:text-cyber-red transition-colors p-0.5"
          >
            <Trash2 size={11} />
          </button>
        )}

        {/* Hide panel */}
        <button
          onClick={() => setExecutionPanelVisible(false)}
          title="Esconder painel"
          className="text-cyber-dim hover:text-cyber-muted transition-colors p-0.5 ml-1"
        >
          <PanelRightClose size={11} />
        </button>
      </div>

      {/* ── Category filter bar (exec tab only) ──────────────────────── */}
      {tab === 'exec' && (
        <div
          className="flex-shrink-0 flex items-center gap-1 px-2 py-1 border-b overflow-x-auto"
          style={{ borderColor: 'rgba(0,212,255,0.06)', background: 'rgba(5,8,16,0.7)' }}
        >
          <Filter size={9} className="text-cyber-dim flex-shrink-0" />
          <button
            onClick={() => setExecutionActiveCategory('ALL')}
            className={`text-[9px] font-mono px-2 py-0.5 rounded-sm flex-shrink-0 transition-colors ${executionActiveCategory === 'ALL' ? 'bg-cyber-dim text-cyber-cyan' : 'text-cyber-dim hover:text-cyber-muted'}`}
            style={executionActiveCategory === 'ALL' ? { background: 'rgba(0,212,255,0.12)', color: '#00d4ff' } : {}}
          >
            ALL ({executionLog.length})
          </button>
          {CATEGORIES.map((cat) => {
            const count = executionLog.filter((l) => l.category === cat).length
            if (count === 0) return null
            const c = CATEGORY_COLORS[cat]
            const active = executionActiveCategory === cat
            return (
              <button
                key={cat}
                onClick={() => setExecutionActiveCategory(active ? 'ALL' : cat)}
                className="text-[9px] font-mono px-2 py-0.5 rounded-sm flex-shrink-0 transition-colors"
                style={{
                  background: active ? c.bg : 'transparent',
                  color:      active ? c.text : '#4a5568',
                  border:     `1px solid ${active ? c.border + '44' : 'transparent'}`,
                }}
              >
                {cat} ({count})
              </button>
            )
          })}
        </div>
      )}

      {/* ── Content ──────────────────────────────────────────────────── */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
        style={{ background: '#080b14' }}
      >
        {tab === 'exec' && (
          <>
            {filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-3 py-12">
                <Terminal size={28} className="text-cyber-dim opacity-40" />
                <p className="text-[11px] text-cyber-dim text-center leading-relaxed">
                  Execução ao vivo aparece aqui.<br />
                  <span className="opacity-50">Inicie uma tarefa para ver os logs.</span>
                </p>
              </div>
            ) : executionActiveCategory === 'ALL' ? (
              // Modo ALL: agrupa por categoria
              <div className="py-1 px-1">
                {(Object.keys(grouped) as ExecCategory[]).map((cat) => (
                  <CategorySection
                    key={cat}
                    category={cat}
                    lines={grouped[cat]}
                    onClear={() => clearExecutionLog(cat)}
                  />
                ))}
              </div>
            ) : (
              // Modo filtrado: lista simples
              <div className="py-1 space-y-px">
                {filtered.map((line) => <LogLine key={line.id} line={line} />)}
              </div>
            )}
          </>
        )}

        {tab === 'context' && <ContextTab />}
        {tab === 'stats'   && <StatsTab />}
      </div>

      {/* ── Footer: running indicator ────────────────────────────────── */}
      {runningTools > 0 && tab === 'exec' && (
        <div
          className="flex-shrink-0 flex items-center gap-2 px-3 py-1.5 border-t"
          style={{ borderColor: 'rgba(0,212,255,0.1)', background: 'rgba(5,8,16,0.95)' }}
        >
          <Loader2 size={10} className="text-cyber-cyan animate-spin" />
          <span className="text-[10px] text-cyber-cyan font-mono">
            {runningTools} tool{runningTools > 1 ? 's' : ''} rodando...
          </span>
        </div>
      )}
    </div>
  )
}

export default ExecutionPanel
