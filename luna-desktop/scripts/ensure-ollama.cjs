const fs = require('fs')
const net = require('net')
const path = require('path')
const { spawn } = require('child_process')

const HOST = process.env.OLLAMA_HOST?.split(':')[0] || '127.0.0.1'
const PORT = Number(process.env.OLLAMA_HOST?.split(':').pop()) || 11434
const START_TIMEOUT_MS = 15000

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function isPortOpen(timeoutMs = 500) {
  return new Promise(resolve => {
    const socket = net.createConnection({ host: HOST, port: PORT })
    let settled = false

    const finish = value => {
      if (settled) return
      settled = true
      socket.destroy()
      resolve(value)
    }

    socket.setTimeout(timeoutMs)
    socket.once('connect', () => finish(true))
    socket.once('timeout', () => finish(false))
    socket.once('error', () => finish(false))
  })
}

function ollamaCandidates() {
  const candidates = []

  if (process.env.OLLAMA_EXE) {
    candidates.push(process.env.OLLAMA_EXE)
  }

  if (process.platform === 'win32') {
    const localAppData = process.env.LOCALAPPDATA
    const programFiles = process.env.ProgramFiles
    const programFilesX86 = process.env['ProgramFiles(x86)']

    if (localAppData) {
      candidates.push(path.join(localAppData, 'Programs', 'Ollama', 'ollama.exe'))
      candidates.push(path.join(localAppData, 'Ollama', 'ollama.exe'))
    }
    if (programFiles) candidates.push(path.join(programFiles, 'Ollama', 'ollama.exe'))
    if (programFilesX86) candidates.push(path.join(programFilesX86, 'Ollama', 'ollama.exe'))
  }

  // Last resort: rely on PATH.
  candidates.push(process.platform === 'win32' ? 'ollama.exe' : 'ollama')
  return [...new Set(candidates)]
}

function candidateExists(candidate) {
  // Plain executable names are resolved by PATH at spawn time.
  if (!candidate.includes(path.sep) && !candidate.includes('/')) return true
  return fs.existsSync(candidate)
}

function spawnDetached(command) {
  return new Promise((resolve, reject) => {
    let child
    try {
      child = spawn(command, ['serve'], {
        detached: true,
        stdio: 'ignore',
        windowsHide: true,
        env: { ...process.env },
      })
    } catch (error) {
      reject(error)
      return
    }

    const onError = error => reject(error)
    child.once('error', onError)
    child.once('spawn', () => {
      child.removeListener('error', onError)
      child.unref()
      resolve()
    })
  })
}

async function waitForOllama() {
  const deadline = Date.now() + START_TIMEOUT_MS
  while (Date.now() < deadline) {
    if (await isPortOpen()) return true
    await sleep(300)
  }
  return false
}

async function main() {
  if (await isPortOpen()) {
    console.log(`[Luna] Ollama já está ativo em ${HOST}:${PORT}.`)
    return
  }

  console.log(`[Luna] Ollama não está ativo em ${HOST}:${PORT}. Tentando iniciar...`)

  let lastError = null
  for (const candidate of ollamaCandidates()) {
    if (!candidateExists(candidate)) continue

    try {
      console.log(`[Luna] Iniciando Ollama com: ${candidate} serve`)
      await spawnDetached(candidate)

      if (await waitForOllama()) {
        console.log(`[Luna] Ollama pronto em ${HOST}:${PORT}.`)
        return
      }

      lastError = new Error(`processo iniciou, mas a porta ${PORT} não ficou disponível em ${START_TIMEOUT_MS / 1000}s`)
    } catch (error) {
      lastError = error
    }
  }

  const details = lastError instanceof Error ? lastError.message : String(lastError || 'executável não encontrado')
  console.error('[Luna] Falha ao iniciar o Ollama automaticamente.')
  console.error(`[Luna] Detalhe: ${details}`)
  console.error('[Luna] Confirme a instalação com "ollama --version" ou defina OLLAMA_EXE com o caminho do ollama.exe.')
  process.exitCode = 1
}

main().catch(error => {
  console.error('[Luna] Erro inesperado ao preparar Ollama:', error)
  process.exitCode = 1
})
