import React, { useRef, useCallback, useEffect } from 'react'
import { useStore } from '@store/appStore'
import Sidebar from './Sidebar'
import ExecutionPanel from './ExecutionPanel'
import { PanelRight } from 'lucide-react'

// Limites do split (frações da área útil, sem sidebar)
const SPLIT_MIN = 0.25   // mínimo 25% para o chat
const SPLIT_MAX = 0.75   // máximo 75% para o chat

interface LayoutProps {
  children: React.ReactNode
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const {
    sidebarCollapsed,
    activePage,
    splitRatio,
    setSplitRatio,
    executionPanelVisible,
    setExecutionPanelVisible,
  } = useStore()

  // Painel de execução apenas na página de chat
  const showExecPanel = activePage === 'chat' && executionPanelVisible

  // ── Drag-to-resize ─────────────────────────────────────────────────────────
  const containerRef = useRef<HTMLDivElement>(null)
  const dragging     = useRef(false)
  const startX       = useRef(0)
  const startRatio   = useRef(splitRatio)

  const onDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    dragging.current   = true
    startX.current     = e.clientX
    startRatio.current = splitRatio
    document.body.style.cursor    = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [splitRatio])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current || !containerRef.current) return
      const containerW = containerRef.current.offsetWidth
      if (containerW === 0) return
      const delta    = e.clientX - startX.current
      const newRatio = startRatio.current + delta / containerW
      setSplitRatio(Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, newRatio)))
    }
    const onUp = () => {
      if (!dragging.current) return
      dragging.current               = false
      document.body.style.cursor    = ''
      document.body.style.userSelect = ''
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup',   onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup',   onUp)
    }
  }, [setSplitRatio])

  return (
    <div className="flex h-screen cyber-bg scanlines overflow-hidden">

      {/* ── Sidebar (ícones) ───────────────────────────────────────────── */}
      <div
        className="flex-shrink-0 flex flex-col h-full transition-all duration-200 glass-strong border-r border-cyber-border"
        style={{ width: sidebarCollapsed ? 56 : 220 }}
      >
        <Sidebar />
      </div>

      {/* ── Área principal: split Chat | Execution ─────────────────────── */}
      <div ref={containerRef} className="flex-1 flex min-w-0 overflow-hidden relative">

        {/* Chat (children) */}
        <div
          className="flex flex-col h-full min-w-0 overflow-hidden"
          style={{ width: showExecPanel ? `${splitRatio * 100}%` : '100%' }}
        >
          {children}
        </div>

        {/* Split drag handle + execution panel */}
        {showExecPanel && (
          <>
            {/* Drag handle — V4 */}
            <div
              onMouseDown={onDragStart}
              className="flex-shrink-0 w-[6px] cursor-col-resize relative group z-10 select-none"
              style={{ background: 'transparent' }}
              title="Arrastar para redimensionar"
            >
              {/* Linha de divisão base */}
              <div
                className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-px transition-all duration-200"
                style={{ background: 'rgba(0,212,255,0.1)' }}
              />
              {/* Glow forte no hover */}
              <div
                className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-[2px] opacity-0 group-hover:opacity-100 transition-all duration-200"
                style={{
                  background: 'linear-gradient(180deg, transparent, rgba(0,212,255,0.6) 20%, rgba(0,212,255,0.8) 50%, rgba(0,212,255,0.6) 80%, transparent)',
                  boxShadow: '0 0 10px rgba(0,212,255,0.6)',
                }}
              />
              {/* Grip dot center */}
              <div
                className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[6px] h-10 flex flex-col items-center justify-center gap-[3px] opacity-0 group-hover:opacity-100 transition-opacity duration-200"
              >
                {[0,1,2,3,4].map((i) => (
                  <div key={i} className="w-[2px] h-[2px] rounded-full" style={{ background: '#00d4ff' }} />
                ))}
              </div>
            </div>

            {/* ExecutionPanel */}
            <div
              className="flex-shrink-0 h-full overflow-hidden border-l"
              style={{
                width:       `${(1 - splitRatio) * 100}%`,
                borderColor: 'rgba(0,212,255,0.1)',
              }}
            >
              <ExecutionPanel />
            </div>
          </>
        )}

        {/* Botão "abrir painel" quando escondido (canto superior direito) */}
        {activePage === 'chat' && !executionPanelVisible && (
          <button
            onClick={() => setExecutionPanelVisible(true)}
            title="Abrir painel de execução"
            className="absolute top-2 right-2 z-20 flex items-center gap-1 text-[10px] font-mono text-cyber-dim hover:text-cyber-cyan transition-colors px-2 py-1 rounded"
            style={{ background: 'rgba(0,212,255,0.06)', border: '1px solid rgba(0,212,255,0.12)' }}
          >
            <PanelRight size={12} />
            <span>Execução</span>
          </button>
        )}
      </div>

    </div>
  )
}

export default Layout
