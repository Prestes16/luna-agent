/**
 * Luna Bug Report Service
 * Captures unhandled errors + manual reports, stores locally,
 * and optionally forwards to the developer webhook.
 */

export type BugSeverity = 'critical' | 'error' | 'warning' | 'info'

export interface BugReport {
  id: string
  severity: BugSeverity
  title: string
  message: string
  stack?: string
  context: Record<string, string>
  timestamp: number
  sent: boolean
  userNote?: string
}

const STORAGE_KEY = 'luna-bug-reports'
const MAX_STORED  = 50

// ── Storage helpers ────────────────────────────────────────────────────────────

export function getBugReports(): BugReport[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
  } catch {
    return []
  }
}

function saveBugReports(reports: BugReport[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(reports.slice(-MAX_STORED)))
  } catch { /* local storage limit exceeded — ignore */ }
}

export function addBugReport(report: Omit<BugReport, 'id' | 'timestamp' | 'sent'>): BugReport {
  const full: BugReport = {
    ...report,
    id:        `bug-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    timestamp: Date.now(),
    sent:      false,
  }
  const existing = getBugReports()
  saveBugReports([...existing, full])
  return full
}

export function markSent(ids: string[]): void {
  const reports = getBugReports().map(r =>
    ids.includes(r.id) ? { ...r, sent: true } : r
  )
  saveBugReports(reports)
}

export function clearBugReports(): void {
  localStorage.removeItem(STORAGE_KEY)
}

export function deleteBugReport(id: string): void {
  saveBugReports(getBugReports().filter(r => r.id !== id))
}

// ── Severity classifier ────────────────────────────────────────────────────────

function classifySeverity(error: Error | string): BugSeverity {
  const msg = (typeof error === 'string' ? error : error.message).toLowerCase()
  if (msg.includes('chunk load') || msg.includes('network') || msg.includes('fetch'))
    return 'warning'
  if (msg.includes('cannot read') || msg.includes('undefined') || msg.includes('null'))
    return 'error'
  if (msg.includes('overflow') || msg.includes('maximum call') || msg.includes('memory'))
    return 'critical'
  return 'error'
}

// ── Global error capture ───────────────────────────────────────────────────────

let _initialized = false

export function initErrorCapture(): void {
  if (_initialized) return
  _initialized = true

  // Unhandled JS exceptions
  window.addEventListener('error', (ev) => {
    addBugReport({
      severity: classifySeverity(ev.error ?? ev.message),
      title:    ev.message.slice(0, 100),
      message:  ev.message,
      stack:    ev.error?.stack,
      context: {
        file:   `${ev.filename}:${ev.lineno}:${ev.colno}`,
        source: 'window.onerror',
        url:    window.location.hash,
      },
    })
  })

  // Unhandled promise rejections
  window.addEventListener('unhandledrejection', (ev) => {
    const err   = ev.reason
    const msg   = err?.message ?? String(err)
    addBugReport({
      severity: classifySeverity(err ?? msg),
      title:    msg.slice(0, 100),
      message:  msg,
      stack:    err?.stack,
      context: {
        source: 'unhandledrejection',
        url:    window.location.hash,
      },
    })
  })
}

// ── Manual report ──────────────────────────────────────────────────────────────

export function reportManual(
  title: string,
  message: string,
  severity: BugSeverity = 'info',
  extra?: Record<string, string>
): void {
  addBugReport({ severity, title, message, context: { source: 'manual', ...extra } })
}

// ── Send to backend / webhook ──────────────────────────────────────────────────

export async function sendBugReports(
  reports: BugReport[],
  backendUrl: string,
  webhookUrl?: string,
  userNote?: string
): Promise<{ ok: boolean; message: string }> {
  const payload = {
    reports: reports.map(r => ({ ...r, userNote: userNote ?? r.userNote })),
    app_version: '4.0.0',
    platform: navigator.platform,
    user_agent: navigator.userAgent,
    sent_at: new Date().toISOString(),
  }

  try {
    // Always post to our own backend (which stores and optionally forwards)
    const res = await fetch(`${backendUrl}/bug-report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...payload, webhook_url: webhookUrl }),
    })

    if (!res.ok) throw new Error(`Backend returned ${res.status}`)
    markSent(reports.map(r => r.id))
    return { ok: true, message: `${reports.length} relatório(s) enviado(s) com sucesso.` }
  } catch (err: any) {
    return { ok: false, message: `Falha ao enviar: ${err.message}` }
  }
}
