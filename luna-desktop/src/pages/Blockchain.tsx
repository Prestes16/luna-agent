import React, { useState, useEffect, useCallback } from 'react'
import { useStore } from '@store/appStore'
import {
  Wallet, RefreshCw, ExternalLink, Copy, CheckCircle,
  AlertCircle, TrendingUp, Globe, Zap, Loader2,
} from 'lucide-react'

// ── RPC endpoint — uses Helius if VITE_HELIUS_API_KEY is set in .env ─────────
const getEndpoint = (network: 'mainnet' | 'devnet') => {
  const key = (import.meta as any).env?.VITE_HELIUS_API_KEY as string | undefined
  if (network === 'devnet') {
    return key
      ? `https://devnet.helius-rpc.com/?api-key=${key}`
      : 'https://api.devnet.solana.com'
  }
  return key
    ? `https://mainnet.helius-rpc.com/?api-key=${key}`
    : 'https://api.mainnet-beta.solana.com'
}

const LAMPORTS_PER_SOL = 1_000_000_000

interface TxSignature {
  signature: string
  slot: number
  blockTime: number | null
  err: any | null
  memo: string | null
}

const shortenSig = (sig: string) =>
  sig.length > 20 ? `${sig.slice(0, 16)}…${sig.slice(-6)}` : sig

const timeAgo = (ts: number): string => {
  const diff = Math.floor(Date.now() / 1000) - ts
  if (diff < 60) return `${diff}s atrás`
  if (diff < 3600) return `${Math.floor(diff / 60)}m atrás`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h atrás`
  return `${Math.floor(diff / 86400)}d atrás`
}

// ── Component ─────────────────────────────────────────────────────────────────
const Blockchain: React.FC = () => {
  const { solanaWalletAddress, setSolanaWalletAddress } = useStore()

  const [address,      setAddress]      = useState(solanaWalletAddress ?? '')
  const [inputAddr,    setInputAddr]    = useState(solanaWalletAddress ?? '')
  const [network,      setNetwork]      = useState<'mainnet' | 'devnet'>('mainnet')
  const [balance,      setBalance]      = useState<number | null>(null)
  const [solPrice,     setSolPrice]     = useState<number | null>(null)
  const [transactions, setTransactions] = useState<TxSignature[]>([])
  const [loading,      setLoading]      = useState(false)
  const [error,        setError]        = useState<string | null>(null)
  const [copied,       setCopied]       = useState(false)
  const [lastFetch,    setLastFetch]    = useState<Date | null>(null)

  // ── JSON-RPC helper ─────────────────────────────────────────────────────────
  const rpcCall = useCallback(async (method: string, params: any[]) => {
    const endpoint = getEndpoint(network)
    const res = await fetch(endpoint, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
      signal:  AbortSignal.timeout(15_000),
    })
    if (!res.ok) throw new Error(`RPC HTTP ${res.status}`)
    const data = await res.json()
    if (data.error) throw new Error(data.error.message ?? 'RPC error')
    return data.result
  }, [network])

  // ── Fetch all blockchain data ───────────────────────────────────────────────
  const fetchData = useCallback(async (addr: string) => {
    const clean = addr.trim()
    if (!clean || clean.length < 32) {
      setError('Endereço inválido — deve ter ao menos 32 caracteres (base58)')
      return
    }
    setLoading(true)
    setError(null)

    try {
      // 1. SOL balance
      const balResult = await rpcCall('getBalance', [clean])
      const sol = (balResult?.value ?? 0) / LAMPORTS_PER_SOL
      setBalance(sol)

      // 2. Recent transactions (last 15)
      const sigs: TxSignature[] = await rpcCall('getSignaturesForAddress', [
        clean, { limit: 15 },
      ])
      setTransactions(sigs ?? [])

      // 3. SOL/USD price — CoinGecko free tier (no key required)
      try {
        const pr  = await fetch(
          'https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd',
          { signal: AbortSignal.timeout(6_000) }
        )
        const pd  = await pr.json()
        setSolPrice(pd?.solana?.usd ?? null)
      } catch {
        /* price fetch is non-critical — skip silently */
      }

      setAddress(clean)
      setSolanaWalletAddress(clean)
      setLastFetch(new Date())
    } catch (e: any) {
      setError(e?.message ?? 'Erro ao consultar a blockchain')
    } finally {
      setLoading(false)
    }
  }, [rpcCall, setSolanaWalletAddress])

  // ── Auto-load saved address ─────────────────────────────────────────────────
  useEffect(() => {
    if (solanaWalletAddress) {
      setInputAddr(solanaWalletAddress)
      fetchData(solanaWalletAddress)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Helpers ─────────────────────────────────────────────────────────────────
  const copyAddress = () => {
    navigator.clipboard.writeText(address)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const explorerBase = network === 'devnet' ? '?cluster=devnet' : ''
  const explorerAccount = `https://solscan.io/account/${address}${explorerBase}`
  const explorerTx = (sig: string) => `https://solscan.io/tx/${sig}${explorerBase}`

  const usdValue = balance !== null && solPrice !== null
    ? (balance * solPrice).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : null

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full overflow-y-auto p-6 gap-5 animate-fade-up">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <Wallet size={14} className="text-cyber-cyan" />
            <h1 className="text-lg font-bold text-cyber-text">Blockchain</h1>
          </div>
          <p className="text-[11px] text-cyber-muted font-mono">
            Solana wallet — saldo e transações em tempo real
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Network toggle */}
          <div
            className="flex gap-0.5 p-0.5 rounded-lg"
            style={{ background: 'rgba(0,212,255,0.06)', border: '1px solid rgba(0,212,255,0.1)' }}
          >
            {(['mainnet', 'devnet'] as const).map((net) => (
              <button
                key={net}
                onClick={() => {
                  setNetwork(net)
                  if (address) setTimeout(() => fetchData(address), 0)
                }}
                className="px-2.5 py-1 rounded-md text-[10px] font-mono transition-all"
                style={network === net
                  ? { background: 'rgba(0,212,255,0.15)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.3)' }
                  : { color: '#64748b' }}
              >
                {net}
              </button>
            ))}
          </div>

          {balance !== null && (
            <button
              onClick={() => fetchData(address)}
              disabled={loading}
              className="btn-cyber flex items-center gap-1.5"
            >
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
              Atualizar
            </button>
          )}
        </div>
      </div>

      {/* ── Wallet Address Input ────────────────────────────────────────────── */}
      <div
        className="rounded-xl p-4"
        style={{ background: 'rgba(15,22,36,0.6)', border: '1px solid rgba(0,212,255,0.1)' }}
      >
        <label className="block text-[10px] font-mono text-cyber-muted uppercase tracking-[0.12em] mb-2">
          Endereço da Wallet Solana
        </label>
        <div className="flex gap-2">
          <input
            value={inputAddr}
            onChange={(e) => setInputAddr(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && fetchData(inputAddr)}
            placeholder="Ex: 9W…XyZ (base58)"
            className="input-cyber flex-1 text-[12px] font-mono"
            spellCheck={false}
          />
          <button
            onClick={() => fetchData(inputAddr)}
            disabled={loading || !inputAddr.trim()}
            className="btn-cyber flex items-center gap-1.5 disabled:opacity-40"
          >
            {loading
              ? <Loader2 size={12} className="animate-spin" />
              : <Zap size={12} />}
            Consultar
          </button>
        </div>

        {error && (
          <div className="flex items-center gap-2 mt-2.5 text-[11px] font-mono"
            style={{ color: '#ef4444' }}>
            <AlertCircle size={11} /> {error}
          </div>
        )}
      </div>

      {/* ── Balance Card ───────────────────────────────────────────────────── */}
      {balance !== null && (
        <>
          <div
            className="relative overflow-hidden rounded-xl p-5"
            style={{ background: 'rgba(15,22,36,0.7)', border: '1px solid rgba(124,58,237,0.3)' }}
          >
            {/* Top accent line */}
            <div
              className="absolute top-0 left-0 right-0 h-px"
              style={{ background: 'linear-gradient(90deg, transparent, rgba(124,58,237,0.7), transparent)' }}
            />

            <div className="flex items-start justify-between">
              <div>
                <p className="text-[10px] font-mono text-cyber-muted uppercase tracking-widest mb-2">
                  Saldo · {network}
                </p>
                <p className="text-3xl font-bold font-mono text-cyber-text">
                  {balance.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 6 })}
                  <span className="ml-2 text-[18px] text-cyber-purple">SOL</span>
                </p>
                {usdValue !== null && (
                  <p className="text-[13px] text-cyber-muted mt-1.5 font-mono">
                    ≈ <span className="text-cyber-green">${usdValue} USD</span>
                    {solPrice && (
                      <span className="ml-2 text-[10px] text-cyber-dim">
                        @ ${solPrice.toLocaleString('en-US', { minimumFractionDigits: 2 })}/SOL
                      </span>
                    )}
                  </p>
                )}
              </div>

              <div
                className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: 'rgba(124,58,237,0.12)', border: '1px solid rgba(124,58,237,0.3)' }}
              >
                <Wallet size={22} className="text-cyber-purple" />
              </div>
            </div>

            {/* Address + actions */}
            <div className="mt-4 flex items-center gap-2">
              <Globe size={11} className="text-cyber-dim flex-shrink-0" />
              <span className="text-[11px] font-mono text-cyber-muted truncate flex-1">
                {address}
              </span>
              <button
                onClick={copyAddress}
                title="Copiar endereço"
                className="flex items-center gap-1 text-[10px] font-mono px-2 py-1 rounded-lg flex-shrink-0 transition-colors"
                style={{ background: 'rgba(0,212,255,0.06)', border: '1px solid rgba(0,212,255,0.12)', color: '#00d4ff' }}
              >
                {copied ? <CheckCircle size={10} /> : <Copy size={10} />}
                {copied ? 'Copiado!' : 'Copiar'}
              </button>
              <a
                href={explorerAccount}
                target="_blank"
                rel="noreferrer"
                title="Abrir no Solscan"
                className="flex items-center gap-1 text-[10px] font-mono px-2 py-1 rounded-lg flex-shrink-0 transition-colors"
                style={{ background: 'rgba(0,212,255,0.06)', border: '1px solid rgba(0,212,255,0.12)', color: '#00d4ff' }}
              >
                <ExternalLink size={10} /> Solscan
              </a>
            </div>

            {lastFetch && (
              <p className="mt-2 text-[9px] font-mono text-cyber-dim">
                Última atualização: {lastFetch.toLocaleTimeString()}
              </p>
            )}
          </div>

          {/* ── Transactions ─────────────────────────────────────────────── */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <TrendingUp size={11} className="text-cyber-muted" />
              <h2 className="text-[10px] font-mono text-cyber-muted uppercase tracking-[0.15em]">
                Transações Recentes
                {transactions.length > 0 && (
                  <span className="ml-1.5 text-cyber-dim">({transactions.length})</span>
                )}
              </h2>
            </div>

            {loading && transactions.length === 0 ? (
              <div className="flex items-center justify-center py-10 gap-2 text-[11px] font-mono text-cyber-muted">
                <Loader2 size={14} className="animate-spin text-cyber-cyan" />
                Buscando transações…
              </div>
            ) : transactions.length === 0 ? (
              <div
                className="flex items-center justify-center py-10 rounded-xl text-[12px] text-cyber-muted font-mono"
                style={{ background: 'rgba(15,22,36,0.4)', border: '1px solid rgba(0,212,255,0.06)' }}
              >
                Nenhuma transação encontrada
              </div>
            ) : (
              <div
                className="rounded-xl overflow-hidden"
                style={{ background: 'rgba(15,22,36,0.6)', border: '1px solid rgba(0,212,255,0.08)' }}
              >
                {transactions.map((tx, i) => {
                  const success = !tx.err
                  return (
                    <div
                      key={tx.signature}
                      className="flex items-center gap-3 px-4 py-3 hover:bg-white/[0.02] transition-colors"
                      style={{
                        borderBottom: i < transactions.length - 1
                          ? '1px solid rgba(0,212,255,0.05)'
                          : 'none',
                      }}
                    >
                      {/* Status icon */}
                      <div
                        className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                        style={{
                          background: success ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                          border: `1px solid ${success ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'}`,
                        }}
                      >
                        {success
                          ? <CheckCircle size={12} className="text-cyber-green" />
                          : <AlertCircle size={12} className="text-cyber-red" />}
                      </div>

                      {/* Signature + time */}
                      <div className="flex-1 min-w-0">
                        <p className="text-[12px] font-mono text-cyber-text truncate">
                          {shortenSig(tx.signature)}
                        </p>
                        <p className="text-[10px] text-cyber-muted mt-0.5">
                          {tx.blockTime ? timeAgo(tx.blockTime) : 'Pending'}
                          {tx.memo && (
                            <span className="ml-2 text-cyber-cyan truncate">{tx.memo}</span>
                          )}
                        </p>
                      </div>

                      {/* Status badge */}
                      <span
                        className="text-[9px] font-mono px-1.5 py-0.5 rounded flex-shrink-0"
                        style={success
                          ? { background: 'rgba(16,185,129,0.1)', color: '#10b981', border: '1px solid rgba(16,185,129,0.2)' }
                          : { background: 'rgba(239,68,68,0.1)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.2)' }}
                      >
                        {success ? 'success' : 'failed'}
                      </span>

                      {/* Explorer link */}
                      <a
                        href={explorerTx(tx.signature)}
                        target="_blank"
                        rel="noreferrer"
                        title="Ver no Solscan"
                        className="flex-shrink-0 text-cyber-dim hover:text-cyber-cyan transition-colors"
                      >
                        <ExternalLink size={11} />
                      </a>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </>
      )}

      {/* ── Idle / no wallet ───────────────────────────────────────────────── */}
      {balance === null && !loading && !error && (
        <div
          className="flex flex-col items-center justify-center py-16 gap-4 rounded-xl"
          style={{ background: 'rgba(15,22,36,0.4)', border: '1px dashed rgba(0,212,255,0.1)' }}
        >
          <div
            className="w-14 h-14 rounded-xl flex items-center justify-center"
            style={{ background: 'rgba(124,58,237,0.08)', border: '1px solid rgba(124,58,237,0.2)' }}
          >
            <Wallet size={24} className="text-cyber-purple" />
          </div>
          <div className="text-center">
            <p className="text-sm font-semibold text-cyber-text">Nenhuma wallet consultada</p>
            <p className="text-[11px] text-cyber-muted mt-1 font-mono">
              Insira um endereço Solana acima e clique em Consultar
            </p>
          </div>
          <div className="flex items-center gap-2 text-[10px] font-mono text-cyber-dim">
            <Globe size={11} />
            Mainnet-beta · Helius RPC · CoinGecko price feed
          </div>
        </div>
      )}

      {/* ── Loading spinner (initial) ───────────────────────────────────────── */}
      {balance === null && loading && (
        <div className="flex flex-col items-center justify-center py-16 gap-4">
          <div
            className="w-14 h-14 rounded-full flex items-center justify-center"
            style={{ background: 'rgba(0,212,255,0.06)', border: '2px solid rgba(0,212,255,0.2)' }}
          >
            <Loader2 size={24} className="animate-spin text-cyber-cyan" />
          </div>
          <p className="text-[12px] font-mono text-cyber-muted">
            Consultando blockchain…
          </p>
        </div>
      )}

      <div className="h-4" />
    </div>
  )
}

export default Blockchain
