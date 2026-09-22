import { describe, expect, it } from 'vitest'
import { backendLogLines, classifyBackendLog } from './backendLog'

describe('backend logging', () => {
  it('não classifica INFO do uvicorn como erro só porque veio no stderr', () => {
    expect(classifyBackendLog('INFO:     127.0.0.1:51000 - "GET /health HTTP/1.1" 200 OK')).toBe('info')
    expect(classifyBackendLog('2026-08-14 - app - INFO - Luna Engine ready - providers: Ollama')).toBe('info')
  })

  it('preserva níveis warning e error', () => {
    expect(classifyBackendLog('WARNING: Ollama indisponível')).toBe('warn')
    expect(classifyBackendLog('2026-08-14 - app - ERROR - geração falhou')).toBe('error')
  })

  it('separa linhas de um mesmo chunk', () => {
    expect(backendLogLines('INFO: ready\r\nERROR: failed\r\n')).toEqual(['INFO: ready', 'ERROR: failed'])
  })
})
