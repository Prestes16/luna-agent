import React, { useState, useRef, useEffect, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { useStore, Message, ActiveFile, ExecutionAction } from '@store/appStore'
import { useI18n } from '@i18n/hooks'
import TopBar from '@components/TopBar'
import { Send, FolderOpen, Zap, Volume2, VolumeX, Mic, MicOff, ImagePlus, X as XIcon, FolderSymlink, Copy, Check, RotateCcw, Plus, History, Trash2, ChevronDown, Play, ShieldCheck } from 'lucide-react'
import { ChatSession } from '@store/appStore'
import { parseNumberedListItem } from '@/utils/markdown'

// ── Image helpers ─────────────────────────────────────────────────────────────
interface AttachedImage {
  id: string
  dataUrl: string   // para preview (inclui "data:image/...;base64,")
  data: string      // só o base64 (para enviar ao backend)
  mime: string
  name: string
}

function createStreamingMessageWriter(
  messageId: string,
  updateMessage: (id: string, patch: Partial<Message>) => void,
) {
  let latest = ''
  let frame: number | null = null
  let finished = false

  const cancelFrame = () => {
    if (frame !== null) cancelAnimationFrame(frame)
    frame = null
  }

  return {
    push(content: string) {
      latest = content
      if (finished || frame !== null) return
      frame = requestAnimationFrame(() => {
        frame = null
        updateMessage(messageId, { content: latest, isStreaming: true })
      })
    },
    finish(content = latest) {
      if (finished) return
      finished = true
      latest = content
      cancelFrame()
      updateMessage(messageId, { content: latest, isStreaming: false })
    },
  }
}

async function fileToAttachedImage(file: File): Promise<AttachedImage | null> {
  if (!file.type.startsWith('image/')) return null
  if (file.size > 5 * 1024 * 1024) return null  // max 5MB

  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const dataUrl = e.target?.result as string
      const [prefix, data] = dataUrl.split(',')
      const mime = prefix.match(/data:([^;]+)/)?.[1] ?? 'image/png'
      resolve({
        id: `img-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        dataUrl,
        data,
        mime,
        name: file.name,
      })
    }
    reader.onerror = () => resolve(null)
    reader.readAsDataURL(file)
  })
}
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { speak, stop as stopSpeaking, onSpeakingChange, stt } from '../services/voiceService'
import type { STTState } from '../services/voiceService'
import { LunaRequirementsForm, parseLunaForm } from '@components/LunaRequirementsForm'

// ── Code block com botão de copiar ───────────────────────────────────────
const CodeBlock: React.FC<{ lang: string; code: string }> = ({ lang, code }) => {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    }).catch(() => {})
  }
  const displayLang = (lang || 'code').toLowerCase()
  return (
    <div className="luna-code-block my-2 relative group">
      {/* Header separado em dois elementos independentes para não "colar" no copy */}
      <div className="luna-code-header">
        <span
          className="text-[10px] font-mono select-none"
          style={{ color: 'rgba(0,212,255,0.45)', letterSpacing: '0.08em' }}
        >
          {displayLang}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 px-2 py-0.5 rounded text-[9px] font-mono transition-all select-none"
          style={{
            color: copied ? '#4ade80' : 'rgba(0,212,255,0.55)',
            background: copied ? 'rgba(74,222,128,0.08)' : 'rgba(0,212,255,0.04)',
            border: `1px solid ${copied ? 'rgba(74,222,128,0.2)' : 'rgba(0,212,255,0.1)'}`,
          }}
          title={copied ? 'Copiado!' : 'Copiar código'}
        >
          {copied ? <><Check size={9}/> Copiado</> : <><Copy size={9}/> Copiar</>}
        </button>
      </div>
      <SyntaxHighlighter
        language={displayLang}
        style={oneDark}
        customStyle={{ background: 'transparent', padding: '0.75rem', margin: 0, fontSize: '0.75rem' }}
        wrapLongLines
      >
        {code}
      </SyntaxHighlighter>
    </div>
  )
}

// ── Lightweight markdown renderer ────────────────────────────────────────
function renderMarkdown(text: string): React.ReactNode[] {
  const lines = text.split('\n')
  const nodes: React.ReactNode[] = []
  let i = 0
  let key = 0

  while (i < lines.length) {
    const line = lines[i]

    // Fenced code block
    const fenceMatch = line.match(/^```(\w*)/)
    if (fenceMatch) {
      const lang = fenceMatch[1] || 'text'
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i])
        i++
      }
      nodes.push(<CodeBlock key={key++} lang={lang} code={codeLines.join('\n')} />)
      i++ // skip closing ```
      continue
    }

    // Heading — reseta contadores visuais implícitos
    const h3 = line.match(/^### (.+)/)
    const h2 = line.match(/^## (.+)/)
    const h1 = line.match(/^# (.+)/)
    if (h3) { nodes.push(<h3 key={key++} className="text-sm font-bold text-cyber-cyan mt-3 mb-1">{h3[1]}</h3>); i++; continue }
    if (h2) { nodes.push(<h2 key={key++} className="text-base font-bold text-cyber-cyan mt-4 mb-1">{h2[1]}</h2>); i++; continue }
    if (h1) { nodes.push(<h1 key={key++} className="text-lg font-bold text-cyber-cyan mt-4 mb-2">{h1[1]}</h1>); i++; continue }

    // Horizontal rule
    if (line.match(/^---+$/)) { nodes.push(<hr key={key++} className="border-cyber-border my-3" />); i++; continue }

    // Bullet list
    if (line.match(/^[\-\*] /)) {
      const items: string[] = []
      while (i < lines.length && lines[i].match(/^[\-\*] /)) {
        items.push(lines[i].replace(/^[\-\*] /, ''))
        i++
      }
      nodes.push(
        <ul key={key++} className="list-none space-y-0.5 my-1.5 ml-2">
          {items.map((item, idx) => (
            <li key={idx} className="flex items-start gap-1.5 text-[13px]">
              <span className="text-cyber-cyan mt-0.5 text-[10px]">▸</span>
              <span>{inlineMarkdown(item)}</span>
            </li>
          ))}
        </ul>
      )
      continue
    }

    // Numbered list — preserva o marcador declarado e remove só duplicação idêntica.
    if (parseNumberedListItem(line)) {
      const items: Array<{ text: string; num: number }> = []
      while (i < lines.length) {
        const item = parseNumberedListItem(lines[i])
        if (!item) break
        items.push({
          text: item.text,
          num: item.number,
        })
        i++
      }
      nodes.push(
        <ol key={key++} className="space-y-0.5 my-1.5 ml-4 list-none">
          {items.map(({ text, num }, idx) => (
            <li key={idx} className="flex items-start gap-1.5 text-[13px]">
              <span
                className="flex-shrink-0 font-mono text-[10px] mt-0.5 tabular-nums text-right"
                style={{ color: '#a78bfa', minWidth: '1.25rem' }}
              >
                {num}.
              </span>
              <span>{inlineMarkdown(text)}</span>
            </li>
          ))}
        </ol>
      )
      continue
    }

    // Empty line = spacing
    if (line.trim() === '') {
      nodes.push(<div key={key++} className="h-1.5" />)
      i++
      continue
    }

    // Regular paragraph
    nodes.push(
      <p key={key++} className="text-[13px] leading-relaxed">
        {inlineMarkdown(line)}
      </p>
    )
    i++
  }

  return nodes
}

function inlineMarkdown(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**'))
      return <strong key={i} className="text-cyber-text font-semibold">{part.slice(2, -2)}</strong>
    if (part.startsWith('`') && part.endsWith('`'))
      return (
        <code key={i}
          className="px-1 py-0.5 rounded text-[11px] font-mono text-cyber-cyan"
          style={{ background: 'rgba(0,212,255,0.08)', border: '1px solid rgba(0,212,255,0.15)' }}>
          {part.slice(1, -1)}
        </code>
      )
    if (part.startsWith('*') && part.endsWith('*'))
      return <em key={i} className="text-cyber-muted">{part.slice(1, -1)}</em>
    return part
  })
}

// ── Supervised execution action ───────────────────────────────────────────
const ExecutionActionCard: React.FC<{ action: ExecutionAction }> = ({ action }) => {
  const { backendUrl, lunaApiToken, sessionId, addLogLine } = useStore()
  const [state, setState] = useState<'idle' | 'working' | 'done' | 'error'>('idle')
  const [detail, setDetail] = useState('')

  const run = async () => {
    if (state === 'working' || action.authority === 'BLOCKED') return

    const operatorRequest = 'Execute sob demanda este comando aprovado pelo operador: ' + action.command
    let rollbackReady = !action.rollback_required

    if (action.rollback_required) {
      rollbackReady = window.confirm(
        'Esta ação altera estado. Confirma que o rollback/cleanup descrito pela Luna foi revisado e está pronto?'
      )
      if (!rollbackReady) return
    }

    if ((action.destructive || action.persistent_change) && !window.confirm(
      'Ação de alto impacto detectada. Confirma explicitamente a execução exata deste comando?'
    )) return

    setState('working')
    setDetail('')

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(lunaApiToken ? { 'X-Luna-Token': lunaApiToken } : {}),
    }

    try {
      let approvalToken: string | undefined

      if (action.authority === 'APPROVAL_REQUIRED') {
        const approvalRes = await fetch(backendUrl + '/api/execution/approve', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            command: action.command,
            session_id: sessionId,
            operator_request_text: operatorRequest,
            operator_confirmed: true,
            ttl_seconds: 120,
            allow_destructive: Boolean(action.destructive),
            allow_persistent_change: Boolean(action.persistent_change),
            rollback_ready: rollbackReady,
            verification_ready: true,
          }),
        })
        const approvalBody = await approvalRes.json()
        if (!approvalRes.ok) throw new Error(approvalBody?.detail ?? ('approval HTTP ' + approvalRes.status))
        approvalToken = approvalBody.approval_token
      }

      const runRes = await fetch(backendUrl + '/api/execution/run', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          command: action.command,
          session_id: sessionId,
          operator_request_text: operatorRequest,
          approval_token: approvalToken,
          rollback_ready: rollbackReady,
          verification_ready: true,
        }),
      })
      const body = await runRes.json()
      if (!runRes.ok) throw new Error(body?.detail ?? ('execution HTTP ' + runRes.status))

      const executed = body.status === 'executed'
      setState(executed ? 'done' : 'error')
      const summary = executed
        ? 'exit=' + (body.exit_code ?? '?') + ' · backend=' + (body.backend ?? 'unknown')
        : (body.status ?? 'denied') + ' · ' + (body.denial_reasons ?? []).join(', ')
      setDetail(summary)
      addLogLine({
        category: 'SYSTEM',
        level: executed ? 'success' : 'warning',
        text: 'Supervised execution: ' + summary,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setState('error')
      setDetail(message)
      addLogLine({ category: 'SYSTEM', level: 'error', text: 'Execution error: ' + message })
    }
  }

  const blocked = action.authority === 'BLOCKED'
  const badgeColor = blocked
    ? '#ef4444'
    : action.authority === 'APPROVAL_REQUIRED'
      ? '#f59e0b'
      : '#22c55e'

  return (
    <div
      className="mt-2 rounded-md px-2.5 py-2 font-mono text-[10px]"
      style={{ border: '1px solid rgba(0,212,255,0.15)', background: 'rgba(2,8,20,0.65)' }}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <ShieldCheck size={11} style={{ color: badgeColor }} />
        <span style={{ color: badgeColor }}>{action.authority_level}</span>
        <span className="text-cyber-dim">·</span>
        <span style={{ color: badgeColor }}>{action.authority}</span>
        {typeof action.risk_index === 'number' && (
          <span className="ml-auto text-cyber-dim">risk {action.risk_index.toFixed(3)}</span>
        )}
      </div>
      <code className="block whitespace-pre-wrap break-all text-cyber-text mb-2">{action.command}</code>
      {action.target && <div className="text-cyber-dim mb-1">target: {action.target}</div>}
      <div className="flex items-center gap-2">
        <button
          onClick={run}
          disabled={blocked || state === 'working'}
          className="inline-flex items-center gap-1 rounded px-2 py-1 disabled:opacity-40"
          style={{
            color: blocked ? '#ef4444' : '#00d4ff',
            border: '1px solid rgba(0,212,255,0.22)',
            background: 'rgba(0,212,255,0.06)',
          }}
          title={blocked ? 'Intent bloqueado pela política determinística' : 'Executar sob supervisão'}
        >
          <Play size={10} />
          {state === 'working' ? 'Executando...' : blocked ? 'Bloqueado' : 'Executar'}
        </button>
        {detail && (
          <span style={{ color: state === 'done' ? '#4ade80' : '#f59e0b' }}>{detail}</span>
        )}
      </div>
    </div>
  )
}

// ── Message component ────────────────────────────────────────────────────
interface MessageBubbleProps {
  msg: Message
  onSpeak: (content: string) => void
  speakingMsgId: string | null
  onFormSubmit?: (text: string) => void
  onReload?: () => void
}

const MessageBubble: React.FC<MessageBubbleProps> = ({ msg, onSpeak, speakingMsgId, onFormSubmit, onReload }) => {
  const isUser    = msg.role === 'user'
  const isSystem  = msg.role === 'system'
  const isLuna    = msg.role === 'luna'
  const isSpeakingThis = speakingMsgId === msg.id
  const [copied, setCopied] = useState(false)

  // ── Detect :::luna-form block in Luna messages ────────────────────────
  const formData = (!isUser && !isSystem && !msg.isStreaming)
    ? parseLunaForm(msg.content)
    : null

  // ── Detect error messages that can be retried ─────────────────────────
  const isErrorMsg = isLuna && !msg.isStreaming && msg.content && (
    msg.content.startsWith('⚠️') ||
    msg.content.includes('429') ||
    msg.content.includes('rate_limit') ||
    msg.content.includes('Rate limit') ||
    msg.content.includes('Erro de conexão')
  )

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    }).catch(() => {/* silently ignore */})
  }

  return (
    <div className={`flex animate-msg-in ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      {!isUser && !isSystem && (
        <div
          className="flex-shrink-0 w-7 h-7 rounded-full mr-2 flex items-center justify-center text-xs self-end mb-0.5"
          style={{ background: 'linear-gradient(135deg, #7c3aed, #00d4ff)', boxShadow: '0 0 10px rgba(0,212,255,0.3)' }}
        >
          🌙
        </div>
      )}

      <div className={`max-w-[85%] ${isSystem ? 'w-full max-w-full' : ''}`}>
        {/* Tool calls summary */}
        {msg.toolCalls && msg.toolCalls.length > 0 && (
          <div className="mb-1.5 flex flex-wrap gap-1">
            {msg.toolCalls.map((tc) => (
              <span
                key={tc.id}
                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono status-done"
              >
                ✓ {tc.name}
              </span>
            ))}
          </div>
        )}

        {/* DIR_ACCESS card — card especial quando Luna acessa diretório externo */}
        {isSystem && msg.content.startsWith('__DIR_ACCESS__') && (() => {
          let info = { path: '', workspace: '' }
          try { info = JSON.parse(msg.content.replace('__DIR_ACCESS__', '')) } catch { /**/ }
          return (
            <div
              className="flex items-start gap-2 px-3 py-2 rounded-lg text-[11px] font-mono my-1"
              style={{
                background: 'rgba(251,191,36,0.06)',
                border: '1px solid rgba(251,191,36,0.22)',
                color: '#fbbf24',
              }}
            >
              <FolderSymlink size={13} className="flex-shrink-0 mt-0.5 opacity-80" />
              <div className="flex-1 min-w-0">
                <span className="opacity-70">Luna acessou diretório externo: </span>
                <span className="text-amber-300 font-semibold truncate block" title={info.path}>{info.path}</span>
                {info.workspace && (
                  <span className="opacity-50 text-[9px]">workspace atual: {info.workspace}</span>
                )}
              </div>
              <button
                onClick={async () => {
                  const api = window.electronAPI?.workspace
                  if (!api) return
                  const result = await api.openFolderDialog()
                  if (!result.canceled && result.filePaths[0]) {
                    const p = result.filePaths[0]
                    const name = p.split(/[\\/]/).filter(Boolean).pop() ?? p
                    useStore.getState().setWorkspace(p, name)
                  }
                }}
                className="flex-shrink-0 flex items-center gap-1 px-2 py-0.5 rounded text-[9px] transition-all"
                style={{
                  background: 'rgba(251,191,36,0.12)',
                  border: '1px solid rgba(251,191,36,0.3)',
                  color: '#fbbf24',
                  whiteSpace: 'nowrap',
                }}
                title="Trocar workspace para este diretório"
              >
                <FolderOpen size={10} />
                Trocar workspace
              </button>
            </div>
          )
        })()}

        {/* Message content — oculta para DIR_ACCESS (já renderizado acima) */}
        {!(isSystem && msg.content.startsWith('__DIR_ACCESS__')) && (
        <div className={`px-3 py-2.5 ${isUser ? 'msg-user' : isSystem ? 'msg-system' : 'msg-luna'}`}>
          {/* Inline image thumbnails (user messages with attached images) */}
          {isUser && msg.images && msg.images.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {msg.images.map((img, idx) => (
                <div
                  key={idx}
                  className="relative rounded-lg overflow-hidden flex-shrink-0"
                  style={{ width: 72, height: 72, border: '1px solid rgba(0,212,255,0.2)' }}
                  title={img.name}
                >
                  <img
                    src={img.dataUrl}
                    alt={img.name}
                    className="w-full h-full object-cover"
                  />
                </div>
              ))}
            </div>
          )}

          {/* ── Luna form block — rendered as interactive UI ── */}
          {formData ? (
            <>
              {formData.before && (
                <div className="text-cyber-text mb-2">{renderMarkdown(formData.before)}</div>
              )}
              <LunaRequirementsForm
                schema={formData.schema}
                onSubmit={(text) => onFormSubmit?.(text)}
              />
              {formData.after && (
                <div className="text-cyber-text mt-2">{renderMarkdown(formData.after)}</div>
              )}
            </>
          ) : isUser ? (
            <p className="text-[13px] leading-relaxed text-cyber-text whitespace-pre-wrap">{msg.content}</p>
          ) : (
            <div className="text-cyber-text">{renderMarkdown(msg.content)}</div>
          )}

          {msg.isStreaming && (
            <span className="inline-block w-1.5 h-4 ml-0.5 bg-cyber-cyan animate-blink" />
          )}

          {isLuna && !msg.isStreaming && msg.executionActions && msg.executionActions.length > 0 && (
            <div className="mt-2">
              {msg.executionActions.map((action, index) => (
                <ExecutionActionCard key={msg.id + '-exec-' + index} action={action} />
              ))}
            </div>
          )}
        </div>
        )}

        {/* Footer: timestamp + action buttons for luna messages */}
        <div className="flex items-center gap-2 mt-0.5 px-1">
          <p className="text-[9px] text-cyber-dim">
            {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </p>

          {/* Copy button */}
          {isLuna && !msg.isStreaming && msg.content && (
            <button
              onClick={handleCopy}
              className="transition-all flex items-center gap-1"
              style={{ color: copied ? '#4ade80' : 'rgba(0,212,255,0.55)' }}
              onMouseEnter={(e) => {
                if (!copied) (e.currentTarget as HTMLElement).style.color = '#00d4ff'
              }}
              onMouseLeave={(e) => {
                if (!copied) (e.currentTarget as HTMLElement).style.color = 'rgba(0,212,255,0.55)'
              }}
              title={copied ? 'Copiado!' : 'Copiar resposta'}
            >
              {copied ? <Check size={11} /> : <Copy size={11} />}
            </button>
          )}

          {/* Voice button — highlighted */}
          {isLuna && !msg.isStreaming && msg.content && (
            <button
              onClick={() => onSpeak(msg.id)}
              className="transition-all flex items-center gap-1"
              style={{
                color: isSpeakingThis ? '#ef4444' : 'rgba(0,212,255,0.70)',
                filter: isSpeakingThis ? 'drop-shadow(0 0 4px rgba(239,68,68,0.6))' : undefined,
              }}
              onMouseEnter={(e) => {
                if (!isSpeakingThis) {
                  ;(e.currentTarget as HTMLElement).style.color = '#00d4ff'
                  ;(e.currentTarget as HTMLElement).style.filter = 'drop-shadow(0 0 5px rgba(0,212,255,0.7))'
                }
              }}
              onMouseLeave={(e) => {
                if (!isSpeakingThis) {
                  ;(e.currentTarget as HTMLElement).style.color = 'rgba(0,212,255,0.70)'
                  ;(e.currentTarget as HTMLElement).style.filter = ''
                }
              }}
              title={isSpeakingThis ? 'Parar áudio' : 'Ouvir resposta'}
            >
              {isSpeakingThis
                ? <VolumeX size={13} className="animate-pulse" />
                : <Volume2 size={13} />
              }
            </button>
          )}

          {/* Reload / retry button — shown on error messages */}
          {isErrorMsg && onReload && (
            <button
              onClick={onReload}
              className="transition-all flex items-center gap-1 px-2 py-0.5 rounded text-[9px] font-mono"
              style={{
                background: 'rgba(251,191,36,0.08)',
                border: '1px solid rgba(251,191,36,0.3)',
                color: 'rgba(251,191,36,0.8)',
              }}
              onMouseEnter={(e) => {
                ;(e.currentTarget as HTMLElement).style.background = 'rgba(251,191,36,0.15)'
                ;(e.currentTarget as HTMLElement).style.color = '#fbbf24'
                ;(e.currentTarget as HTMLElement).style.borderColor = 'rgba(251,191,36,0.55)'
              }}
              onMouseLeave={(e) => {
                ;(e.currentTarget as HTMLElement).style.background = 'rgba(251,191,36,0.08)'
                ;(e.currentTarget as HTMLElement).style.color = 'rgba(251,191,36,0.8)'
                ;(e.currentTarget as HTMLElement).style.borderColor = 'rgba(251,191,36,0.3)'
              }}
              title="Recarregar/Reenviar última tarefa"
            >
              <RotateCcw size={9} />
              <span>Recarregar</span>
            </button>
          )}
        </div>
      </div>

      {isUser && (
        <div
          className="flex-shrink-0 w-7 h-7 rounded-full ml-2 flex items-center justify-center text-xs self-end mb-0.5 font-bold"
          style={{ background: 'rgba(124,58,237,0.3)', border: '1px solid rgba(124,58,237,0.4)', color: '#e2e8f0' }}
        >
          C
        </div>
      )}
    </div>
  )
}

// ── Typing indicator ─────────────────────────────────────────────────────
const TypingIndicator: React.FC = () => (
  <div className="flex items-end gap-2 mb-3">
    <div
      className="w-7 h-7 rounded-full flex items-center justify-center text-xs flex-shrink-0"
      style={{ background: 'linear-gradient(135deg, #7c3aed, #00d4ff)' }}
    >
      🌙
    </div>
    <div className="msg-luna px-3 py-2.5">
      <div className="flex items-center gap-1.5">
        <div className="typing-dot" />
        <div className="typing-dot" />
        <div className="typing-dot" />
      </div>
    </div>
  </div>
)

// ── Chat page ────────────────────────────────────────────────────────────
const Chat: React.FC = () => {
  const location = useLocation()
  const { t } = useI18n()
  const {
    messages, addMessage, updateMessage,
    isStreaming, setIsStreaming,
    currentStreamingId, setCurrentStreamingId,
    addLiveToolEvent, updateLiveToolEvent, commitLiveToolsToMessage, clearLiveToolEvents,
    addLogLine,
    setProjectContext,
    userContext,
    currentModel, sessionId, backendUrl, workspacePath,
    voiceEnabled, voiceId, voiceSpeed, voiceModel,
    isSpeaking: isSpeakingStore, setIsSpeaking,
    lunaApiToken,
    zeroCloudMode,
    // Chat sessions
    chatSessions, createNewChat, loadChatSession, deleteChatSession, archiveCurrentChat,
  } = useStore()

  const [input, setInput]         = useState('')
  const [showWelcome, setShowWelcome] = useState(messages.length === 0)
  const [showHistory, setShowHistory] = useState(false)
  const [sttState, setSttState]         = useState<STTState>('idle')
  const [sttError, setSttError]         = useState<string | null>(null)
  const [speakingMsgId, setSpeakingMsgId] = useState<string | null>(null)
  const [compressing, setCompressing]   = useState(false)
  const [compressProgress, setCompressProgress] = useState(0)
  const [compressMsg, setCompressMsg]   = useState('')
  const [showJumpToLatest, setShowJumpToLatest] = useState(false)

  // Vision — imagens anexadas à próxima mensagem
  const [attachedImages, setAttachedImages] = useState<AttachedImage[]>([])
  const imageInputRef = useRef<HTMLInputElement>(null)

  const messagesEndRef  = useRef<HTMLDivElement>(null)
  const messagesScrollRef = useRef<HTMLDivElement>(null)
  const shouldFollowMessagesRef = useRef(true)
  const scrollFrameRef = useRef<number | null>(null)
  const inputRef        = useRef<HTMLTextAreaElement>(null)
  const abortRef        = useRef<AbortController | null>(null)
  const toolCounterRef  = useRef(0)
  const prevStreamingRef = useRef(false)

  // Sync speaking state from voiceService → store
  useEffect(() => {
    onSpeakingChange((speaking) => {
      setIsSpeaking(speaking)
      if (!speaking) setSpeakingMsgId(null)
    })
  }, [setIsSpeaking])

  const handleMessagesScroll = useCallback(() => {
    const element = messagesScrollRef.current
    if (!element) return
    const atBottom = element.scrollHeight - element.scrollTop - element.clientHeight < 72
    shouldFollowMessagesRef.current = atBottom
    setShowJumpToLatest((visible) => visible === !atBottom ? visible : !atBottom)
  }, [])

  const scrollToLatest = useCallback((behavior: ScrollBehavior = 'smooth') => {
    shouldFollowMessagesRef.current = true
    setShowJumpToLatest(false)
    messagesEndRef.current?.scrollIntoView({ behavior, block: 'end' })
  }, [])

  // Follow streaming only while the operator remains at the bottom.
  useEffect(() => {
    if (!shouldFollowMessagesRef.current) return
    if (scrollFrameRef.current !== null) cancelAnimationFrame(scrollFrameRef.current)
    scrollFrameRef.current = requestAnimationFrame(() => {
      scrollFrameRef.current = null
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto', block: 'end' })
    })
    return () => {
      if (scrollFrameRef.current !== null) {
        cancelAnimationFrame(scrollFrameRef.current)
        scrollFrameRef.current = null
      }
    }
  }, [messages, isStreaming])

  useEffect(() => {
    if (messages.length > 0) setShowWelcome(false)
  }, [messages.length])

  // Pre-fill from Workspace page actions (navigate state)
  useEffect(() => {
    const prefill = (location.state as any)?.prefill
    if (prefill && typeof prefill === 'string') {
      setInput(prefill)
      inputRef.current?.focus()
      // Clear state so back-navigation doesn't re-fill
      window.history.replaceState({}, '')
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Auto-speak: when streaming ends and voiceEnabled, speak the last luna message
  useEffect(() => {
    const wasStreaming = prevStreamingRef.current
    prevStreamingRef.current = isStreaming

    if (wasStreaming && !isStreaming && voiceEnabled) {
      const lunaMessages = messages.filter(m => m.role === 'luna' && !m.isStreaming && m.content)
      const last = lunaMessages[lunaMessages.length - 1]
      if (last) {
        setSpeakingMsgId(last.id)
        speak(last.content, backendUrl, {
          voice: voiceId as any,
          speed: voiceSpeed,
          model: voiceModel as any,
        }).then(() => setSpeakingMsgId(null))
      }
    }
  }, [isStreaming, voiceEnabled, messages, backendUrl, voiceId, voiceSpeed, voiceModel])

  // Handle per-message speak/stop toggle
  const handleSpeak = useCallback(async (msgId: string) => {
    // If already speaking this message, stop it
    if (speakingMsgId === msgId) {
      stopSpeaking()
      setSpeakingMsgId(null)
      return
    }
    // Stop any other audio
    stopSpeaking()

    const msg = messages.find(m => m.id === msgId)
    if (!msg) return

    setSpeakingMsgId(msgId)
    await speak(msg.content, backendUrl, {
      voice: voiceId as any,
      speed: voiceSpeed,
      model: voiceModel as any,
    })
    setSpeakingMsgId(null)
  }, [speakingMsgId, messages, backendUrl, voiceId, voiceSpeed, voiceModel])

  // STT: start/stop mic
  const handleMic = useCallback(() => {
    if (sttState === 'listening' || sttState === 'processing') {
      stt.stop()
      setSttState('idle')
      return
    }
    setSttError(null)
    stt.start({
      onResult: (transcript, final) => {
        setInput(prev => {
          // Replace interim result — if last part was interim, replace it
          return final ? (prev.trimEnd() + (prev ? ' ' : '') + transcript).trim() : prev
        })
        if (!final) {
          // Show interim in a different way — just append for now
          setInput(transcript)
        }
      },
      onStateChange: (state) => {
        setSttState(state)
        if (state === 'idle') inputRef.current?.focus()
      },
      onError: (msg) => {
        setSttError(msg)
        setSttState('idle')
        setTimeout(() => setSttError(null), 3000)
      },
    }, 'pt-BR')
  }, [sttState])

  const sendMessage = useCallback(async () => {
    if ((!input.trim() && attachedImages.length === 0) || isStreaming) return
    shouldFollowMessagesRef.current = true
    setShowJumpToLatest(false)

    // Stop any STT in progress
    if (sttState !== 'idle') stt.stop()

    // Captura imagens antes de limpar o state
    const imagesToSend = [...attachedImages]
    setAttachedImages([])

    const msgContent = input.trim() || (imagesToSend.length > 0 ? 'Analise esta imagem.' : '')
    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: msgContent,
      timestamp: Date.now(),
      // Armazena dataUrls para exibir thumbnails na mensagem
      images: imagesToSend.length > 0
        ? imagesToSend.map(i => ({ dataUrl: i.dataUrl, name: i.name }))
        : undefined,
    }
    addMessage(userMsg)
    setInput('')
    setIsStreaming(true)
    clearLiveToolEvents()
    toolCounterRef.current = 0

    const lunaId = `luna-${Date.now()}`
    setCurrentStreamingId(lunaId)
    addMessage({
      id: lunaId,
      role: 'luna',
      content: '',
      timestamp: Date.now(),
      isStreaming: true,
    })
    const streamWriter = createStreamingMessageWriter(lunaId, updateMessage)

    try {
      abortRef.current = new AbortController()

      const res = await fetch(`${backendUrl}/chat/agent/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(lunaApiToken ? { 'X-Luna-Token': lunaApiToken } : {}),
        },
        body: JSON.stringify({
          message:          msgContent,
          session_id:       sessionId,
          model:            currentModel,
          workspace_path:   workspacePath || null,
          zero_cloud_mode:  zeroCloudMode,
          user_context:     userContext.trim() || undefined,
          images: imagesToSend.length > 0
            ? imagesToSend.map(i => ({ data: i.data, mime: i.mime }))
            : undefined,
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
              toolCounterRef.current++
              const toolId = `tool-${Date.now()}-${toolCounterRef.current}`
              addLiveToolEvent({
                id: toolId,
                callNum: toolCounterRef.current,
                name: event.name,
                argsSummary: event.args_summary ?? '',
                status: 'running',
                startedAt: Date.now(),
              })
            }

            else if (event.type === 'tool_done') {
              const store = useStore.getState()
              const running = store.liveToolEvents.find(
                (e) => e.name === event.name && e.status === 'running'
              )
              if (running) {
                updateLiveToolEvent(running.id, {
                  status: 'done',
                  resultSummary: event.result_summary,
                  doneAt: Date.now(),
                })
              }
              if (event.name === 'save_context' && event.key) {
                setProjectContext(event.key, event.value ?? '')
              }
            }

            else if (event.type === 'tool_skipped') {
              const store = useStore.getState()
              const running = store.liveToolEvents.find(
                (e) => e.name === event.name && e.status === 'running'
              )
              if (running) {
                updateLiveToolEvent(running.id, { status: 'skipped', doneAt: Date.now() })
              }
            }

            else if (event.type === 'text_chunk') {
              fullText += event.text
              streamWriter.push(fullText)
            }

            else if (event.type === 'response_meta') {
              if (Array.isArray(event.execution_actions)) {
                updateMessage(lunaId, { executionActions: event.execution_actions as ExecutionAction[] })
              }
            }

            else if (event.type === 'done') {
              streamWriter.finish(fullText || event.final_text || '')
              commitLiveToolsToMessage(lunaId)
            }

            else if (event.type === 'compressing') {
              const prog = event.progress as number ?? 0
              const msg  = event.message as string ?? 'Compactando...'
              setCompressing(prog < 100)
              setCompressProgress(prog)
              setCompressMsg(msg)
              // V4: alimenta execution panel com progresso de compressão
              addLogLine({
                category: 'SYSTEM',
                level:    prog >= 100 ? 'success' : 'progress',
                text:     msg,
                progress: prog,
              })
              if (prog >= 100) {
                setTimeout(() => setCompressing(false), 1500)
              }
            }

            else if (event.type === 'file_accessed') {
              const store = useStore.getState()
              const filePath: string = event.path ?? ''
              if (filePath) {
                const wp = store.workspacePath
                const absPath = (wp && !filePath.startsWith('/') && !filePath.match(/^[A-Za-z]:/))
                  ? `${wp}/${filePath}`.replace(/\/+/g, '/')
                  : filePath
                store.addActiveFile({
                  path: absPath,
                  operation: (event.operation as ActiveFile['operation']) ?? 'read',
                  timestamp: Date.now(),
                })
              }
            }

            else if (event.type === 'dir_access') {
              // Luna acessou diretório fora do workspace atual — mostra card informativo
              const accessedPath: string = event.path ?? ''
              const currentWs: string = event.workspace ?? ''
              addMessage({
                id: `dir-access-${Date.now()}`,
                role: 'system',
                content: `__DIR_ACCESS__${JSON.stringify({ path: accessedPath, workspace: currentWs })}`,
                timestamp: Date.now(),
              })
            }

            else if (event.type === 'frontend_action' && event.__action__ === 'open_workspace_dialog') {
              // Luna requested workspace access — open native folder picker
              const api = window.electronAPI?.workspace
              if (api) {
                const result = await api.openFolderDialog()
                if (!result.canceled && result.filePaths[0]) {
                  const p = result.filePaths[0]
                  const name = p.split(/[\\/]/).filter(Boolean).pop() ?? p
                  useStore.getState().setWorkspace(p, name)
                  // Inject a system message so Luna knows workspace is now set
                  addMessage({
                    id: `sys-${Date.now()}`,
                    role: 'system',
                    content: `✅ Workspace configurado: \`${p}\` — Luna agora tem acesso aos arquivos.`,
                    timestamp: Date.now(),
                  })
                }
              }
            }

            else if (event.type === 'frontend_action' && event.__action__ === 'project_context_updated') {
              const store = useStore.getState()
              const wp = store.workspacePath || '_global'
              const content: string = event.content ?? ''
              if (content) {
                store.setProjectMarkdown(wp, content)
                // V4: log no painel de execução
                addLogLine({
                  category: 'SYSTEM',
                  level:    'success',
                  text:     '💾 Contexto do projeto atualizado',
                })
              }
            }

            else if (event.type === 'error') {
              // Limpa barra de progresso (compressing) imediatamente ao receber erro
              setCompressing(false)
              setCompressProgress(0)
              streamWriter.finish(`⚠️ Erro: ${event.message}`)
            }

            // Limpa barra ao finalizar normalmente também
            if (event.type === 'done') {
              setCompressing(false)
              setCompressProgress(0)
            }
          } catch (_) {
            // JSON parse error — ignore
          }
        }
      }
    } catch (error: unknown) {
      setCompressing(false)
      setCompressProgress(0)
      if (error instanceof DOMException && error.name === 'AbortError') streamWriter.finish()
      else streamWriter.finish(`⚠️ Erro de conexão com o backend. Verifique se Luna está rodando em ${backendUrl}`)
    } finally {
      streamWriter.finish()
      setIsStreaming(false)
      setCurrentStreamingId(null)
      abortRef.current = null
    }
  }, [input, isStreaming, sttState, addMessage, updateMessage, setIsStreaming, currentModel, sessionId, backendUrl, workspacePath, userContext])

  // ── Send a message directly with explicit text (used by form submit) ─────────
  // IMPORTANT: mirrors sendMessage SSE handling exactly — must stay in sync.
  const sendRaw = useCallback(async (text: string) => {
    if (!text.trim() || isStreaming) return
    shouldFollowMessagesRef.current = true
    setShowJumpToLatest(false)

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: Date.now(),
    }
    addMessage(userMsg)
    setIsStreaming(true)
    clearLiveToolEvents()
    toolCounterRef.current = 0

    const lunaId = `luna-${Date.now()}`
    setCurrentStreamingId(lunaId)
    addMessage({ id: lunaId, role: 'luna', content: '', timestamp: Date.now(), isStreaming: true })
    const streamWriter = createStreamingMessageWriter(lunaId, updateMessage)

    try {
      abortRef.current = new AbortController()
      const res = await fetch(`${backendUrl}/chat/agent/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(lunaApiToken ? { 'X-Luna-Token': lunaApiToken } : {}),
        },
        body: JSON.stringify({
          message:          text,
          session_id:       sessionId,
          model:            currentModel,
          workspace_path:   workspacePath || null,
          zero_cloud_mode:  zeroCloudMode,
          user_context:     userContext.trim() || undefined,
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
              toolCounterRef.current++
              const toolId = `tool-${Date.now()}-${toolCounterRef.current}`
              addLiveToolEvent({
                id: toolId,
                callNum: toolCounterRef.current,
                name: event.name,
                argsSummary: event.args_summary ?? '',
                status: 'running',
                startedAt: Date.now(),
              })
            }
            else if (event.type === 'tool_done') {
              const store = useStore.getState()
              const running = store.liveToolEvents.find(
                (e) => e.name === event.name && e.status === 'running'
              )
              if (running) {
                updateLiveToolEvent(running.id, {
                  status: 'done',
                  resultSummary: event.result_summary,
                  doneAt: Date.now(),
                })
              }
              if (event.name === 'save_context' && event.key) {
                setProjectContext(event.key, event.value ?? '')
              }
            }
            else if (event.type === 'tool_skipped') {
              const store = useStore.getState()
              const running = store.liveToolEvents.find(
                (e) => e.name === event.name && e.status === 'running'
              )
              if (running) {
                updateLiveToolEvent(running.id, { status: 'skipped', doneAt: Date.now() })
              }
            }
            else if (event.type === 'text_chunk') {
              fullText += event.text
              streamWriter.push(fullText)
            }
            else if (event.type === 'response_meta') {
              if (Array.isArray(event.execution_actions)) {
                updateMessage(lunaId, { executionActions: event.execution_actions as ExecutionAction[] })
              }
            }
            else if (event.type === 'done') {
              streamWriter.finish(fullText || event.final_text || '')
              commitLiveToolsToMessage(lunaId)
            }
            else if (event.type === 'compressing') {
              const prog = event.progress as number ?? 0
              const msg  = event.message as string ?? 'Compactando...'
              setCompressing(prog < 100)
              setCompressProgress(prog)
              setCompressMsg(msg)
              addLogLine({
                category: 'SYSTEM',
                level:    prog >= 100 ? 'success' : 'progress',
                text:     msg,
                progress: prog,
              })
              if (prog >= 100) setTimeout(() => setCompressing(false), 1500)
            }
            else if (event.type === 'file_accessed') {
              const store = useStore.getState()
              const filePath: string = event.path ?? ''
              if (filePath) {
                const wp = store.workspacePath
                const absPath = (wp && !filePath.startsWith('/') && !filePath.match(/^[A-Za-z]:/))
                  ? `${wp}/${filePath}`.replace(/\/+/g, '/') : filePath
                store.addActiveFile({
                  path: absPath,
                  operation: (event.operation as ActiveFile['operation']) ?? 'read',
                  timestamp: Date.now(),
                })
              }
            }
            else if (event.type === 'dir_access') {
              addMessage({
                id: `dir-access-${Date.now()}`,
                role: 'system',
                content: `__DIR_ACCESS__${JSON.stringify({ path: event.path ?? '', workspace: event.workspace ?? '' })}`,
                timestamp: Date.now(),
              })
            }
            else if (event.type === 'frontend_action' && event.__action__ === 'open_workspace_dialog') {
              const api = window.electronAPI?.workspace
              if (api) {
                const result = await api.openFolderDialog()
                if (!result.canceled && result.filePaths[0]) {
                  const p = result.filePaths[0]
                  const name = p.split(/[\\/]/).filter(Boolean).pop() ?? p
                  useStore.getState().setWorkspace(p, name)
                  addMessage({ id: `sys-${Date.now()}`, role: 'system', content: `✅ Workspace configurado: \`${p}\``, timestamp: Date.now() })
                }
              }
            }
            else if (event.type === 'frontend_action' && event.__action__ === 'project_context_updated') {
              const store = useStore.getState()
              const wp = store.workspacePath || '_global'
              const content: string = event.content ?? ''
              if (content) {
                store.setProjectMarkdown(wp, content)
                addLogLine({ category: 'SYSTEM', level: 'success', text: '💾 Contexto do projeto atualizado' })
              }
            }
            else if (event.type === 'error') {
              setCompressing(false)
              setCompressProgress(0)
              streamWriter.finish(`⚠️ Erro: ${event.message}`)
            }
            if (event.type === 'done') {
              setCompressing(false)
              setCompressProgress(0)
            }
          } catch (_) { /* JSON parse error — ignore */ }
        }
      }
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === 'AbortError') streamWriter.finish()
      else streamWriter.finish(`⚠️ Erro de conexão com o backend. Verifique se Luna está rodando em ${backendUrl}`)
    } finally {
      streamWriter.finish()
      setIsStreaming(false)
      setCurrentStreamingId(null)
      abortRef.current = null
    }
  }, [isStreaming, addMessage, updateMessage, setIsStreaming, currentModel, sessionId, backendUrl, workspacePath, lunaApiToken, userContext, addLiveToolEvent, updateLiveToolEvent, commitLiveToolsToMessage, clearLiveToolEvents, setProjectContext, addLogLine, setCompressing, setCompressProgress, setCompressMsg])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const stopStreaming = () => {
    abortRef.current?.abort()
    setIsStreaming(false)
  }

  // ── Suggested prompts
  const suggestions = [
    { icon: '🔍', text: 'Analise o projeto em /mnt/d/Dev/meu-app' },
    { icon: '🛡️', text: 'Encontre vulnerabilidades no contrato Solana' },
    { icon: '⚡', text: 'Revise o código em /mnt/d/Dev/backend e sugira melhorias' },
    { icon: '🌐', text: 'Pesquise ataques de reentrancy em programas Anchor' },
  ]

  const micActive    = sttState === 'listening' || sttState === 'processing'
  const micSupported = stt.supported

  // Auto-archive quando Luna termina de responder (streaming para → false)
  useEffect(() => {
    if (!isStreaming && messages.length > 0) {
      archiveCurrentChat()
    }
  }, [isStreaming]) // eslint-disable-line

  return (
    <div className={`flex flex-col h-full relative chat-area-v4${isStreaming ? ' is-streaming' : ''}`}>
      <TopBar title="Chat" />

      {/* Barra de ação rápida: Nova Conversa + Histórico */}
      <div
        className="flex items-center gap-2 px-3 py-1.5"
        style={{
          background: 'rgba(5,8,16,0.9)',
          borderBottom: '1px solid rgba(0,212,255,0.07)',
        }}
      >
        <button
          onClick={() => { createNewChat(); setShowHistory(false) }}
          disabled={isStreaming}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-mono transition-all"
          style={{
            background: 'rgba(0,212,255,0.07)',
            border: '1px solid rgba(0,212,255,0.18)',
            color: isStreaming ? 'rgba(0,212,255,0.3)' : '#00d4ff',
          }}
          title="Nova conversa (salva o chat atual)"
        >
          <Plus size={10} />
          Nova conversa
        </button>

        <button
          onClick={() => setShowHistory((v) => !v)}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-mono transition-all"
          style={{
            background: showHistory ? 'rgba(124,58,237,0.15)' : 'transparent',
            border: `1px solid ${showHistory ? 'rgba(124,58,237,0.4)' : 'rgba(0,212,255,0.1)'}`,
            color: showHistory ? '#a78bfa' : 'rgba(0,212,255,0.5)',
          }}
          title="Ver histórico de conversas"
        >
          <History size={10} />
          Histórico {chatSessions.length > 0 && <span className="opacity-60">({chatSessions.length})</span>}
        </button>
      </div>

      {/* Painel de histórico */}
      {showHistory && (
        <div
          className="border-b overflow-y-auto"
          style={{
            maxHeight: 220,
            borderColor: 'rgba(124,58,237,0.2)',
            background: 'rgba(10,15,28,0.95)',
          }}
        >
          {chatSessions.length === 0 ? (
            <div className="flex items-center justify-center h-16 text-[11px] text-cyber-dim">
              Nenhuma conversa salva ainda
            </div>
          ) : (
            <div className="divide-y" style={{ borderColor: 'rgba(255,255,255,0.04)' }}>
              {chatSessions.map((session: ChatSession) => (
                <div
                  key={session.id}
                  className="flex items-center gap-2 px-3 py-2 group cursor-pointer transition-all"
                  style={{ background: session.id === sessionId ? 'rgba(0,212,255,0.06)' : 'transparent' }}
                  onMouseEnter={(e) => { if (session.id !== sessionId) (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.03)' }}
                  onMouseLeave={(e) => { if (session.id !== sessionId) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                  onClick={() => { loadChatSession(session.id); setShowHistory(false) }}
                >
                  <div className="flex-1 min-w-0">
                    <p
                      className="text-[11px] truncate"
                      style={{ color: session.id === sessionId ? '#00d4ff' : '#e2e8f0' }}
                    >
                      {session.id === sessionId && <span className="text-cyber-cyan mr-1">▸</span>}
                      {session.title}
                    </p>
                    <p className="text-[9px] text-cyber-dim mt-0.5">
                      {new Date(session.updatedAt).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                      {session.workspaceName && <span className="ml-2 opacity-60">📁 {session.workspaceName}</span>}
                      <span className="ml-2 opacity-40">{session.messages.length} msgs</span>
                    </p>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteChatSession(session.id) }}
                    className="opacity-0 group-hover:opacity-60 hover:!opacity-100 transition-all p-1 rounded"
                    style={{ color: '#ef4444' }}
                    title="Apagar conversa"
                  >
                    <Trash2 size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Local runtime notice */}
      {zeroCloudMode && (
        <div
          className="flex items-center gap-2 px-4 py-1.5 text-[10px] font-mono"
          style={{
            background: 'rgba(0,212,255,0.035)',
            borderBottom: '1px solid rgba(0,212,255,0.08)',
            color: '#94a3b8',
          }}
        >
          <span>🔒</span>
          <span><strong>Operação local supervisionada</strong> · zero-cloud · Ollama</span>
        </div>
      )}

      {/* Messages area */}
      <div ref={messagesScrollRef} onScroll={handleMessagesScroll} className="flex-1 overflow-y-auto px-4 py-4">
        {showWelcome && messages.length === 0 ? (
          <div className="flex h-full max-w-xl flex-col items-center justify-center gap-6 px-4 mx-auto">
            <div className="relative">
              <div
                className="flex h-16 w-16 items-center justify-center rounded-xl border border-cyber-cyan/30 bg-[#0d1728] text-3xl"
                style={{
                  boxShadow: '0 0 8px rgba(0,212,255,0.16)',
                }}
              >
                🌙
              </div>
              <div
                className="absolute -bottom-1.5 -right-3 rounded-full px-2 py-0.5 font-mono text-[8px] font-bold"
                style={{
                  background: 'rgba(20,241,149,0.12)',
                  border: '1px solid rgba(20,241,149,0.3)',
                  color: '#14f195',
                  letterSpacing: '0.1em',
                }}
              >
                LOCAL
              </div>
            </div>

            <div className="space-y-2 text-center">
              <h1 className="font-mono text-2xl font-bold tracking-tight text-cyber-text">Luna Cyber</h1>
              <p className="text-[12px] leading-relaxed text-cyber-muted">
                Copiloto local para análise, desenvolvimento e segurança.
              </p>
            </div>

            <div className="grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
              {suggestions.map((s, i) => (
                <button
                  type="button"
                  key={i}
                  onClick={() => setInput(s.text)}
                  className="rounded-lg border border-cyber-cyan/10 bg-[#0a101c]/80 p-3 text-left font-mono text-[11px] text-cyber-muted transition-colors hover:border-cyber-cyan/30 hover:bg-[#0d1728] hover:text-cyber-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan/50"
                  style={{
                    boxShadow: 'inset 0 1px 0 rgba(0,212,255,0.04)',
                  }}
                >
                  <span className="block text-base mb-1">{s.icon}</span>
                  {s.text}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg, idx) => {
              // onReload: só para mensagens de erro da Luna
              let reloadFn: (() => void) | undefined = undefined
              if (msg.role === 'luna' && !msg.isStreaming) {
                const prevMsgs = [...messages].slice(0, idx).reverse()
                const lastUserMsg = prevMsgs.find((m) => m.role === 'user')
                if (lastUserMsg) {
                  reloadFn = () => {
                    // Coleta contexto real: ferramentas já usadas + progresso Luna
                    const toolsUsed: string[] = []
                    prevMsgs.forEach(m => {
                      if (m.role === 'luna' && m.toolCalls) {
                        m.toolCalls.forEach(tc => { if (!toolsUsed.includes(tc.name)) toolsUsed.push(tc.name) })
                      }
                    })
                    const lastGoodLuna = prevMsgs.find(
                      m => m.role === 'luna' && !m.isStreaming && m.content && !m.content.startsWith('⚠️') && m.content.trim().length > 30
                    )
                    const ws = workspacePath || 'não definido'
                    const toolsSummary = toolsUsed.length > 0 ? `Ferramentas já executadas: ${toolsUsed.join(', ')}.` : ''
                    const progressSummary = lastGoodLuna?.content?.trim()
                      ? `Seu último relatório antes da interrupção: "${lastGoodLuna.content.trim().slice(0, 250)}"`
                      : ''
                    const parts = [
                      `[RECOVERY — continuando após erro/rate limit]`,
                      `Workspace ativo: ${ws}`,
                      toolsSummary,
                      progressSummary,
                      `NÃO recomece do zero. Continue EXATAMENTE de onde parou.`,
                      `Tarefa original: ${lastUserMsg.content}`,
                    ].filter(Boolean)
                    sendRaw(parts.join('\n'))
                  }
                }
              }
              return (
                <MessageBubble
                  key={msg.id}
                  msg={msg}
                  onSpeak={handleSpeak}
                  speakingMsgId={speakingMsgId}
                  onFormSubmit={sendRaw}
                  onReload={reloadFn}
                />
              )
            })}
            {isStreaming && (!currentStreamingId || messages.find((m) => m.id === currentStreamingId)?.content === '') && (
              <TypingIndicator />
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {showJumpToLatest ? (
        <button
          type="button"
          onClick={() => scrollToLatest()}
          className="absolute bottom-[112px] left-1/2 z-20 flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-cyber-cyan/25 bg-[#08111f]/95 px-3 py-1.5 font-mono text-[10px] text-cyber-cyan shadow-lg shadow-black/30 transition-colors hover:border-cyber-cyan/45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan/50"
          aria-label="Ir para a última mensagem"
        >
          <ChevronDown size={12} /> última mensagem
        </button>
      ) : null}

      {/* Compression progress banner */}
      {compressing && (
        <div
          className="mx-4 mb-1 px-3 py-2 rounded-lg flex items-center gap-3"
          style={{
            background: 'rgba(124,58,237,0.08)',
            border: '1px solid rgba(124,58,237,0.25)',
          }}
        >
          {/* Spinner */}
          <div className="spinner-cyber flex-shrink-0" style={{ borderTopColor: '#7c3aed' }} />
          <div className="flex-1 min-w-0">
            <div className="text-[11px] font-mono text-purple-300 mb-1 truncate">
              {compressMsg}
            </div>
            <div className="h-1 rounded-full overflow-hidden" style={{ background: 'rgba(124,58,237,0.15)' }}>
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${compressProgress}%`,
                  background: 'linear-gradient(90deg, #7c3aed, #00d4ff)',
                  boxShadow: '0 0 6px rgba(124,58,237,0.5)',
                }}
              />
            </div>
          </div>
          <span className="text-[10px] font-mono text-purple-400 flex-shrink-0">
            {compressProgress}%
          </span>
        </div>
      )}

      {/* STT error toast */}
      {sttError && (
        <div
          className="mx-4 mb-1 px-3 py-2 rounded-lg text-[11px] font-mono flex items-center gap-2"
          style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444' }}
        >
          <MicOff size={12} /> {sttError}
        </div>
      )}

      {/* Speaking indicator bar */}
      {isSpeakingStore && (
        <div
          className="mx-4 mb-1 px-3 py-1.5 rounded-lg flex items-center gap-2"
          style={{ background: 'rgba(0,212,255,0.06)', border: '1px solid rgba(0,212,255,0.2)' }}
        >
          <Volume2 size={12} className="text-cyber-cyan animate-pulse" />
          <span className="text-[10px] font-mono text-cyber-cyan flex-1">Luna está falando...</span>
          <button
            onClick={() => { stopSpeaking(); setSpeakingMsgId(null) }}
            className="text-[10px] font-mono text-cyber-red hover:text-red-400 transition-colors"
          >
            ✕ parar
          </button>
        </div>
      )}

      {/* Input area */}
      <div className="flex-shrink-0 px-4 pb-4 pt-2 chat-input-v4">
        {/* Attached images preview strip */}
        {attachedImages.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2 px-1">
            {attachedImages.map((img) => (
              <div
                key={img.id}
                className="relative rounded-lg overflow-hidden flex-shrink-0 group"
                style={{ width: 64, height: 64, border: '1px solid rgba(0,212,255,0.25)' }}
              >
                <img
                  src={img.dataUrl}
                  alt={img.name}
                  className="w-full h-full object-cover"
                  title={img.name}
                />
                {/* Remove button */}
                <button
                  onClick={() => setAttachedImages(prev => prev.filter(i => i.id !== img.id))}
                  className="absolute top-0.5 right-0.5 w-4 h-4 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ background: 'rgba(0,0,0,0.75)', color: '#ef4444' }}
                  title="Remover imagem"
                >
                  <XIcon size={10} />
                </button>
              </div>
            ))}
            <div className="flex items-center self-center ml-1">
              <span className="text-[10px] font-mono text-cyber-dim">
                {attachedImages.length}/4 {attachedImages.length === 4 ? '· máx atingido' : ''}
              </span>
            </div>
          </div>
        )}

        <div
          className={`flex items-end gap-2 rounded-xl p-2${isStreaming ? ' input-streaming' : ''}`}
          style={{
            background: 'rgba(10,15,26,0.9)',
            border: `1px solid ${
              micActive
                ? 'rgba(239,68,68,0.4)'
                : isStreaming
                  ? 'rgba(0,212,255,0.35)'
                  : 'rgba(0,212,255,0.14)'
            }`,
            boxShadow: micActive
              ? '0 0 20px rgba(239,68,68,0.12)'
              : isStreaming
                ? '0 0 20px rgba(0,212,255,0.14)'
                : '0 2px 12px rgba(0,0,0,0.3)',
            transition: 'border-color 0.2s, box-shadow 0.2s',
          }}
        >
          {/* Folder quick button */}
          <button
            type="button"
            onClick={() => setInput('/allow ')}
            className="p-2 rounded-lg transition-colors text-cyber-muted hover:text-cyber-cyan flex-shrink-0 self-end"
            title="Liberar diretório"
            aria-label="Liberar diretório"
          >
            <FolderOpen size={16} />
          </button>

          {/* Image upload button */}
          <button
            type="button"
            onClick={() => imageInputRef.current?.click()}
            disabled={isStreaming || attachedImages.length >= 4}
            className="p-2 rounded-lg transition-colors flex-shrink-0 self-end"
            style={{ color: attachedImages.length > 0 ? '#00d4ff' : '#475569' }}
            title="Anexar imagem (PNG, JPG, WEBP — max 5MB)"
            aria-label="Anexar imagem"
          >
            <ImagePlus size={16} />
          </button>
          <input
            ref={imageInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            className="hidden"
            onChange={async (e) => {
              const files = Array.from(e.target.files ?? [])
              const converted = await Promise.all(files.map(fileToAttachedImage))
              const valid = converted.filter(Boolean) as AttachedImage[]
              setAttachedImages(prev => [...prev, ...valid].slice(0, 4))
              e.target.value = ''  // reset para permitir re-upload do mesmo arquivo
            }}
          />

          {/* Textarea */}
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              micActive
                ? sttState === 'listening' ? '🎙️ Ouvindo...' : '⏳ Processando...'
                : t('chat.placeholder')
            }
            rows={1}
            className="flex-1 resize-none bg-transparent text-[13px] text-cyber-text placeholder-cyber-dim outline-none leading-relaxed py-1.5"
            style={{ maxHeight: 160, minHeight: 36 }}
            onInput={(e) => {
              const t = e.currentTarget
              t.style.height = 'auto'
              t.style.height = `${Math.min(t.scrollHeight, 160)}px`
            }}
            disabled={isStreaming}
          />

          {/* Mic button (STT) */}
          {micSupported && (
            <button
              type="button"
              onClick={handleMic}
              disabled={isStreaming}
              className="flex-shrink-0 p-2 rounded-lg transition-all self-end"
              style={micActive
                ? { background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.4)', color: '#ef4444' }
                : { background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.12)', color: '#475569' }
              }
              title={micActive ? 'Parar gravação' : 'Falar com Luna (voz → texto)'}
              aria-label={micActive ? 'Parar gravação' : 'Falar com Luna'}
            >
              {micActive
                ? <Mic size={16} className="animate-pulse" />
                : <Mic size={16} />
              }
            </button>
          )}

          {/* Send or Stop */}
          {isStreaming ? (
            <button
              type="button"
              onClick={stopStreaming}
              className="flex-shrink-0 p-2 rounded-lg transition-all self-end"
              style={{ background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444' }}
              title="Parar"
              aria-label="Parar geração"
            >
              <Zap size={16} />
            </button>
          ) : (
            <button
              type="button"
              onClick={sendMessage}
              disabled={!input.trim() && attachedImages.length === 0}
              className="flex-shrink-0 p-2 rounded-lg transition-all self-end"
              style={{
                background: (input.trim() || attachedImages.length > 0) ? 'rgba(0,212,255,0.15)' : 'rgba(0,212,255,0.04)',
                border: `1px solid ${(input.trim() || attachedImages.length > 0) ? 'rgba(0,212,255,0.4)' : 'rgba(0,212,255,0.1)'}`,
                color: (input.trim() || attachedImages.length > 0) ? '#00d4ff' : '#334155',
                boxShadow: (input.trim() || attachedImages.length > 0) ? '0 0 10px rgba(0,212,255,0.2)' : 'none',
              }}
              title="Enviar (Enter)"
              aria-label="Enviar mensagem"
            >
              <Send size={16} />
            </button>
          )}
        </div>

        <p className="text-[9px] text-cyber-dim mt-1.5 text-center font-mono">
          {t('chat.hint')} ·{' '}
          {micSupported ? <><Mic size={9} className="inline" /> para falar · </> : null}
          <Volume2 size={9} className="inline" /> para ouvir respostas
        </p>
      </div>
    </div>
  )
}

export default Chat
