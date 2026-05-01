/**
 * WorkspaceSelector — lets the user pick or create the folder Luna works in.
 * Rendered in the Sidebar. Calls Electron IPC via window.electronAPI.workspace.
 */
import React, { useState, useEffect, useRef } from 'react'
import { FolderOpen, FolderPlus, X, CheckCircle, AlertCircle } from 'lucide-react'
import { useStore } from '@store/appStore'

const WorkspaceSelector: React.FC<{ collapsed?: boolean }> = ({ collapsed }) => {
  const { workspacePath, workspaceName, backendUrl, setWorkspace, clearWorkspace } = useStore()
  const [loading, setLoading]     = useState(false)
  const [showNew, setShowNew]     = useState(false)
  const [newName, setNewName]     = useState('')
  const [error, setError]         = useState('')
  const [stack, setStack]         = useState<string[]>([])
  const [fileCount, setFileCount] = useState<number>(0)

  const api = window.electronAPI?.workspace

  // ── Re-register persisted workspace with backend on mount ────────────────
  // This ensures the backend's global _real_workspace is populated after
  // a restart even if the user never touches the workspace selector.
  const registeredRef = useRef<string>('')
  useEffect(() => {
    if (!workspacePath || registeredRef.current === workspacePath) return
    registeredRef.current = workspacePath
    const base = (backendUrl || 'http://127.0.0.1:8000').replace(/\/$/, '')
    fetch(`${base}/api/workspace/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: workspacePath }),
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data) {
          setStack(data.response?.stack ?? [])
          setFileCount(data.response?.files ?? 0)
        }
      })
      .catch(() => { /* backend offline — retry next message */ })
  }, [workspacePath, backendUrl])

  // ── Registra no backend E no Electron main process ────────────────────────
  const applyWorkspace = async (chosen: string) => {
    const name = chosen.split(/[\\/]/).filter(Boolean).pop() ?? chosen
    setWorkspace(chosen, name)
    // 1. Notifica Electron main process (guards de fs:)
    await api?.setWorkspace?.(chosen).catch(() => {})
    // 2. Registra no backend — injeta contexto real no system prompt
    try {
      const base = (backendUrl || 'http://127.0.0.1:8000').replace(/\/$/, '')
      const res = await fetch(`${base}/api/workspace/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: chosen }),
      })
      if (res.ok) {
        const data = await res.json()
        setStack(data.response?.stack ?? [])
        setFileCount(data.response?.files ?? 0)
      }
    } catch { /* backend pode estar offline — continua */ }
  }

  // ── Select existing folder ─────────────────────────────────────────────────
  const handleSelect = async () => {
    if (!api) return
    setLoading(true)
    setError('')
    try {
      const result = await api.openFolderDialog()
      if (!result.canceled && result.filePaths[0]) {
        await applyWorkspace(result.filePaths[0])
      }
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  // ── Create new project folder ──────────────────────────────────────────────
  const handleCreate = async () => {
    if (!api || !newName.trim()) return
    setLoading(true)
    setError('')
    try {
      const result = await api.newProjectDialog(newName.trim())
      if (!result.canceled && result.filePaths[0]) {
        await applyWorkspace(result.filePaths[0])
        setShowNew(false)
        setNewName('')
      }
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  // ── Collapsed sidebar: just show icon ─────────────────────────────────────
  if (collapsed) {
    return (
      <button
        onClick={handleSelect}
        className="sidebar-link w-full"
        title={workspacePath || 'Selecionar pasta de trabalho'}
        data-tooltip="Workspace"
      >
        <FolderOpen
          size={16}
          className={workspacePath ? 'text-cyber-cyan' : 'text-cyber-muted'}
        />
      </button>
    )
  }

  // ── Expanded sidebar ───────────────────────────────────────────────────────
  return (
    <div
      className="mx-2 mb-2 rounded-lg overflow-hidden"
      style={{ border: '1px solid rgba(0,212,255,0.12)', background: 'rgba(0,212,255,0.03)' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-2.5 py-1.5 border-b"
        style={{ borderColor: 'rgba(0,212,255,0.08)' }}>
        <span className="text-[9px] font-mono text-cyber-muted uppercase tracking-[0.12em]">Workspace</span>
        {workspacePath && (
          <button
            onClick={clearWorkspace}
            className="text-cyber-dim hover:text-cyber-red transition-colors"
            title="Remover workspace"
          >
            <X size={10} />
          </button>
        )}
      </div>

      {/* Current workspace display */}
      <div className="px-2.5 pt-2 pb-1">
        {workspacePath ? (
          <div className="mb-1.5 space-y-1">
            <div className="flex items-center gap-1.5">
              <CheckCircle size={10} className="text-cyber-green flex-shrink-0" />
              <span
                className="text-[10px] font-mono text-cyber-cyan truncate"
                title={workspacePath}
              >
                {workspaceName || workspacePath}
              </span>
            </div>
            {/* Stack badges + file count */}
            {(stack.length > 0 || fileCount > 0) && (
              <div className="flex items-center gap-1 flex-wrap pl-3.5">
                {stack.map((s) => (
                  <span
                    key={s}
                    className="text-[8px] font-mono px-1 py-0.5 rounded"
                    style={{
                      background: 'rgba(124,58,237,0.12)',
                      border: '1px solid rgba(124,58,237,0.2)',
                      color: '#a78bfa',
                    }}
                  >
                    {s}
                  </span>
                ))}
                {fileCount > 0 && (
                  <span
                    className="text-[8px] font-mono px-1 py-0.5 rounded"
                    style={{
                      background: 'rgba(0,212,255,0.06)',
                      border: '1px solid rgba(0,212,255,0.12)',
                      color: '#64748b',
                    }}
                  >
                    {fileCount} files
                  </span>
                )}
              </div>
            )}
          </div>
        ) : (
          <p className="text-[10px] font-mono text-cyber-dim mb-1.5">
            Nenhuma pasta selecionada
          </p>
        )}

        {error && (
          <div className="flex items-center gap-1 mb-1.5">
            <AlertCircle size={10} className="text-cyber-red" />
            <span className="text-[9px] font-mono text-cyber-red">{error}</span>
          </div>
        )}

        {/* Buttons */}
        {!showNew ? (
          <div className="flex gap-1">
            <button
              onClick={handleSelect}
              disabled={loading}
              className="flex-1 flex items-center justify-center gap-1 py-1 rounded text-[9px] font-mono transition-all"
              style={{
                background: 'rgba(0,212,255,0.06)',
                border: '1px solid rgba(0,212,255,0.18)',
                color: '#64748b',
              }}
            >
              <FolderOpen size={10} />
              {loading ? '...' : 'Selecionar'}
            </button>
            <button
              onClick={() => setShowNew(true)}
              disabled={loading}
              className="flex-1 flex items-center justify-center gap-1 py-1 rounded text-[9px] font-mono transition-all"
              style={{
                background: 'rgba(124,58,237,0.06)',
                border: '1px solid rgba(124,58,237,0.18)',
                color: '#a78bfa',
              }}
            >
              <FolderPlus size={10} />
              Novo
            </button>
          </div>
        ) : (
          <div className="space-y-1">
            <input
              autoFocus
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              placeholder="Nome do projeto..."
              className="input-cyber w-full text-[10px] font-mono py-1"
            />
            <div className="flex gap-1">
              <button
                onClick={handleCreate}
                disabled={!newName.trim() || loading}
                className="flex-1 py-1 rounded text-[9px] font-mono transition-all"
                style={{
                  background: 'rgba(0,212,255,0.1)',
                  border: '1px solid rgba(0,212,255,0.3)',
                  color: '#00d4ff',
                }}
              >
                {loading ? '...' : 'Criar'}
              </button>
              <button
                onClick={() => { setShowNew(false); setNewName('') }}
                className="px-2 py-1 rounded text-[9px] font-mono"
                style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.1)', color: '#64748b' }}
              >
                Cancelar
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default WorkspaceSelector
