import React, { useState, useRef, useCallback } from 'react'
import { useStore } from '@store/appStore'
import {
  Upload, Code2, AlertTriangle, CheckCircle,
  FileCode, Cpu, Shield, Zap, ChevronDown, ChevronUp,
  Clipboard, RotateCcw,
} from 'lucide-react'

const SUPPORTED = [
  { ext: '.py',   lang: 'Python',     color: '#3b82f6' },
  { ext: '.rs',   lang: 'Rust',       color: '#f97316' },
  { ext: '.ts',   lang: 'TypeScript', color: '#00d4ff' },
  { ext: '.js',   lang: 'JavaScript', color: '#f59e0b' },
  { ext: '.sol',  lang: 'Solidity',   color: '#7c3aed' },
  { ext: '.go',   lang: 'Go',         color: '#10b981' },
  { ext: '.java', lang: 'Java',       color: '#ef4444' },
  { ext: '.cpp',  lang: 'C++',        color: '#e040fb' },
]

const CAPABILITIES = [
  { icon: Shield,   label: 'Vulnerabilidades de Segurança',  desc: 'SQL Injection, XSS, Buffer Overflow, Race Conditions' },
  { icon: Cpu,      label: 'Análise de Complexidade',        desc: 'Big-O, hotspots, funções com alto custo computacional' },
  { icon: Zap,      label: 'Otimizações de Performance',     desc: 'Loops desnecessários, alocações excessivas, N+1 queries' },
  { icon: Code2,    label: 'Qualidade e Boas Práticas',      desc: 'Clean code, nomenclatura, duplicações, dead code' },
]

type Mode = 'idle' | 'analyzing' | 'done' | 'error'

const severityColor = { critical: '#ef4444', high: '#f97316', medium: '#f59e0b', low: '#10b981', info: '#00d4ff' }

const CodeAnalyzer: React.FC = () => {
  const { backendUrl } = useStore()
  const fileRef        = useRef<HTMLInputElement>(null)
  const [mode, setMode]         = useState<Mode>('idle')
  const [file, setFile]         = useState<File | null>(null)
  const [pasteCode, setPasteCode] = useState('')
  const [usePaste, setUsePaste]   = useState(false)
  const [analysis, setAnalysis]   = useState<any>(null)
  const [drag, setDrag]           = useState(false)
  const [expandedIdx, setExpanded] = useState<number | null>(null)

  const analyze = async (content: string, filename: string) => {
    setMode('analyzing')
    setAnalysis(null)
    try {
      const form = new FormData()
      form.append('file', new Blob([content], { type: 'text/plain' }), filename)
      const res = await fetch(`${backendUrl}/api/analyze-code`, { method: 'POST', body: form })
      if (!res.ok) throw new Error(await res.text())
      setAnalysis(await res.json())
      setMode('done')
    } catch {
      // Backend offline — generate local demo analysis
      setAnalysis({
        summary: `Análise estática de ${filename}`,
        language: filename.split('.').pop()?.toUpperCase() ?? 'UNKNOWN',
        lines: content.split('\n').length,
        issues: [
          { title: 'Backend offline', severity: 'info',
            description: 'Inicie o backend (python main.py) para análise completa com IA.',
            line: null, suggestion: 'pip install -r requirements.txt && python backend/main.py' },
        ],
        recommendations: ['Conecte o backend para análise completa', 'Verifique as API keys em Settings'],
        score: 100,
      })
      setMode('done')
    }
  }

  const handleFile = (f: File) => {
    setFile(f)
    const reader = new FileReader()
    reader.onload = (e) => analyze(e.target?.result as string, f.name)
    reader.readAsText(f)
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDrag(false)
    const f = e.dataTransfer.files?.[0]
    if (f) handleFile(f)
  }, [])

  const handlePasteAnalyze = () => {
    if (!pasteCode.trim()) return
    analyze(pasteCode, 'code.txt')
  }

  const reset = () => { setMode('idle'); setFile(null); setAnalysis(null); setPasteCode('') }

  // ── Severity counts
  const severityCounts = analysis?.issues?.reduce((acc: Record<string, number>, i: any) => {
    acc[i.severity] = (acc[i.severity] ?? 0) + 1; return acc
  }, {}) ?? {}

  return (
    <div className="flex flex-col h-full overflow-y-auto p-6 gap-5 animate-fade-up">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <Code2 size={14} className="text-cyber-cyan" />
            <h1 className="text-lg font-bold text-cyber-text">Code Analyzer</h1>
          </div>
          <p className="text-[11px] text-cyber-muted font-mono">
            Análise estática de código com IA — segurança, performance, qualidade
          </p>
        </div>
        {mode !== 'idle' && (
          <button onClick={reset} className="btn-cyber flex items-center gap-1.5">
            <RotateCcw size={12} /> Nova análise
          </button>
        )}
      </div>

      {/* ── IDLE: upload area ─────────────────────────────────────────────── */}
      {mode === 'idle' && (
        <>
          {/* Toggle upload / paste */}
          <div className="flex gap-1 p-0.5 rounded-lg w-fit" style={{ background: 'rgba(0,212,255,0.06)', border: '1px solid rgba(0,212,255,0.1)' }}>
            {[{ v: false, label: 'Upload de arquivo' }, { v: true, label: 'Colar código' }].map(({ v, label }) => (
              <button
                key={String(v)}
                onClick={() => setUsePaste(v)}
                className="px-3 py-1.5 rounded-md text-[11px] font-mono transition-all"
                style={usePaste === v
                  ? { background: 'rgba(0,212,255,0.15)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.3)' }
                  : { color: '#64748b' }
                }
              >
                {label}
              </button>
            ))}
          </div>

          {!usePaste ? (
            /* Drop zone */
            <div
              className="relative rounded-xl overflow-hidden transition-all duration-200 cursor-pointer"
              style={{
                border: `2px dashed ${drag ? 'rgba(0,212,255,0.6)' : 'rgba(0,212,255,0.15)'}`,
                background: drag ? 'rgba(0,212,255,0.04)' : 'rgba(15,22,36,0.4)',
                minHeight: 180,
              }}
              onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
              onDragLeave={() => setDrag(false)}
              onDrop={handleDrop}
              onClick={() => fileRef.current?.click()}
            >
              <input ref={fileRef} type="file" className="hidden"
                accept={SUPPORTED.map((s) => s.ext).join(',')}
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f) }}
              />
              <div className="flex flex-col items-center justify-center h-full py-12 gap-3">
                <div
                  className="w-14 h-14 rounded-xl flex items-center justify-center"
                  style={{ background: 'rgba(0,212,255,0.08)', border: '1px solid rgba(0,212,255,0.2)' }}
                >
                  <Upload size={24} className="text-cyber-cyan" />
                </div>
                <div className="text-center">
                  <p className="text-sm font-semibold text-cyber-text">
                    Arraste um arquivo ou clique para selecionar
                  </p>
                  <p className="text-[11px] text-cyber-muted mt-1">
                    Suporte para {SUPPORTED.length} linguagens — análise com IA
                  </p>
                </div>
                <div className="flex flex-wrap gap-1.5 justify-center mt-1">
                  {SUPPORTED.map(({ ext, lang, color }) => (
                    <span
                      key={ext}
                      className="text-[9px] font-mono px-2 py-0.5 rounded"
                      style={{ background: `${color}12`, color, border: `1px solid ${color}25` }}
                    >
                      {lang}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            /* Paste area */
            <div className="space-y-2">
              <textarea
                value={pasteCode}
                onChange={(e) => setPasteCode(e.target.value)}
                placeholder={`// Cole seu código aqui...\n\nfn main() {\n    let x: u32 = 0;\n    // ...\n}`}
                className="w-full font-mono text-[12px] text-cyber-text rounded-xl p-4 resize-none outline-none"
                style={{
                  background: 'rgba(0,0,0,0.4)',
                  border: '1px solid rgba(0,212,255,0.15)',
                  minHeight: 200,
                  lineHeight: 1.6,
                }}
                spellCheck={false}
              />
              <button
                onClick={handlePasteAnalyze}
                disabled={!pasteCode.trim()}
                className="btn-cyber flex items-center gap-2 disabled:opacity-40"
              >
                <Clipboard size={13} /> Analisar código
              </button>
            </div>
          )}

          {/* What the analyzer does */}
          <div>
            <h2 className="text-[10px] font-mono text-cyber-muted uppercase tracking-[0.15em] mb-3">
              O que é analisado
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {CAPABILITIES.map(({ icon: Icon, label, desc }) => (
                <div
                  key={label}
                  className="flex gap-3 p-3.5 rounded-xl"
                  style={{ background: 'rgba(15,22,36,0.5)', border: '1px solid rgba(0,212,255,0.07)' }}
                >
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: 'rgba(0,212,255,0.08)', border: '1px solid rgba(0,212,255,0.15)' }}
                  >
                    <Icon size={14} className="text-cyber-cyan" />
                  </div>
                  <div>
                    <p className="text-[12px] font-semibold text-cyber-text">{label}</p>
                    <p className="text-[10px] text-cyber-muted mt-0.5 leading-relaxed">{desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* ── ANALYZING ─────────────────────────────────────────────────────── */}
      {mode === 'analyzing' && (
        <div className="flex flex-col items-center justify-center py-16 gap-4">
          <div
            className="w-16 h-16 rounded-full flex items-center justify-center"
            style={{ background: 'rgba(0,212,255,0.08)', border: '2px solid rgba(0,212,255,0.3)' }}
          >
            <div className="spinner-cyber" style={{ width: 28, height: 28 }} />
          </div>
          <div className="text-center">
            <p className="text-sm font-semibold text-cyber-text">Analisando {file?.name ?? 'código'}…</p>
            <p className="text-[11px] text-cyber-muted mt-1 font-mono">
              IA escaneando padrões de segurança e qualidade
            </p>
          </div>
        </div>
      )}

      {/* ── RESULTS ──────────────────────────────────────────────────────── */}
      {mode === 'done' && analysis && (
        <>
          {/* Summary bar */}
          <div
            className="rounded-xl p-4 flex items-center justify-between"
            style={{ background: 'rgba(15,22,36,0.7)', border: '1px solid rgba(0,212,255,0.15)' }}
          >
            <div className="flex items-center gap-3">
              <FileCode size={18} className="text-cyber-cyan" />
              <div>
                <p className="text-[13px] font-semibold text-cyber-text">{file?.name ?? 'Código colado'}</p>
                <p className="text-[10px] text-cyber-muted font-mono">
                  {analysis.language} · {analysis.lines} linhas · Score: {analysis.score ?? '—'}/100
                </p>
              </div>
            </div>
            <div className="flex gap-2">
              {Object.entries(severityCounts).map(([sev, count]) => (
                <span
                  key={sev}
                  className="text-[10px] font-mono px-2 py-0.5 rounded"
                  style={{
                    background: `${(severityColor as any)[sev] ?? '#64748b'}15`,
                    color: (severityColor as any)[sev] ?? '#64748b',
                    border: `1px solid ${(severityColor as any)[sev] ?? '#64748b'}30`,
                  }}
                >
                  {String(count)} {sev}
                </span>
              ))}
            </div>
          </div>

          {/* Issues */}
          {analysis.issues?.length > 0 && (
            <div>
              <h2 className="text-[10px] font-mono text-cyber-muted uppercase tracking-[0.15em] mb-3">
                Problemas encontrados ({analysis.issues.length})
              </h2>
              <div className="space-y-2">
                {analysis.issues.map((issue: any, i: number) => {
                  const color = (severityColor as any)[issue.severity] ?? '#64748b'
                  const open  = expandedIdx === i
                  return (
                    <div
                      key={i}
                      className="rounded-xl overflow-hidden transition-all"
                      style={{ background: `${color}06`, border: `1px solid ${color}25` }}
                    >
                      <button
                        className="w-full flex items-center gap-3 px-4 py-3 text-left"
                        onClick={() => setExpanded(open ? null : i)}
                      >
                        <AlertTriangle size={13} style={{ color }} className="flex-shrink-0" />
                        <span className="flex-1 text-[12px] font-semibold text-cyber-text">{issue.title}</span>
                        {issue.line && (
                          <span className="text-[10px] font-mono text-cyber-muted">L{issue.line}</span>
                        )}
                        <span
                          className="text-[9px] font-mono px-1.5 py-0.5 rounded"
                          style={{ background: `${color}15`, color, border: `1px solid ${color}25` }}
                        >
                          {issue.severity}
                        </span>
                        {open ? <ChevronUp size={12} className="text-cyber-muted" /> : <ChevronDown size={12} className="text-cyber-muted" />}
                      </button>
                      {open && (
                        <div className="px-4 pb-3 space-y-2">
                          <p className="text-[11px] text-cyber-muted leading-relaxed">{issue.description}</p>
                          {issue.suggestion && (
                            <div
                              className="rounded-lg px-3 py-2"
                              style={{ background: 'rgba(0,212,255,0.05)', border: '1px solid rgba(0,212,255,0.1)' }}
                            >
                              <p className="text-[10px] font-mono text-cyber-cyan">💡 {issue.suggestion}</p>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Recommendations */}
          {analysis.recommendations?.length > 0 && (
            <div>
              <h2 className="text-[10px] font-mono text-cyber-muted uppercase tracking-[0.15em] mb-3">
                Recomendações
              </h2>
              <div className="space-y-2">
                {analysis.recommendations.map((rec: string, i: number) => (
                  <div
                    key={i}
                    className="flex items-start gap-3 p-3 rounded-xl"
                    style={{ background: 'rgba(16,185,129,0.05)', border: '1px solid rgba(16,185,129,0.15)' }}
                  >
                    <CheckCircle size={13} className="text-cyber-green mt-0.5 flex-shrink-0" />
                    <p className="text-[12px] text-cyber-text">{rec}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <div className="h-4" />
    </div>
  )
}

export default CodeAnalyzer
