/**
 * Credits.tsx — Luna Pay-Flow
 * Exibe saldo, planos e histórico.
 * Pagamento é feito via página web externa (/pay) aberta no browser padrão.
 */
import { useEffect, useState, useCallback } from 'react'
import { useStore } from '@store/appStore'
import {
  Zap, RefreshCw, AlertCircle,
  Copy, Check, Coins, TrendingUp, Shield,
  ExternalLink, Link2,
} from 'lucide-react'

// ── Constantes ────────────────────────────────────────────────────────────────
// Grains match backend GRAINS_PER_USDC = 1000 (1 USDC = 1000 base Grains).
// Plans include a volume bonus — bigger plan = more bonus Grains on top.
const PLANS = [
  { usdc: 29,  grains: 30000,  label: 'Starter',    desc: '~15k msgs chat / 2k scans',   color: '#00d4ff', popular: false },
  { usdc: 79,  grains: 95000,  label: 'Builder',    desc: '~47k msgs ou 6.3k scans',      color: '#7c3aed', popular: true  },
  { usdc: 199, grains: 270000, label: 'Pro Hunter', desc: '~135k msgs ou 18k scans',      color: '#10b981', popular: false },
  { usdc: 499, grains: 750000, label: 'Elite',      desc: 'Bounty & audit sem limites',   color: '#f59e0b', popular: false },
]

// ── Tipos ─────────────────────────────────────────────────────────────────────
interface HistoryEntry {
  id: string
  usdc_amount: number
  grains_credited: number
  status: string
  created_at: string
  tx_signature?: string
}

// ── Utils ─────────────────────────────────────────────────────────────────────
const statusColor = (s: string) =>
  s === 'finalized' ? '#10b981' : s === 'pending' ? '#f59e0b' : s === 'expired' ? '#ef4444' : '#64748b'
const statusLabel = (s: string) =>
  s === 'finalized' ? 'Confirmado' : s === 'pending' ? 'Aguardando' : s === 'expired' ? 'Expirado' : s

function timeSince(iso: string) {
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (m < 1) return 'agora'
  if (m < 60) return `${m}m atrás`
  const h = Math.floor(m / 60)
  return h < 24 ? `${h}h atrás` : `${Math.floor(h / 24)}d atrás`
}

// ── CopyBtn ───────────────────────────────────────────────────────────────────
function CopyBtn({ text, label }: { text: string; label?: string }) {
  const [ok, setOk] = useState(false)
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setOk(true); setTimeout(() => setOk(false), 2000) }}
      className="flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-mono transition-all"
      style={{
        background: ok ? 'rgba(16,185,129,0.15)' : 'rgba(0,212,255,0.08)',
        border: `1px solid ${ok ? 'rgba(16,185,129,0.3)' : 'rgba(0,212,255,0.2)'}`,
        color: ok ? '#10b981' : '#00d4ff',
      }}
    >
      {ok ? <Check size={9} /> : <Copy size={9} />}
      {label ?? (ok ? 'Copiado!' : 'Copiar')}
    </button>
  )
}

// ── Abre URL no browser padrão ────────────────────────────────────────────────
// Ordem de tentativa:
// 1. electronAPI.shell.openExternal (IPC — requer electron-compile rodado)
// 2. window.open interceptado pelo setWindowOpenHandler em main.ts → shell.openExternal
// 3. Fallback: âncora HTML com click programático
function openInBrowser(url: string) {
  const api = (window as any).electronAPI
  if (api?.shell?.openExternal) {
    api.shell.openExternal(url)
    return
  }
  // window.open é interceptado pelo setWindowOpenHandler em main.ts
  // que chama shell.openExternal — funciona mesmo sem electron-compile
  const w = window.open(url, '_blank')
  if (!w) {
    // Último recurso: âncora temporária
    const a = document.createElement('a')
    a.href = url
    a.target = '_blank'
    a.rel = 'noopener noreferrer'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }
}

// ── Obtém userId via Electron safeStorage (IPC) ───────────────────────────
// Persiste entre reinstalações (salvo com criptografia do SO).
// Fallback para localStorage se fora do contexto Electron.
async function resolveUserId(): Promise<string> {
  try {
    const api = (window as any).electronAPI
    if (api?.getUserId) {
      const uid = await api.getUserId()
      if (uid && uid.startsWith('user_')) {
        // Mantém localStorage sincronizado (usado como cache entre renders)
        localStorage.setItem('luna_user_id', uid)
        return uid
      }
    }
  } catch { /* fora do Electron — usa fallback */ }
  // Fallback: localStorage (web/dev mode)
  const saved = localStorage.getItem('luna_user_id')
  if (saved && saved !== 'default_user') return saved
  const generated = `user_${crypto.randomUUID().replace(/-/g, '').slice(0, 16)}`
  localStorage.setItem('luna_user_id', generated)
  return generated
}

// ═══════════════════════════════════════════════════════════════════════════════
export default function Credits() {
  const { backendUrl, lunaApiToken } = useStore()
  // userId assíncrono — vem do Electron safeStorage (IPC)
  const [userId, setUserId]     = useState<string>('')
  const [balance, setBalance]   = useState<number | null>(null)
  const [history, setHistory]   = useState<HistoryEntry[]>([])
  const [loading]               = useState(false)
  const [error, setError]       = useState<string | null>(null)
  const [ngrokUrl, setNgrokUrl] = useState<string>('')
  const [pendingPlan, setPendingPlan] = useState<typeof PLANS[0] | null>(null)
  const [copied, setCopied]     = useState(false)
  // Grains customizável
  const [customUsd, setCustomUsd]   = useState<string>('')
  const CUSTOM_RATE = 1000  // Grains por dólar — matches backend GRAINS_PER_USDC=1000

  const hdr = {
    'Content-Type': 'application/json',
    ...(lunaApiToken ? { 'X-Luna-Token': lunaApiToken } : {}),
  }

  // ── Carregar saldo e histórico ────────────────────────────────────────────
  const fetchBalance = useCallback(async (uid: string) => {
    if (!uid) return
    try {
      const r = await fetch(`${backendUrl}/payment/balance/${uid}`, { headers: hdr })
      const d = await r.json()
      if (d.success) setBalance(d.response.balance_grains)
    } catch { /* silencia */ }
  }, [backendUrl])

  const fetchHistory = useCallback(async (uid: string) => {
    if (!uid) return
    try {
      const r = await fetch(`${backendUrl}/payment/history/${uid}?limit=10`, { headers: hdr })
      const d = await r.json()
      if (d.success) setHistory(d.response.history)
    } catch { /* silencia */ }
  }, [backendUrl])

  // ── Inicialização: resolve userId via safeStorage e carrega dados ─────────
  useEffect(() => {
    resolveUserId().then(uid => {
      setUserId(uid)
      // Garante que o usuário existe no Supabase antes de qualquer pagamento
      fetch(`${backendUrl}/payment/init`, {
        method: 'POST',
        headers: hdr,
        body: JSON.stringify({ user_id: uid }),
      }).catch(() => {}) // silencia — não bloqueia UI
      fetchBalance(uid)
      fetchHistory(uid)
    })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Refresh único quando a janela volta ao foco (usuário voltou do browser) ──
  useEffect(() => {
    if (!userId) return
    let lastFocus = 0
    const onFocus = () => {
      // Debounce: ignora se foco disparou nos últimos 10s (evita flood)
      const now = Date.now()
      if (now - lastFocus < 10_000) return
      lastFocus = now
      fetchBalance(userId)
      fetchHistory(userId)
    }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [userId, fetchBalance, fetchHistory])

  // ── URL de pagamento: usa ngrok se preenchido, senão backend local ─────────
  const payUrl = (usdcAmount?: number) => {
    const base = ngrokUrl.trim() || backendUrl
    const url  = new URL('/pay', base)
    url.searchParams.set('user', userId)
    if (usdcAmount) url.searchParams.set('usdc', String(usdcAmount))
    return url.toString()
  }

  // ── Abrir página de cobrança no browser ───────────────────────────────────
  const openPayPage = (plan: typeof PLANS[0]) => {
    setError(null)
    setCopied(false)
    setPendingPlan(plan)
    openInBrowser(payUrl(plan.usdc))
  }

  const copyPayUrl = () => {
    if (!pendingPlan) return
    navigator.clipboard.writeText(payUrl(pendingPlan.usdc))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6" style={{ background: '#080b14' }}>

      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-cyber-cyan flex items-center gap-2">
            <Coins size={20} /> Créditos Luna
          </h1>
          <p className="text-[11px] text-cyber-muted mt-0.5 font-mono">
            Recarregue via USDC na rede Solana. 1 USDC = 1.000 Grains.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setPendingPlan(null); openInBrowser(payUrl()) }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-mono font-semibold transition-all hover:opacity-90"
            style={{ background: 'linear-gradient(135deg,rgba(0,212,255,0.15),rgba(124,58,237,0.15))', border: '1px solid rgba(0,212,255,0.3)', color: '#00d4ff' }}
            title="Abrir página de pagamento no browser"
          >
            <Link2 size={12} /> Página de Pagamento
          </button>
          <button
            onClick={() => { fetchBalance(userId); fetchHistory(userId) }}
            className="p-2 rounded-lg text-cyber-dim hover:text-cyber-cyan transition-colors"
            style={{ border: '1px solid rgba(0,212,255,0.1)' }}
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* ── Saldo ── */}
      <div className="rounded-xl p-5 flex items-center gap-5" style={{ background: 'linear-gradient(135deg,rgba(0,212,255,0.06),rgba(124,58,237,0.06))', border: '1px solid rgba(0,212,255,0.15)' }}>
        <div className="w-14 h-14 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)' }}>
          <Zap size={24} className="text-cyber-cyan" />
        </div>
        <div className="flex-1">
          <p className="text-[11px] font-mono text-cyber-muted uppercase tracking-widest">Saldo disponível</p>
          <p className="text-3xl font-bold text-cyber-cyan mt-0.5">
            {balance === null ? '—' : balance.toLocaleString()}
            <span className="text-base font-mono text-cyber-muted ml-2">Grains</span>
          </p>
          <p className="text-[10px] font-mono text-cyber-dim mt-1">
            ≈ ${balance !== null ? (balance / 1000).toFixed(3) : '0.000'} USDC
          </p>
        </div>
        <div className="text-right space-y-1">
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-cyber-muted">
            <Shield size={10} className="text-green-400" />Seguro on-chain
          </div>
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-cyber-muted">
            <TrendingUp size={10} className="text-purple-400" />Débito automático
          </div>
        </div>
      </div>

      {/* ── URL ngrok (opcional) ── */}
      <div className="rounded-xl p-4 space-y-2" style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(0,212,255,0.08)' }}>
        <p className="text-[10px] font-mono text-cyber-muted uppercase tracking-widest">
          URL pública (ngrok) — opcional
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            value={ngrokUrl}
            onChange={e => setNgrokUrl(e.target.value)}
            placeholder="https://xxxx.ngrok-free.app  (deixe vazio para usar localhost)"
            className="flex-1 bg-transparent text-[11px] font-mono text-cyber-text outline-none px-3 py-2 rounded-lg"
            style={{ border: '1px solid rgba(0,212,255,0.15)', background: 'rgba(0,0,0,0.4)' }}
          />
          {ngrokUrl.trim() && (
            <CopyBtn text={payUrl()} label="Copiar link" />
          )}
        </div>
        {ngrokUrl.trim() && (
          <p className="text-[9px] font-mono text-cyber-dim">
            Link compartilhável: <span className="text-cyber-cyan">{payUrl()}</span>
          </p>
        )}
      </div>

      {/* ── Planos ── */}
      <div>
        <p className="text-[11px] font-mono text-cyber-muted uppercase tracking-widest mb-3">
          Escolha um plano — abre no browser para pagar
        </p>
        <div className="grid grid-cols-2 gap-3">
          {PLANS.map((plan) => {
            const rgb = plan.color === '#00d4ff' ? '0,212,255'
                      : plan.color === '#7c3aed' ? '124,58,237'
                      : plan.color === '#10b981' ? '16,185,129'
                      : '245,158,11'
            return (
              <button
                key={plan.usdc}
                onClick={() => openPayPage(plan)}
                disabled={loading}
                className="relative rounded-xl p-4 text-left transition-all hover:scale-[1.02] group disabled:opacity-50 disabled:cursor-not-allowed"
                style={{
                  background: `rgba(${rgb},0.05)`,
                  border: `1px solid ${plan.color}33`,
                  boxShadow: plan.popular ? `0 0 20px ${plan.color}22` : 'none',
                }}
              >
                {plan.popular && (
                  <span className="absolute -top-2 right-3 text-[9px] font-bold font-mono px-2 py-0.5 rounded-full" style={{ background: plan.color, color: '#080b14' }}>
                    POPULAR
                  </span>
                )}
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono uppercase tracking-widest" style={{ color: plan.color }}>
                    {plan.label}
                  </span>
                  <span className="text-lg font-bold" style={{ color: plan.color }}>${plan.usdc}</span>
                </div>
                <p className="text-xl font-bold text-cyber-text">
                  {plan.grains.toLocaleString()}
                  <span className="text-[11px] font-mono text-cyber-muted ml-1">Grains</span>
                </p>
                <p className="text-[10px] font-mono text-cyber-dim mt-1">{plan.desc}</p>

                {/* Indicador hover */}
                <div className="mt-3 flex items-center gap-1.5 text-[9px] font-mono opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: plan.color }}>
                  <ExternalLink size={8} /> Abrir página de pagamento
                </div>
              </button>
            )
          })}
        </div>
        <p className="text-[9px] font-mono text-cyber-dim mt-2 text-center">
          ⚡ Pagamento via QR Code Solana Pay · Confirma automaticamente via Helius
        </p>

        {/* ── Checkout box: aparece ao selecionar um plano ── */}
        {pendingPlan && (
          <div className="mt-3 rounded-xl overflow-hidden" style={{ border: '1px solid rgba(0,212,255,0.3)', background: 'rgba(0,212,255,0.04)' }}>
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2.5" style={{ background: 'rgba(0,212,255,0.08)', borderBottom: '1px solid rgba(0,212,255,0.15)' }}>
              <span className="text-[11px] font-mono font-semibold text-cyber-cyan">
                ⚡ {pendingPlan.label} — ${pendingPlan.usdc} USDC → {pendingPlan.grains.toLocaleString()} Grains
              </span>
              <button onClick={() => setPendingPlan(null)} className="text-[10px] font-mono text-cyber-dim hover:text-red-400 transition-colors">✕</button>
            </div>
            {/* Corpo */}
            <div className="p-4 space-y-3">
              <p className="text-[11px] font-mono text-cyber-muted">
                Cole a URL abaixo no seu browser para abrir a página de pagamento:
              </p>
              {/* URL + botão copiar */}
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: 'rgba(0,0,0,0.5)', border: '1px solid rgba(0,212,255,0.2)' }}>
                <code className="text-[10px] font-mono text-cyber-cyan flex-1 truncate select-all">
                  {payUrl(pendingPlan.usdc)}
                </code>
                <button
                  onClick={copyPayUrl}
                  className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-mono font-bold transition-all"
                  style={{
                    background: copied ? 'rgba(16,185,129,0.2)' : 'rgba(0,212,255,0.15)',
                    border: `1px solid ${copied ? 'rgba(16,185,129,0.4)' : 'rgba(0,212,255,0.4)'}`,
                    color: copied ? '#10b981' : '#00d4ff',
                  }}
                >
                  {copied ? <><Check size={10} /> Copiado!</> : <><Copy size={10} /> Copiar URL</>}
                </button>
              </div>
              {/* Botão tentar abrir de novo */}
              <button
                onClick={() => openInBrowser(payUrl(pendingPlan.usdc))}
                className="w-full py-2.5 rounded-lg text-[11px] font-mono font-semibold transition-all hover:opacity-90"
                style={{ background: 'linear-gradient(135deg,rgba(0,212,255,0.2),rgba(124,58,237,0.2))', border: '1px solid rgba(0,212,255,0.3)', color: '#00d4ff' }}
              >
                🌐 Tentar abrir no browser novamente
              </button>
              <p className="text-[9px] font-mono text-cyber-dim text-center">
                Abra o Chrome/Edge, cole a URL e escaneie o QR Code com Phantom no celular
              </p>
            </div>
          </div>
        )}
      </div>

      {/* ── Erro ── */}
      {error && (
        <div className="rounded-lg p-3 flex items-start gap-2" style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)' }}>
          <AlertCircle size={14} className="text-red-400 flex-shrink-0 mt-0.5" />
          <p className="text-[11px] font-mono text-red-400">{error}</p>
        </div>
      )}

      {/* ── Recarga personalizada ── */}
      <div className="rounded-xl p-5 space-y-4" style={{ background: 'rgba(0,212,255,0.03)', border: '1px solid rgba(0,212,255,0.12)' }}>
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-mono text-cyber-muted uppercase tracking-widest">Recarga personalizada</p>
          <span className="text-[9px] font-mono px-2 py-0.5 rounded-full" style={{ background: 'rgba(0,212,255,0.08)', border: '1px solid rgba(0,212,255,0.2)', color: '#00d4ff' }}>
            {CUSTOM_RATE} Grains / $1
          </span>
        </div>

        {/* Quick select */}
        <div className="flex gap-2">
          {[5, 10, 25, 50].map(v => (
            <button
              key={v}
              onClick={() => setCustomUsd(String(v))}
              className="flex-1 py-1.5 rounded-lg text-[10px] font-mono font-semibold transition-all hover:scale-105"
              style={{
                background: customUsd === String(v) ? 'rgba(0,212,255,0.15)' : 'rgba(0,0,0,0.4)',
                border: `1px solid ${customUsd === String(v) ? 'rgba(0,212,255,0.5)' : 'rgba(0,212,255,0.1)'}`,
                color: customUsd === String(v) ? '#00d4ff' : '#64748b',
              }}
            >
              ${v}
            </button>
          ))}
        </div>

        {/* Input livre */}
        <div className="flex gap-3 items-center">
          <div className="relative flex-1">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[13px] font-bold text-cyber-cyan">$</span>
            <input
              type="number"
              min={1} max={1000} step={1}
              value={customUsd}
              onChange={e => {
                const v = e.target.value
                if (v === '' || (Number(v) >= 1 && Number(v) <= 1000)) setCustomUsd(v)
              }}
              placeholder="Ex: 15"
              className="w-full pl-7 pr-3 py-2.5 rounded-lg text-[13px] font-mono text-cyber-text outline-none"
              style={{ background: 'rgba(0,0,0,0.5)', border: '1px solid rgba(0,212,255,0.2)' }}
            />
          </div>
          <div className="text-center">
            <p className="text-[10px] font-mono text-cyber-dim">→</p>
          </div>
          <div className="px-4 py-2.5 rounded-lg min-w-[120px] text-center" style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(0,212,255,0.12)' }}>
            <p className="text-[16px] font-bold text-cyber-cyan">
              {customUsd && Number(customUsd) >= 1 ? (Number(customUsd) * CUSTOM_RATE).toLocaleString() : '—'}
            </p>
            <p className="text-[9px] font-mono text-cyber-dim">Grains</p>
          </div>
        </div>

        {/* Comparativo com planos */}
        {customUsd && Number(customUsd) >= 1 && (
          <p className="text-[10px] font-mono text-cyber-dim text-center">
            💡 Os planos acima têm até +50% de bônus — ideal para recargas maiores
          </p>
        )}

        {/* Botão pagar */}
        <button
          disabled={!customUsd || Number(customUsd) < 1 || !userId}
          onClick={() => {
            const usd = Math.round(Number(customUsd))
            if (usd < 1) return
            const url = payUrl(usd)
            setPendingPlan(null)
            openInBrowser(url)
          }}
          className="w-full py-2.5 rounded-xl text-[12px] font-mono font-bold transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
          style={{ background: 'linear-gradient(135deg,rgba(0,212,255,0.2),rgba(124,58,237,0.2))', border: '1px solid rgba(0,212,255,0.35)', color: '#00d4ff' }}
        >
          💳 Pagar ${customUsd || '—'} USDC →{' '}
          {customUsd && Number(customUsd) >= 1 ? (Number(customUsd) * CUSTOM_RATE).toLocaleString() : '—'} Grains
        </button>
      </div>

      {/* ── Tabela de custos ── */}
      <div className="rounded-xl overflow-hidden" style={{ border: '1px solid rgba(0,212,255,0.08)' }}>
        <div className="px-4 py-2.5 border-b" style={{ background: 'rgba(0,212,255,0.03)', borderColor: 'rgba(0,212,255,0.08)' }}>
          <span className="text-[10px] font-mono text-cyber-muted uppercase tracking-widest">Tabela de custos</span>
        </div>
        {[
          { op: 'Mensagem chat (gpt-4o)',     cost: '~1–3 Grains',  floor: '0.10 mín.' },
          { op: 'Security Scan (1k linhas)',  cost: '15 Grains',    floor: 'fixo'       },
          { op: 'Análise de imagem',          cost: '50 Grains',    floor: 'fixo'       },
          { op: 'Groq / Llama (rápido)',      cost: '~0.1 Grains',  floor: '0.10 mín.' },
        ].map((row, i) => (
          <div key={i} className="flex items-center px-4 py-2.5 gap-4" style={{ borderBottom: i < 3 ? '1px solid rgba(0,212,255,0.05)' : 'none' }}>
            <span className="text-[11px] font-mono text-cyber-muted flex-1">{row.op}</span>
            <span className="text-[11px] font-mono text-cyber-cyan">{row.cost}</span>
            <span className="text-[10px] font-mono text-cyber-dim w-20 text-right">{row.floor}</span>
          </div>
        ))}
      </div>

      {/* ── Histórico ── */}
      <div>
        <p className="text-[11px] font-mono text-cyber-muted uppercase tracking-widest mb-3">Histórico de recargas</p>
        {history.length === 0 ? (
          <div className="rounded-xl p-6 text-center" style={{ background: 'rgba(0,212,255,0.02)', border: '1px dashed rgba(0,212,255,0.1)' }}>
            <p className="text-[11px] font-mono text-cyber-dim">Nenhuma recarga ainda.</p>
            <button
              onClick={() => { setPendingPlan(null); openInBrowser(payUrl()) }}
              className="mt-3 text-[10px] font-mono text-cyber-cyan hover:underline flex items-center gap-1 mx-auto"
            >
              <Link2 size={9} /> Abrir página de pagamento
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            {history.map((e) => (
              <div key={e.id} className="rounded-lg px-4 py-3 flex items-center gap-4" style={{ background: 'rgba(15,22,36,0.7)', border: '1px solid rgba(0,212,255,0.06)' }}>
                <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: statusColor(e.status), boxShadow: `0 0 4px ${statusColor(e.status)}` }} />
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] font-mono text-cyber-text">
                    ${e.usdc_amount.toFixed(2)} USDC → <span className="text-cyber-cyan">{e.grains_credited.toLocaleString()} Grains</span>
                  </p>
                  {e.tx_signature && (
                    <button
                      onClick={() => openInBrowser(`https://solscan.io/tx/${e.tx_signature}`)}
                      className="flex items-center gap-1 text-[9px] font-mono text-cyber-dim hover:text-cyber-cyan transition-colors mt-0.5"
                    >
                      <ExternalLink size={8} />
                      {e.tx_signature.slice(0, 20)}...{e.tx_signature.slice(-8)} (Solscan)
                    </button>
                  )}
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="text-[10px] font-mono" style={{ color: statusColor(e.status) }}>{statusLabel(e.status)}</p>
                  <p className="text-[9px] font-mono text-cyber-dim mt-0.5">{timeSince(e.created_at)}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

    </div>
  )
}
