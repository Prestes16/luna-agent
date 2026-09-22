import React, { useCallback, useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { PanelRight } from 'lucide-react'
import { useStore } from '@store/appStore'
import {
  EXECUTION_PANEL_AUTO_COLLAPSE_WIDTH,
  SIDEBAR_COLLAPSED_WIDTH,
  SIDEBAR_EXPANDED_WIDTH,
  clampExecutionPanelWidth,
} from '@/config/layout'
import Sidebar from './Sidebar'
import ExecutionPanel from './ExecutionPanel'

interface LayoutProps {
  children: React.ReactNode
}

interface DragState {
  active: boolean
  startX: number
  startWidth: number
  currentWidth: number
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const location = useLocation()
  const {
    sidebarCollapsed,
    executionPanelWidth,
    setExecutionPanelWidth,
    executionPanelVisible,
    executionPanelAutoCollapsed,
    setExecutionPanelAutoCollapsed,
  } = useStore()

  const containerRef = useRef<HTMLDivElement>(null)
  const frameRef = useRef<number | null>(null)
  const dragRef = useRef<DragState>({
    active: false,
    startX: 0,
    startWidth: executionPanelWidth,
    currentWidth: executionPanelWidth,
  })

  const isChatRoute = location.pathname === '/chat'
  const showExecPanel = isChatRoute && executionPanelVisible && !executionPanelAutoCollapsed

  const applyPanelWidth = useCallback((width: number) => {
    containerRef.current?.style.setProperty('--execution-panel-width', `${width}px`)
  }, [])

  useEffect(() => {
    dragRef.current.currentWidth = executionPanelWidth
    applyPanelWidth(executionPanelWidth)
  }, [applyPanelWidth, executionPanelWidth])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const updateResponsiveState = (width: number) => {
      const shouldCollapse = isChatRoute && width < EXECUTION_PANEL_AUTO_COLLAPSE_WIDTH
      setExecutionPanelAutoCollapsed(shouldCollapse)
      const safeWidth = clampExecutionPanelWidth(executionPanelWidth, width)
      dragRef.current.currentWidth = safeWidth
      applyPanelWidth(safeWidth)
    }

    const observer = new ResizeObserver(([entry]) => {
      if (entry) updateResponsiveState(entry.contentRect.width)
    })
    observer.observe(container)
    updateResponsiveState(container.clientWidth)

    return () => {
      observer.disconnect()
      setExecutionPanelAutoCollapsed(false)
    }
  }, [applyPanelWidth, executionPanelWidth, isChatRoute, setExecutionPanelAutoCollapsed])

  useEffect(() => {
    const finishDrag = () => {
      if (!dragRef.current.active) return
      dragRef.current.active = false
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current)
        frameRef.current = null
      }
      applyPanelWidth(dragRef.current.currentWidth)
      setExecutionPanelWidth(dragRef.current.currentWidth)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    const handlePointerMove = (event: PointerEvent) => {
      if (!dragRef.current.active || !containerRef.current) return
      const delta = dragRef.current.startX - event.clientX
      dragRef.current.currentWidth = clampExecutionPanelWidth(
        dragRef.current.startWidth + delta,
        containerRef.current.clientWidth,
      )
      if (frameRef.current !== null) return
      frameRef.current = requestAnimationFrame(() => {
        frameRef.current = null
        applyPanelWidth(dragRef.current.currentWidth)
      })
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', finishDrag)
    window.addEventListener('pointercancel', finishDrag)
    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', finishDrag)
      window.removeEventListener('pointercancel', finishDrag)
      finishDrag()
    }
  }, [applyPanelWidth, setExecutionPanelWidth])

  const handleDragStart = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || !containerRef.current) return
    event.preventDefault()
    dragRef.current = {
      active: true,
      startX: event.clientX,
      startWidth: dragRef.current.currentWidth,
      currentWidth: dragRef.current.currentWidth,
    }
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [])

  return (
    <div className="flex h-screen overflow-hidden cyber-bg scanlines">
      <div
        className="flex h-full flex-shrink-0 flex-col border-r border-cyber-border glass-strong transition-[width] duration-200"
        style={{ width: sidebarCollapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_EXPANDED_WIDTH }}
      >
        <Sidebar />
      </div>

      <div
        ref={containerRef}
        className="relative flex min-w-0 flex-1 overflow-hidden"
        style={{ '--execution-panel-width': `${executionPanelWidth}px` } as React.CSSProperties}
      >
        <main className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
          {children}
        </main>

        {showExecPanel ? (
          <>
            <div
              role="separator"
              aria-label="Redimensionar painel de execução"
              aria-orientation="vertical"
              onPointerDown={handleDragStart}
              className="group relative z-10 w-[7px] flex-shrink-0 cursor-col-resize touch-none select-none"
              title="Arrastar para redimensionar"
            >
              <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-cyber-cyan/10 transition-colors group-hover:bg-cyber-cyan/70" />
              <div className="absolute left-1/2 top-1/2 h-10 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-cyber-cyan/0 shadow-none transition-all group-hover:bg-cyber-cyan/70 group-hover:shadow-[0_0_10px_rgba(0,212,255,0.6)]" />
            </div>
            <aside
              className="h-full flex-shrink-0 overflow-hidden border-l border-cyber-cyan/10"
              style={{ width: 'var(--execution-panel-width)' }}
              aria-label="Execução, contexto e estatísticas"
            >
              <ExecutionPanel />
            </aside>
          </>
        ) : null}

        {isChatRoute && executionPanelVisible && executionPanelAutoCollapsed ? (
          <div
            className="pointer-events-none absolute right-2 top-[58px] z-20 flex items-center gap-1 rounded border border-cyber-cyan/10 bg-[#07101c]/90 px-2 py-1 font-mono text-[9px] text-cyber-dim"
            title="O painel voltará automaticamente quando houver espaço"
          >
            <PanelRight size={11} /> painel recolhido pela largura
          </div>
        ) : null}
      </div>
    </div>
  )
}

export default Layout
