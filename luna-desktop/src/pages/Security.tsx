import React, { useEffect } from 'react'
import {
  AlertCircle, CheckCircle2, FolderLock, KeyRound, LockKeyhole,
  RefreshCw, Server, Shield, Terminal, Wifi,
} from 'lucide-react'
import { useStore } from '@store/appStore'

function ProtectionRow({ icon: Icon, label, detail, active }: {
  icon: React.ElementType
  label: string
  detail: string
  active: boolean
}) {
  return (
    <div className="flex min-h-14 items-center gap-3 border-b border-white/[0.04] py-3 last:border-b-0">
      <span className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md ${active ? 'bg-cyber-green/10 text-cyber-green' : 'bg-red-400/10 text-red-300'}`}>
        <Icon size={15} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[12px] font-semibold text-cyber-text">{label}</p>
        <p className="mt-0.5 text-[10px] leading-relaxed text-cyber-muted">{detail}</p>
      </div>
      <span className={`rounded-full border px-2 py-0.5 font-mono text-[8px] ${active ? 'border-cyber-green/20 bg-cyber-green/5 text-cyber-green' : 'border-red-400/20 bg-red-400/5 text-red-300'}`}>
        {active ? 'ATIVO' : 'ATENÇÃO'}
      </span>
    </div>
  )
}

const Security: React.FC = () => {
  const {
    backendUrl, backendStatus, healthLoading, refreshBackendHealth,
    workspacePath,
  } = useStore()

  useEffect(() => { void refreshBackendHealth() }, [refreshBackendHealth])

  const electronBridge = Boolean(window.electronAPI)
  const loopback = backendUrl.includes('localhost') || backendUrl.includes('127.0.0.1')
  const protections = [
    {
      icon: Server,
      label: 'Backend restrito ao loopback',
      detail: backendStatus.connected ? `FastAPI saudável em ${backendUrl}` : `Sem resposta em ${backendUrl}`,
      active: backendStatus.connected && loopback,
    },
    {
      icon: Wifi,
      label: 'Inferência local',
      detail: backendStatus.ollama ? `Ollama conectado · ${backendStatus.model}` : 'Ollama não está acessível em localhost:11434.',
      active: backendStatus.ollama,
    },
    {
      icon: KeyRound,
      label: 'Token Electron ↔ FastAPI',
      detail: electronBridge ? 'X-Luna-Token obtido somente pela bridge restrita do preload.' : 'Validação disponível ao executar dentro do Electron.',
      active: electronBridge,
    },
    {
      icon: LockKeyhole,
      label: 'Context isolation, sandbox e CSP',
      detail: electronBridge ? 'Renderer isolado; navegação externa e permissões sensíveis são bloqueadas.' : 'Proteções aplicadas pelo processo principal do Electron.',
      active: electronBridge,
    },
    {
      icon: FolderLock,
      label: 'Escopo de filesystem',
      detail: workspacePath ? `Acesso limitado ao workspace: ${workspacePath}` : 'Selecione um workspace antes de operar em arquivos.',
      active: Boolean(workspacePath),
    },
    {
      icon: Shield,
      label: 'Copiloto zero-cloud supervisionado',
      detail: 'Nenhuma conta remota ou saldo é necessário; ações sensíveis permanecem sob controle do operador.',
      active: backendStatus.zeroCloudMode && backendStatus.supervisedMode,
    },
  ]

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-6 py-6">
        <header className="flex flex-wrap items-start justify-between gap-4 border-b border-cyber-cyan/10 pb-5">
          <div>
            <div className="mb-2 flex items-center gap-2 font-mono text-[9px] text-cyber-muted"><Terminal size={11} className="text-cyber-cyan" /> SECURITY POSTURE</div>
            <h1 className="text-2xl font-bold tracking-tight text-cyber-text">Segurança local</h1>
            <p className="mt-2 max-w-[68ch] text-[12px] leading-relaxed text-cyber-muted">Estado das proteções que isolam o renderer, o backend e o workspace. Nenhum indicador abaixo representa uma simulação de ataque.</p>
          </div>
          <button type="button" onClick={() => void refreshBackendHealth(true)} disabled={healthLoading} className="inline-flex min-h-10 items-center gap-2 rounded-md border border-cyber-cyan/20 bg-cyber-cyan/5 px-3 font-mono text-[10px] text-cyber-cyan transition-colors hover:bg-cyber-cyan/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan/50 disabled:opacity-50">
            <RefreshCw size={12} className={healthLoading ? 'animate-spin' : ''} /> Verificar
          </button>
        </header>

        <div className="mt-5 grid gap-4 lg:grid-cols-[1fr_0.72fr]">
          <section className="rounded-xl border border-cyber-cyan/10 bg-[#0d1422]/80 px-4">
            <div className="flex items-center justify-between border-b border-cyber-cyan/10 py-3">
              <h2 className="text-sm font-semibold text-cyber-text">Camadas ativas</h2>
              {backendStatus.checkedAt ? <span className="font-mono text-[8px] text-cyber-muted">{new Date(backendStatus.checkedAt).toLocaleTimeString('pt-BR')}</span> : null}
            </div>
            {protections.map((protection) => <ProtectionRow key={protection.label} {...protection} />)}
          </section>

          <div className="space-y-4">
            <section className="rounded-xl border border-cyber-green/15 bg-cyber-green/5 p-4">
              <div className="flex items-start gap-3">
                <CheckCircle2 size={18} className="mt-0.5 flex-shrink-0 text-cyber-green" />
                <div>
                  <h2 className="text-[12px] font-semibold text-cyber-text">Fluxo local sem conta</h2>
                  <p className="mt-1 text-[10px] leading-relaxed text-cyber-muted">A aplicação inicia diretamente no shell principal e conversa com o modelo local. O token exibido nesta página é técnico e protege apenas o canal IPC/backend.</p>
                </div>
              </div>
            </section>

            <section className="rounded-xl border border-amber-400/15 bg-amber-400/5 p-4">
              <div className="flex items-start gap-3">
                <AlertCircle size={18} className="mt-0.5 flex-shrink-0 text-amber-300" />
                <div>
                  <h2 className="text-[12px] font-semibold text-cyber-text">Responsabilidade do operador</h2>
                  <ul className="mt-2 space-y-1.5 text-[10px] leading-relaxed text-cyber-muted">
                    <li>· Defina escopo e autorização antes de qualquer teste.</li>
                    <li>· Revise comandos e alterações antes de executá-los.</li>
                    <li>· Não compartilhe o arquivo local de token.</li>
                    <li>· Mantenha Ollama e dependências atualizados.</li>
                  </ul>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Security
