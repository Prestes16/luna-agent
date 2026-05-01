import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '@store/appStore'
import TopBar from '@components/TopBar'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import {
  Folder, FolderOpen, File, FileCode, FileText,
  ChevronRight, ChevronDown, RefreshCw, Search,
  Bug, BookOpen, Wand2, MessageSquare, Copy,
  AlertTriangle, FolderX, Loader2, CheckCircle2,
} from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface FileNode {
  name: string
  path: string
  isDirectory: boolean
  children?: FileNode[]
  loaded?: boolean
  expanded?: boolean
}

// ── Constants ─────────────────────────────────────────────────────────────────

const IGNORED = new Set([
  'node_modules', '.git', '__pycache__', 'dist', 'build', '.next',
  'target', 'venv', '.venv', 'out', '.cache', '.pytest_cache',
  '.idea', '.vscode', 'coverage', '.nyc_output', 'logs',
])

const LANG_MAP: Record<string, string> = {
  ts: 'typescript', tsx: 'tsx', js: 'javascript', jsx: 'jsx',
  py: 'python', rs: 'rust', go: 'go', java: 'java',
  json: 'json', yaml: 'yaml', yml: 'yaml', md: 'markdown',
  toml: 'toml', css: 'css', scss: 'scss', html: 'html',
  sh: 'bash', bash: 'bash', zsh: 'bash', fish: 'bash',
  sol: 'solidity', c: 'c', cpp: 'cpp', h: 'c',
  cs: 'csharp', rb: 'ruby', php: 'php', swift: 'swift', kt: 'kotlin',
  sql: 'sql', graphql: 'graphql', gql: 'graphql',
  dockerfile: 'docker', tf: 'hcl', hcl: 'hcl', xml: 'xml',
}

const CODE_EXTS = new Set([
  'ts', 'tsx', 'js', 'jsx', 'py', 'rs', 'go', 'java', 'c', 'cpp', 'h',
  'cs', 'rb', 'php', 'swift', 'kt', 'sol', 'sh', 'bash', 'zsh', 'fish',
  'sql', 'graphql', 'gql', 'tf', 'hcl',
])
const TEXT_EXTS = new Set([
  'md', 'txt', 'rst', 'log', 'csv', 'toml', 'yaml', 'yml', 'xml',
  'dockerfile', 'gitignore', 'env', 'ini', 'cfg', 'conf',
])

const MAX_PREVIEW_BYTES = 150_000
const MAX_PREVIEW_LINES = 2000

function getLang(filename: string): string {
  const lower = filename.toLowerCase()
  // Special: Dockerfile
  if (lower === 'dockerfile') return 'docker'
  const ext = lower.split('.').pop() ?? ''
  return LANG_MAP[ext] ?? 'text'
}

function getFileIcon(name: string): React.ReactNode {
  const ext = name.toLowerCase().split('.').pop() ?? ''
  if (CODE_EXTS.has(ext)) {
    return <FileCode size={13} className="flex-shrink-0" style={{ color: '#60a5fa' }} />
  }
  if (TEXT_EXTS.has(ext)) {
    return <FileText size={13} className="flex-shrink-0" style={{ color: '#94a3b8' }} />
  }
  if (ext === 'json') {
    return <FileCode size={13} className="flex-shrink-0" style={{ color: '#fbbf24' }} />
  }
  return <File size={13} className="flex-shrink-0" style={{ color: '#475569' }} />
}

function sortNodes(nodes: FileNode[]): FileNode[] {
  return [...nodes].sort((a, b) => {
    if (a.isDirectory !== b.isDirectory) return a.isDirectory ? -1 : 1
    return a.name.localeCompare(b.name)
  })
}

// ── FileTreeNode ──────────────────────────────────────────────────────────────

interface FileTreeNodeProps {
  node: FileNode
  depth: number
  selectedPath: string | null
  onSelect: (node: FileNode) => void
  onToggle: (path: string) => void
}

const FileTreeNode: React.FC<FileTreeNodeProps> = ({ node, depth, selectedPath, onSelect, onToggle }) => {
  const isSelected = selectedPath === node.path
  const indent = depth * 14 + 8

  if (node.isDirectory) {
    return (
      <>
        <button
          onClick={() => onToggle(node.path)}
          className="flex items-center w-full text-left py-[3px] pr-2 rounded-md transition-colors group"
          style={{ paddingLeft: indent }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.04)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
        >
          <span className="flex-shrink-0 mr-0.5" style={{ width: 14 }}>
            {node.expanded
              ? <ChevronDown size={10} className="text-cyber-dim" />
              : <ChevronRight size={10} className="text-cyber-dim" />
            }
          </span>
          {node.expanded
            ? <FolderOpen size={13} className="flex-shrink-0 mr-1.5" style={{ color: '#fbbf24' }} />
            : <Folder size={13} className="flex-shrink-0 mr-1.5" style={{ color: '#f59e0b' }} />
          }
          <span className="text-[12px] font-mono text-cyber-muted truncate group-hover:text-cyber-text transition-colors">
            {node.name}
          </span>
        </button>
        {node.expanded && node.children && (
          <>
            {node.children.map((child) => (
              <FileTreeNode
                key={child.path}
                node={child}
                depth={depth + 1}
                selectedPath={selectedPath}
                onSelect={onSelect}
                onToggle={onToggle}
              />
            ))}
            {node.children.length === 0 && (
              <div
                className="text-[10px] font-mono text-cyber-dim italic"
                style={{ paddingLeft: indent + 28 }}
              >
                vazio
              </div>
            )}
          </>
        )}
      </>
    )
  }

  return (
    <button
      onClick={() => onSelect(node)}
      className="flex items-center w-full text-left py-[3px] pr-2 rounded-md transition-colors"
      style={{
        paddingLeft: indent + 14,
        background: isSelected ? 'rgba(0,212,255,0.1)' : 'transparent',
      }}
      onMouseEnter={(e) => {
        if (!isSelected) (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.04)'
      }}
      onMouseLeave={(e) => {
        if (!isSelected) (e.currentTarget as HTMLElement).style.background = 'transparent'
      }}
    >
      {getFileIcon(node.name)}
      <span
        className="text-[12px] font-mono ml-1.5 truncate"
        style={{ color: isSelected ? '#00d4ff' : '#94a3b8' }}
      >
        {node.name}
      </span>
    </button>
  )
}

// ── Luna Quick Actions ─────────────────────────────────────────────────────────

const ACTIONS = [
  {
    id: 'analyze', label: 'Analisar', icon: Search, color: '#00d4ff',
    desc: 'Análise de qualidade, padrões e complexidade',
  },
  {
    id: 'bugs', label: 'Buscar bugs', icon: Bug, color: '#ef4444',
    desc: 'Vulnerabilidades, memory leaks, race conditions',
  },
  {
    id: 'explain', label: 'Explicar', icon: BookOpen, color: '#a78bfa',
    desc: 'O que o código faz, responsabilidade e integrações',
  },
  {
    id: 'refactor', label: 'Refatorar', icon: Wand2, color: '#10b981',
    desc: 'Melhorias de legibilidade, performance e design',
  },
  {
    id: 'test', label: 'Gerar testes', icon: CheckCircle2, color: '#f59e0b',
    desc: 'Unit tests, casos de borda e mocks',
  },
  {
    id: 'chat', label: 'Abrir no Chat', icon: MessageSquare, color: '#7c3aed',
    desc: 'Enviar arquivo para conversar com Luna',
  },
]

interface LunaActionsProps {
  filePath: string | null
  fileName: string | null
  onAction: (id: string) => void
}

const LunaActions: React.FC<LunaActionsProps> = ({ filePath, fileName, onAction }) => {
  if (!filePath) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 px-4 text-center">
        <FileCode size={26} style={{ color: 'rgba(0,212,255,0.15)' }} />
        <p className="text-[11px] font-mono text-cyber-dim leading-relaxed">
          Selecione um arquivo para ver as ações Luna
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div
        className="flex-shrink-0 px-3 py-2.5 border-b"
        style={{ borderColor: 'rgba(0,212,255,0.08)' }}
      >
        <p className="text-[9px] font-mono text-cyber-dim uppercase tracking-wider mb-1">
          🌙 Ações Luna
        </p>
        <p
          className="text-[11px] font-mono truncate"
          style={{ color: '#00d4ff' }}
          title={filePath}
        >
          {fileName}
        </p>
      </div>

      {/* Actions list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {ACTIONS.map((action) => {
          const Icon = action.icon
          return (
            <button
              key={action.id}
              onClick={() => onAction(action.id)}
              className="flex items-start gap-2.5 w-full p-2.5 rounded-lg text-left transition-all"
              style={{
                background: 'rgba(255,255,255,0.02)',
                border: '1px solid rgba(255,255,255,0.05)',
              }}
              onMouseEnter={(e) => {
                ;(e.currentTarget as HTMLElement).style.background = `${action.color}10`
                ;(e.currentTarget as HTMLElement).style.borderColor = `${action.color}28`
              }}
              onMouseLeave={(e) => {
                ;(e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.02)'
                ;(e.currentTarget as HTMLElement).style.borderColor = 'rgba(255,255,255,0.05)'
              }}
            >
              <Icon size={13} className="flex-shrink-0 mt-0.5" style={{ color: action.color }} />
              <div className="min-w-0">
                <p className="text-[11px] font-semibold" style={{ color: action.color }}>
                  {action.label}
                </p>
                <p className="text-[10px] text-cyber-dim mt-0.5 leading-relaxed">{action.desc}</p>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ── Flatten tree (for search) ─────────────────────────────────────────────────

function flattenTree(nodes: FileNode[]): FileNode[] {
  const result: FileNode[] = []
  for (const n of nodes) {
    if (!n.isDirectory) result.push(n)
    if (n.children) result.push(...flattenTree(n.children))
  }
  return result
}

// ── Workspace page ─────────────────────────────────────────────────────────────

const Workspace: React.FC = () => {
  const navigate       = useNavigate()
  const { workspacePath, workspaceName } = useStore()

  const [tree, setTree]               = useState<FileNode[]>([])
  const [treeLoading, setTreeLoading] = useState(false)
  const [treeError, setTreeError]     = useState<string | null>(null)

  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [fileContent, setFileContent]   = useState<string | null>(null)
  const [fileLoading, setFileLoading]   = useState(false)
  const [fileError, setFileError]       = useState<string | null>(null)
  const [isBinary, setIsBinary]         = useState(false)
  const [fileTruncated, setFileTruncated] = useState(false)

  const [searchQuery, setSearchQuery] = useState('')
  const [copied, setCopied]           = useState(false)

  const fsAPI = window.electronAPI?.workspace

  // ── Load root ──────────────────────────────────────────────────────────────
  const loadRoot = useCallback(async () => {
    if (!workspacePath || !fsAPI) return
    setTreeLoading(true)
    setTreeError(null)
    try {
      const res = await fsAPI.readDir(workspacePath)
      if ('error' in res) { setTreeError(res.error as string); return }
      setTree(
        sortNodes(
          (res as Array<{ name: string; isDirectory: boolean; path: string }>)
            .filter((e) => !IGNORED.has(e.name))
            .map((e): FileNode => ({ ...e, loaded: false, expanded: false }))
        )
      )
    } catch (err: any) {
      setTreeError(err.message ?? 'Erro ao ler diretório')
    } finally {
      setTreeLoading(false)
    }
  }, [workspacePath, fsAPI])

  useEffect(() => { loadRoot() }, [loadRoot])

  // ── Toggle directory ───────────────────────────────────────────────────────
  const updateNodeRecursive = useCallback(
    async (nodes: FileNode[], targetPath: string): Promise<FileNode[]> => {
      return Promise.all(
        nodes.map(async (node) => {
          if (node.path === targetPath && node.isDirectory) {
            if (!node.loaded) {
              const res = await fsAPI!.readDir(node.path)
              const raw = 'error' in res
                ? []
                : (res as Array<{ name: string; isDirectory: boolean; path: string }>)
                    .filter((e) => !IGNORED.has(e.name))
                    .map((e): FileNode => ({ ...e, loaded: false, expanded: false }))
              return { ...node, expanded: true, loaded: true, children: sortNodes(raw) }
            }
            return { ...node, expanded: !node.expanded }
          }
          if (node.children) {
            return { ...node, children: await updateNodeRecursive(node.children, targetPath) }
          }
          return node
        })
      )
    },
    [fsAPI]
  )

  const toggleNode = useCallback(async (targetPath: string) => {
    setTree((prev) => {
      // We need async, so update asynchronously
      updateNodeRecursive(prev, targetPath).then(setTree)
      return prev  // optimistic no-op while awaiting
    })
  }, [updateNodeRecursive])

  // ── Select file ────────────────────────────────────────────────────────────
  const selectFile = useCallback(async (node: FileNode) => {
    if (node.isDirectory) return
    setSelectedPath(node.path)
    setSelectedName(node.name)
    setFileContent(null)
    setFileError(null)
    setIsBinary(false)
    setFileTruncated(false)
    setFileLoading(true)

    try {
      const res = await fsAPI?.readFile(node.path)
      if (!res || 'error' in res) {
        setFileError((res as any)?.error ?? 'Erro ao ler arquivo')
        return
      }

      let content: string = (res as { content: string }).content

      // Binary check
      const nullCount = (content.match(/\x00/g) ?? []).length
      if (nullCount > 5) {
        setIsBinary(true)
        return
      }

      // Truncate
      const lines = content.split('\n')
      if (lines.length > MAX_PREVIEW_LINES) {
        content = lines.slice(0, MAX_PREVIEW_LINES).join('\n')
          + `\n\n// … ${lines.length - MAX_PREVIEW_LINES} linhas omitidas (arquivo muito grande)`
        setFileTruncated(true)
      } else if (content.length > MAX_PREVIEW_BYTES) {
        content = content.slice(0, MAX_PREVIEW_BYTES) + '\n\n// … truncado'
        setFileTruncated(true)
      }

      setFileContent(content)
    } catch (err: any) {
      setFileError(err.message ?? 'Erro desconhecido')
    } finally {
      setFileLoading(false)
    }
  }, [fsAPI])

  // ── Luna action ────────────────────────────────────────────────────────────
  const handleAction = useCallback((actionId: string) => {
    if (!selectedPath || !selectedName) return

    const relPath = workspacePath
      ? selectedPath.replace(workspacePath, '').replace(/^[\\/]/, '')
      : selectedPath
    const ref = `\`${relPath}\``

    const prompts: Record<string, string> = {
      analyze:  `Analise o arquivo ${ref} do workspace. Avalie qualidade, padrões, complexidade ciclomática e sugira melhorias.`,
      bugs:     `Analise o arquivo ${ref} buscando bugs, vulnerabilidades de segurança, race conditions e memory leaks. Liste cada problema com severidade (CRÍTICO/ALTO/MÉDIO) e sugestão de correção.`,
      explain:  `Explique o que o arquivo ${ref} faz: sua responsabilidade, principais funções/classes/structs e como ele se integra ao restante do projeto.`,
      refactor: `Sugira refatorações para o arquivo ${ref}. Foque em legibilidade, performance, aplicação de design patterns e boas práticas da linguagem.`,
      test:     `Gere testes unitários completos para o arquivo ${ref}. Inclua: casos felizes, casos de borda, cenários de erro e mocks necessários.`,
      chat:     `Vou trabalhar com o arquivo ${ref}. O que você quer analisar ou modificar nele?`,
    }

    const prompt = prompts[actionId]
    if (prompt) navigate('/chat', { state: { prefill: prompt } })
  }, [selectedPath, selectedName, workspacePath, navigate])

  // ── Copy content ───────────────────────────────────────────────────────────
  const handleCopy = () => {
    if (!fileContent) return
    navigator.clipboard.writeText(fileContent).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    })
  }

  // ── Search results ─────────────────────────────────────────────────────────
  const q = searchQuery.trim().toLowerCase()
  const searchResults = q ? flattenTree(tree).filter((n) => n.name.toLowerCase().includes(q)).slice(0, 60) : null

  // ── No workspace state ─────────────────────────────────────────────────────
  if (!workspacePath) {
    return (
      <div className="flex flex-col h-full">
        <TopBar title="Workspace" />
        <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center px-8">
          <FolderX size={40} style={{ color: 'rgba(0,212,255,0.18)' }} />
          <div>
            <p className="text-[15px] font-semibold text-cyber-text mb-2">Nenhum workspace aberto</p>
            <p className="text-[13px] text-cyber-muted leading-relaxed">
              Selecione um workspace na sidebar para explorar os arquivos do projeto com Luna.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <TopBar title="Workspace" />

      {/* ── 3-panel layout ────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">

        {/* ── LEFT: File tree (240px) ─────────────────────────────────── */}
        <div
          className="flex-shrink-0 flex flex-col h-full border-r"
          style={{ width: 240, borderColor: 'rgba(0,212,255,0.1)' }}
        >
          {/* Tree header */}
          <div
            className="flex items-center gap-2 px-3 py-2 border-b flex-shrink-0"
            style={{ borderColor: 'rgba(0,212,255,0.08)' }}
          >
            <FolderOpen size={11} style={{ color: '#fbbf24' }} />
            <span className="text-[10px] font-mono text-cyber-muted flex-1 truncate uppercase tracking-wider">
              {workspaceName}
            </span>
            <button
              onClick={loadRoot}
              className="text-cyber-dim hover:text-cyber-cyan transition-colors"
              title="Recarregar"
            >
              <RefreshCw size={10} className={treeLoading ? 'animate-spin' : ''} />
            </button>
          </div>

          {/* Search */}
          <div
            className="flex items-center gap-1.5 px-2.5 py-1.5 border-b flex-shrink-0"
            style={{ borderColor: 'rgba(0,212,255,0.06)' }}
          >
            <Search size={11} className="text-cyber-dim flex-shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Buscar arquivo..."
              className="flex-1 bg-transparent text-[11px] font-mono text-cyber-muted placeholder-cyber-dim outline-none"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="text-cyber-dim hover:text-cyber-muted text-[10px] leading-none"
              >
                ✕
              </button>
            )}
          </div>

          {/* Tree body */}
          <div className="flex-1 overflow-y-auto py-1 px-1">
            {treeLoading && (
              <div className="flex items-center gap-2 px-3 py-4 text-[11px] font-mono text-cyber-dim">
                <Loader2 size={12} className="animate-spin" /> Carregando...
              </div>
            )}
            {treeError && !treeLoading && (
              <div className="flex items-start gap-2 px-3 py-3 text-[10px] font-mono text-red-400">
                <AlertTriangle size={10} className="flex-shrink-0 mt-0.5" />
                <span>{treeError}</span>
              </div>
            )}
            {!treeLoading && !treeError && (
              searchResults !== null ? (
                <>
                  <div className="px-2 py-1 text-[9px] font-mono text-cyber-dim">
                    {searchResults.length} resultado{searchResults.length !== 1 ? 's' : ''}
                  </div>
                  {searchResults.length === 0 ? (
                    <p className="text-[11px] font-mono text-cyber-dim px-3 py-2">Nenhum arquivo encontrado</p>
                  ) : searchResults.map((node) => (
                    <button
                      key={node.path}
                      onClick={() => { setSearchQuery(''); selectFile(node) }}
                      className="flex items-center gap-1.5 w-full text-left py-1 px-2 rounded-md transition-colors"
                      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.04)' }}
                      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                    >
                      {getFileIcon(node.name)}
                      <span className="text-[11px] font-mono text-cyber-muted truncate ml-1.5">{node.name}</span>
                    </button>
                  ))}
                </>
              ) : (
                tree.map((node) => (
                  <FileTreeNode
                    key={node.path}
                    node={node}
                    depth={0}
                    selectedPath={selectedPath}
                    onSelect={selectFile}
                    onToggle={toggleNode}
                  />
                ))
              )
            )}
          </div>
        </div>

        {/* ── CENTER: File preview ─────────────────────────────────────── */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {selectedPath ? (
            <>
              {/* File header bar */}
              <div
                className="flex-shrink-0 flex items-center gap-2 px-4 py-2 border-b"
                style={{
                  borderColor: 'rgba(0,212,255,0.08)',
                  background: 'rgba(8,11,20,0.5)',
                }}
              >
                {getFileIcon(selectedName ?? '')}
                <span className="text-[12px] font-mono text-cyber-muted flex-1 truncate ml-1">
                  {selectedName}
                </span>
                <span
                  className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                  style={{ background: 'rgba(0,212,255,0.06)', color: '#64748b' }}
                >
                  {getLang(selectedName ?? '')}
                </span>
                {fileTruncated && (
                  <span
                    className="text-[9px] font-mono px-1.5 py-0.5 rounded"
                    style={{ background: 'rgba(245,158,11,0.08)', color: '#f59e0b' }}
                  >
                    truncado
                  </span>
                )}
                <button
                  onClick={handleCopy}
                  disabled={!fileContent}
                  className="p-1 rounded transition-colors disabled:opacity-30"
                  style={{ color: copied ? '#10b981' : '#475569' }}
                  onMouseEnter={(e) => { if (fileContent) (e.currentTarget as HTMLElement).style.color = '#00d4ff' }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = copied ? '#10b981' : '#475569' }}
                  title="Copiar conteúdo"
                >
                  {copied ? <CheckCircle2 size={13} /> : <Copy size={13} />}
                </button>
              </div>

              {/* Content area */}
              <div className="flex-1 overflow-auto">
                {fileLoading && (
                  <div className="flex items-center gap-2 px-6 py-8 text-[12px] font-mono text-cyber-dim">
                    <Loader2 size={14} className="animate-spin" /> Carregando arquivo...
                  </div>
                )}

                {!fileLoading && fileError && (
                  <div
                    className="m-4 px-3 py-2.5 rounded-lg text-[11px] font-mono flex items-start gap-2"
                    style={{
                      background: 'rgba(245,158,11,0.06)',
                      border: '1px solid rgba(245,158,11,0.15)',
                      color: '#fbbf24',
                    }}
                  >
                    <AlertTriangle size={12} className="flex-shrink-0 mt-0.5" />
                    {fileError}
                  </div>
                )}

                {!fileLoading && isBinary && (
                  <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
                    <File size={32} style={{ color: 'rgba(0,212,255,0.12)' }} />
                    <p className="text-[12px] font-mono text-cyber-dim">
                      Arquivo binário — pré-visualização não disponível
                    </p>
                  </div>
                )}

                {!fileLoading && !fileError && !isBinary && fileContent !== null && (
                  <SyntaxHighlighter
                    language={getLang(selectedName ?? '')}
                    style={oneDark}
                    showLineNumbers
                    customStyle={{
                      background: 'transparent',
                      padding: '1rem',
                      margin: 0,
                      fontSize: '0.72rem',
                      minHeight: '100%',
                    }}
                    lineNumberStyle={{
                      color: 'rgba(0,212,255,0.18)',
                      fontSize: '0.65rem',
                      minWidth: '3em',
                      userSelect: 'none',
                    }}
                    wrapLongLines={false}
                  >
                    {fileContent}
                  </SyntaxHighlighter>
                )}

                {!fileLoading && !fileError && !isBinary && fileContent === null && (
                  <div className="flex flex-col items-center justify-center py-16 gap-2 text-cyber-dim">
                    <File size={28} style={{ color: 'rgba(0,212,255,0.1)' }} />
                    <span className="text-[12px] font-mono">Arquivo vazio</span>
                  </div>
                )}
              </div>
            </>
          ) : (
            /* Empty state */
            <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center px-8">
              <div
                className="w-14 h-14 rounded-2xl flex items-center justify-center"
                style={{
                  background: 'linear-gradient(135deg, rgba(124,58,237,0.1), rgba(0,212,255,0.1))',
                  border: '1px solid rgba(0,212,255,0.12)',
                }}
              >
                <FileCode size={24} style={{ color: 'rgba(0,212,255,0.35)' }} />
              </div>
              <div>
                <p className="text-[14px] font-semibold text-cyber-muted mb-1.5">
                  Selecione um arquivo
                </p>
                <p className="text-[12px] text-cyber-dim leading-relaxed">
                  Clique em qualquer arquivo na árvore para ver o conteúdo com syntax highlighting.
                  Use as ações Luna para analisar, refatorar ou enviar ao chat.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* ── RIGHT: Luna Actions (220px) ─────────────────────────────── */}
        <div
          className="flex-shrink-0 border-l overflow-hidden"
          style={{ width: 220, borderColor: 'rgba(0,212,255,0.1)' }}
        >
          <LunaActions
            filePath={selectedPath}
            fileName={selectedName}
            onAction={handleAction}
          />
        </div>

      </div>
    </div>
  )
}

export default Workspace
