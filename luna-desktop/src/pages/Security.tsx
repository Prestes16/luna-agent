import React, { useState } from 'react'
import {
  Shield, Lock, AlertTriangle, CheckCircle, Key,
  Eye, Activity, Clock, ChevronRight, Zap,
} from 'lucide-react'

// ── Data ─────────────────────────────────────────────────────────────────────

interface SecurityCheck {
  id: string
  name: string
  desc: string
  defaultOn: boolean
  toggleable: boolean
  icon: React.ElementType
  level: 'critical' | 'high' | 'medium'
}

const CHECKS: SecurityCheck[] = [
  { id: 'e2e',     name: 'End-to-End Encryption',     desc: 'Mensagens criptografadas localmente',          defaultOn: true,  toggleable: false, icon: Lock,          level: 'critical' },
  { id: 'apikeys', name: 'API Key Management',         desc: 'Keys armazenadas de forma segura',            defaultOn: true,  toggleable: false, icon: Key,           level: 'critical' },
  { id: '2fa',     name: 'Two-Factor Authentication',  desc: 'Verificação em dois fatores',                 defaultOn: false, toggleable: true,  icon: Shield,        level: 'high' },
  { id: 'audit',   name: 'Audit Logging',              desc: 'Registro de todas as ações do agente',       defaultOn: true,  toggleable: true,  icon: CheckCircle,   level: 'medium' },
  { id: 'threat',  name: 'Threat Detection',           desc: 'Monitora padrões suspeitos em tempo real',   defaultOn: true,  toggleable: true,  icon: AlertTriangle, level: 'high' },
  { id: 'sandbox', name: 'Code Sandbox',               desc: 'Execução isolada de código inseguro',         defaultOn: false, toggleable: true,  icon: Eye,           level: 'medium' },
]

const EVENTS = [
  { event: 'API key carregada do .env',         time: 'Agora',       type: 'success' as const },
  { event: 'Backend conectado na porta 8000',   time: '1 min',       type: 'success' as const },
  { event: 'Verificação de criptografia OK',    time: '5 min',       type: 'success' as const },
  { event: 'Tentativa de acesso à porta 8001',  time: '12 min',      type: 'warning' as const },
  { event: 'Sessão iniciada com sucesso',       time: 'Esta sessão', type: 'success' as const },
]

const levelColor: Record<string, string> = {
  critical: '#10b981',   // green — always-on protections shown in green
  high:     '#f97316',
  medium:   '#f59e0b',
}

// ── Toggle ────────────────────────────────────────────────────────────────────
const Toggle: React.FC<{ on: boolean; onChange: () => void }> = ({ on, onChange }) => (
  <button
    onClick={onChange}
    role="switch"
    aria-checked={on}
    className="relative flex-shrink-0 w-9 h-5 rounded-full transition-colors duration-200 focus:outline-none"
    style={{ background: on ? '#10b981' : 'rgba(100,116,139,0.3)' }}
  >
    <span
      className="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all duration-200"
      style={{ left: on ? '18px' : '2px' }}
    />
  </button>
)

// ── Component ─────────────────────────────────────────────────────────────────
const Security: React.FC = () => {
  const [enabled, setEnabled] = useState<Record<string, boolean>>(
    Object.fromEntries(CHECKS.map((c) => [c.id, c.defaultOn]))
  )

  const toggle = (id: string) =>
    setEnabled((prev) => ({ ...prev, [id]: !prev[id] }))

  const enableAll = () =>
    setEnabled(Object.fromEntries(CHECKS.map((c) => [c.id, true])))

  const resetDefaults = () =>
    setEnabled(Object.fromEntries(CHECKS.map((c) => [c.id, c.defaultOn])))

  const activeCount = CHECKS.filter((c) => enabled[c.id]).length
  const threatLevel = activeCount >= 5 ? 'LOW' : activeCount >= 3 ? 'MEDIUM' : 'HIGH'
  const threatColor = threatLevel === 'LOW' ? '#10b981' : threatLevel === 'MEDIUM' ? '#f59e0b' : '#ef4444'
  const threatPct   = Math.round((activeCount / CHECKS.length) * 100)

  return (
    <div className="flex flex-col h-full overflow-y-auto p-6 gap-5 animate-fade-up">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <Shield size={14} className="text-cyber-cyan" />
            <h1 className="text-lg font-bold text-cyber-text">Security</h1>
          </div>
          <p className="text-[11px] text-cyber-muted font-mono">
            Gerenciar configurações de segurança e status de ameaças
          </p>
        </div>

        <div
          className="flex items-center gap-2 px-3 py-1.5 rounded-full flex-shrink-0"
          style={{ background: `${threatColor}12`, border: `1px solid ${threatColor}40` }}
        >
          <Shield size={11} style={{ color: threatColor }} />
          <span className="text-[10px] font-mono font-bold" style={{ color: threatColor }}>
            Ameaça: {threatLevel}
          </span>
        </div>
      </div>

      {/* ── Threat Level Card ───────────────────────────────────────────────── */}
      {/* Using padding + explicit structure instead of overflow-hidden to prevent clipping */}
      <div
        className="relative rounded-xl flex-shrink-0 p-5"
        style={{
          background: 'rgba(15,22,36,0.65)',
          border: `1px solid ${threatColor}30`,
          boxShadow: `0 0 32px ${threatColor}08`,
        }}
      >
        {/* Gradient top line */}
        <div
          style={{
            position: 'absolute', top: 0, left: 0, right: 0, height: 1,
            borderRadius: '12px 12px 0 0',
            background: `linear-gradient(90deg, transparent, ${threatColor}70, transparent)`,
          }}
        />

        <div className="flex items-center justify-between gap-4">
          {/* Left — info */}
          <div>
            <p className="text-[10px] font-mono text-cyber-muted uppercase tracking-widest mb-2">
              Nível de Ameaça Atual
            </p>
            <p
              className="font-bold font-mono leading-none"
              style={{ fontSize: 38, color: threatColor }}
            >
              {threatLevel}
            </p>
            <p className="text-[11px] text-cyber-muted mt-2 font-mono">
              {activeCount} / {CHECKS.length} proteções ativas
            </p>
          </div>

          {/* Right — shield ring */}
          <div
            className="flex items-center justify-center flex-shrink-0"
            style={{
              width: 72, height: 72,
              borderRadius: '50%',
              background: `${threatColor}10`,
              border: `2px solid ${threatColor}30`,
              boxShadow: `0 0 20px ${threatColor}20`,
            }}
          >
            <Shield size={30} style={{ color: threatColor }} />
          </div>
        </div>

        {/* Progress bar */}
        <div className="mt-5 progress-cyber">
          <div
            className="progress-cyber-fill"
            style={{
              width: `${threatPct}%`,
              background: `linear-gradient(90deg, ${threatColor}70, ${threatColor})`,
              transition: 'width 0.6s ease',
            }}
          />
        </div>

        {/* Dot indicators */}
        <div className="mt-2.5 flex items-center gap-1.5">
          {CHECKS.map((c) => (
            <div
              key={c.id}
              title={c.name}
              style={{
                width: 6, height: 6,
                borderRadius: '50%',
                background: enabled[c.id] ? '#10b981' : '#334155',
                transition: 'background 0.2s',
              }}
            />
          ))}
          <span className="ml-1 text-[9px] font-mono text-cyber-dim">
            {threatPct}% coberto
          </span>
        </div>
      </div>

      {/* ── Security Checks ─────────────────────────────────────────────────── */}
      <div className="flex-shrink-0">
        <div className="flex items-center gap-2 mb-3">
          <Activity size={11} className="text-cyber-muted" />
          <h2 className="text-[10px] font-mono text-cyber-muted uppercase tracking-[0.15em]">
            Verificações de Segurança
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {CHECKS.map((check) => {
            const Icon  = check.icon
            const isOn  = enabled[check.id]
            const color = isOn ? levelColor[check.level] : '#334155'

            return (
              <div
                key={check.id}
                className="relative rounded-xl p-4"
                style={{
                  background: 'rgba(15,22,36,0.65)',
                  border: `1px solid ${isOn ? color + '28' : 'rgba(0,212,255,0.06)'}`,
                  transition: 'border-color 0.2s',
                }}
              >
                {/* Accent line */}
                {isOn && (
                  <div style={{
                    position: 'absolute', top: 0, left: 0, right: 0, height: 1,
                    borderRadius: '12px 12px 0 0',
                    background: `linear-gradient(90deg, transparent, ${color}50, transparent)`,
                  }} />
                )}

                <div className="flex items-start gap-3">
                  {/* Icon */}
                  <div
                    className="flex items-center justify-center flex-shrink-0 mt-0.5"
                    style={{
                      width: 32, height: 32,
                      borderRadius: 8,
                      background: `${color}12`,
                      border: `1px solid ${color}28`,
                    }}
                  >
                    <Icon size={14} style={{ color }} />
                  </div>

                  {/* Text */}
                  <div className="flex-1 min-w-0">
                    <p className="text-[12px] font-semibold text-cyber-text">{check.name}</p>
                    <p className="text-[10px] text-cyber-muted mt-0.5 leading-relaxed">{check.desc}</p>
                    <span
                      className="inline-block mt-1.5 text-[9px] font-mono px-1.5 py-0.5 rounded"
                      style={{ background: `${color}12`, color, border: `1px solid ${color}28` }}
                    >
                      {isOn
                        ? (!check.toggleable ? 'Permanente' : 'Ativo')
                        : 'Inativo'}
                    </span>
                  </div>

                  {/* Toggle or lock */}
                  {check.toggleable
                    ? <Toggle on={isOn} onChange={() => toggle(check.id)} />
                    : (
                      <div
                        className="flex items-center justify-center flex-shrink-0"
                        title="Sempre ativo"
                        style={{
                          width: 36, height: 20,
                          borderRadius: 10,
                          background: 'rgba(16,185,129,0.12)',
                          border: '1px solid rgba(16,185,129,0.25)',
                        }}
                      >
                        <Lock size={9} className="text-cyber-green" />
                      </div>
                    )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Recent Events ───────────────────────────────────────────────────── */}
      <div className="flex-shrink-0">
        <div className="flex items-center gap-2 mb-3">
          <Clock size={11} className="text-cyber-muted" />
          <h2 className="text-[10px] font-mono text-cyber-muted uppercase tracking-[0.15em]">
            Eventos Recentes
          </h2>
        </div>

        <div
          className="rounded-xl"
          style={{ background: 'rgba(15,22,36,0.6)', border: '1px solid rgba(0,212,255,0.08)', overflow: 'hidden' }}
        >
          {EVENTS.map((item, i) => (
            <div
              key={i}
              className="flex items-center justify-between px-4 py-3 transition-colors hover:bg-white/[0.02]"
              style={{ borderBottom: i < EVENTS.length - 1 ? '1px solid rgba(0,212,255,0.05)' : 'none' }}
            >
              <div className="flex items-center gap-3">
                <div
                  style={{
                    width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                    background: item.type === 'success' ? '#10b981' : '#f59e0b',
                  }}
                />
                <span className="text-[12px] text-cyber-text">{item.event}</span>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <span className="text-[10px] font-mono text-cyber-muted">{item.time}</span>
                <ChevronRight size={11} className="text-cyber-dim" />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Quick Actions ────────────────────────────────────────────────────── */}
      <div className="flex gap-3 flex-shrink-0">
        <button
          onClick={enableAll}
          className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-[11px] font-mono transition-all"
          style={{ background: 'rgba(16,185,129,0.07)', border: '1px solid rgba(16,185,129,0.22)', color: '#10b981' }}
        >
          <Zap size={12} /> Ativar todas
        </button>
        <button
          onClick={resetDefaults}
          className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-[11px] font-mono transition-all"
          style={{ background: 'rgba(0,212,255,0.06)', border: '1px solid rgba(0,212,255,0.15)', color: '#00d4ff' }}
        >
          Restaurar padrões
        </button>
      </div>

      <div className="h-4" />
    </div>
  )
}

export default Security
