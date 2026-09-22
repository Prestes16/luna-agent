import type { BackendStatus } from '@store/appStore'

interface HealthPayload {
  status?: string
  version?: string
  model?: string
  mode?: string
  ollama?: boolean
  available_models?: string[]
  zero_cloud_mode?: boolean
  supervised_mode?: boolean
  modules?: BackendStatus['modules']
}

let inFlight: { key: string; promise: Promise<BackendStatus> } | null = null

export function fetchRuntimeHealth(backendUrl: string, token: string): Promise<BackendStatus> {
  const key = `${backendUrl}\u0000${token}`
  if (inFlight?.key === key) return inFlight.promise

  const promise = fetch(`${backendUrl}/health`, {
    headers: token ? { 'X-Luna-Token': token } : undefined,
    signal: AbortSignal.timeout(4_000),
  })
    .then(async (response) => {
      if (!response.ok) throw new Error(`Backend local respondeu HTTP ${response.status}`)
      const data = await response.json() as HealthPayload
      return {
        connected: data.status === 'healthy',
        model: data.model ?? 'luna-cyber-fast',
        version: data.version ?? '4.0',
        mode: data.mode ?? 'local_copilot',
        ollama: Boolean(data.ollama),
        availableModels: Array.isArray(data.available_models) ? data.available_models : [],
        zeroCloudMode: data.zero_cloud_mode !== false,
        supervisedMode: data.supervised_mode !== false,
        modules: data.modules,
        checkedAt: Date.now(),
        error: '',
      }
    })
    .finally(() => {
      if (inFlight?.promise === promise) inFlight = null
    })

  inFlight = { key, promise }
  return promise
}
