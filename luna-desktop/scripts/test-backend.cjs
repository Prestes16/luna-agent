#!/usr/bin/env node

const fs = require('fs')
const path = require('path')
const { spawnSync } = require('child_process')

const root = path.resolve(__dirname, '..')
const backendDir = path.join(root, 'backend')
const venvPython = process.platform === 'win32'
  ? path.join(backendDir, '.venv', 'Scripts', 'python.exe')
  : path.join(backendDir, '.venv', 'bin', 'python')

const python = fs.existsSync(venvPython)
  ? venvPython
  : (process.platform === 'win32' ? 'python' : 'python3')

console.log(`[Luna] Backend test interpreter: ${python}`)

const result = spawnSync(
  python,
  ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-v'],
  {
    cwd: backendDir,
    stdio: 'inherit',
    env: {
      ...process.env,
      PYTHONUTF8: '1',
      PYTHONIOENCODING: 'utf-8',
    },
  },
)

if (result.error) {
  console.error(`[Luna] Falha ao iniciar os testes: ${result.error.message}`)
  process.exit(1)
}

if ((result.status ?? 1) !== 0) {
  if (!fs.existsSync(venvPython)) {
    console.error('\n[Luna] O .venv do backend não foi encontrado. Instale as dependências com:')
    console.error(`  ${python} -m pip install -r "${path.join(backendDir, 'requirements.txt')}"`)
  }
  process.exit(result.status ?? 1)
}

process.exit(0)
