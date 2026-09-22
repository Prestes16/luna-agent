import { app, BrowserWindow, ipcMain, Menu, session, dialog, shell } from 'electron'
import path from 'path'
import fs from 'fs'
import { randomBytes } from 'crypto'
import { spawn } from 'child_process'
import { StringDecoder } from 'string_decoder'
import { backendLogLines, classifyBackendLog } from './utils/backendLog'

// Use Electron's built-in isPackaged flag — no extra dependency needed
const isDev = !app.isPackaged

// Keep a consistent userData path in development and production.
app.setName('luna-agent')

// Disable GPU acceleration to prevent GPU process crashes on Windows
// (exit_code=-1073740791 / STATUS_STACK_BUFFER_OVERRUN with some drivers)
app.disableHardwareAcceleration()

// Single-instance lock avoids duplicate local backend processes.
if (process.platform !== 'darwin') {
  const gotLock = app.requestSingleInstanceLock()
  if (!gotLock) {
    app.quit()
  }
}

let mainWindow: BrowserWindow | null = null
let pythonProcess: any = null

// ── IPC Auth Token ─────────────────────────────────────────────────────────
// Sincronizado com o backend via ~/.luna-agent/.api_token.
// A mesma lógica do security.py:get_or_create_api_token() é replicada aqui
// para que o token seja idêntico independente de como o backend foi iniciado
// (spawn interno pelo Electron OU processo externo via start-backend.bat).
function getLunaApiToken(): string {
  // 1. Variável de ambiente tem prioridade (CI, Docker, etc.)
  const envTok = (process.env.LUNA_API_TOKEN || '').trim()
  if (envTok) return envTok

  // 2. Lê do arquivo persistido pelo backend (mesmo path que security.py usa)
  const tokenFile = path.join(app.getPath('home'), '.luna-agent', '.api_token')
  try {
    if (fs.existsSync(tokenFile)) {
      const val = fs.readFileSync(tokenFile, 'utf-8').trim()
      if (val) return val
    }
  } catch { /* ignora — vai gerar abaixo */ }

  // 3. Gera novo token, persiste para que o backend leia na próxima inicialização
  const tok = randomBytes(32).toString('hex')
  try {
    const dir = path.dirname(tokenFile)
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })
    fs.writeFileSync(tokenFile, tok, { encoding: 'utf-8', mode: 0o600 })
  } catch (e) {
    console.warn('[Luna] Não foi possível persistir o API token:', e)
  }
  return tok
}

const LUNA_API_TOKEN: string = getLunaApiToken()

const createWindow = () => {
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 1200,
    minHeight: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true
    },
    icon: path.join(__dirname, '../assets/luna-icon.png')
  })

  const startUrl = isDev
    ? 'http://localhost:5173'
    : `file://${path.join(__dirname, '../dist/index.html')}`

  mainWindow.loadURL(startUrl)

  // In dev mode, Vite may not be ready yet — retry every 2s until it connects
  if (isDev) {
    mainWindow.webContents.on('did-fail-load', (_event, errorCode, _errorDescription) => {
      if (errorCode === -102 || errorCode === -6) {
        // ERR_CONNECTION_REFUSED or ERR_NAME_NOT_RESOLVED — Vite not ready yet
        console.log('[Luna] Vite not ready, retrying in 2s...')
        setTimeout(() => {
          mainWindow?.loadURL('http://localhost:5173')
        }, 2000)
      }
    })
    mainWindow.webContents.openDevTools()
  }

  // Intercepta window.open() no renderer e redireciona para o browser padrão do SO.
  // Sem isso, window.open() abre uma janela Electron vazia (sandbox=true bloqueia).
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://') || url.startsWith('https://')) {
      shell.openExternal(url)
    }
    return { action: 'deny' } // nunca abre nova janela Electron
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

const startPythonBackend = () => {
  // Check if a backend is already running on port 8000 before spawning a new one
  const http = require('http')
  const req = http.get('http://127.0.0.1:8000/health', (res: any) => {
    if (res.statusCode === 200) {
      console.log('[Luna] Backend already running on :8000 — skipping spawn')
      return
    }
    _spawnBackend()
  })
  req.on('error', () => _spawnBackend())
  req.setTimeout(1500, () => { req.destroy(); _spawnBackend() })
}

const _spawnBackend = () => {
  const pythonScript = path.join(__dirname, '../backend/main.py')
  const backendDir = path.join(__dirname, '../backend')
  const venvPython = process.platform === 'win32'
    ? path.join(backendDir, '.venv', 'Scripts', 'python.exe')
    : path.join(backendDir, '.venv', 'bin', 'python')
  const pythonExecutable = fs.existsSync(venvPython) ? venvPython : 'python'

  pythonProcess = spawn(pythonExecutable, [pythonScript], {
    cwd: backendDir,
    stdio: 'pipe',
    env: {
      ...process.env,
      // Injeta token de auth para o middleware LunaSecurityMiddleware
      LUNA_API_TOKEN,
      PYTHONUTF8: '1',
      PYTHONIOENCODING: 'utf-8',
    },
  })

  const stdoutDecoder = new StringDecoder('utf8')
  const stderrDecoder = new StringDecoder('utf8')

  pythonProcess.stdout?.on('data', (data: Buffer) => {
    for (const line of backendLogLines(stdoutDecoder.write(data))) {
      console.log(`[Backend] ${line}`)
    }
  })

  pythonProcess.stderr?.on('data', (data: Buffer) => {
    for (const line of backendLogLines(stderrDecoder.write(data))) {
      const level = classifyBackendLog(line)
      if (level === 'error') console.error(`[Backend Error] ${line}`)
      else if (level === 'warn') console.warn(`[Backend Warning] ${line}`)
      else console.log(`[Backend] ${line}`)
    }
  })

  pythonProcess.on('close', (code: number) => {
    console.log(`[Backend] process exited with code ${code}`)
  })
}


app.on('second-instance', () => {
  // Também restaura a janela se estiver minimizada
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.focus()
  }
})

app.on('ready', () => {
  // ── Content-Security-Policy ───────────────────────────────────────────────
  // Tighter CSP in production to eliminate Electron security warnings.
  // Dev mode keeps unsafe-eval/unsafe-inline so Vite HMR works correctly.
  // External APIs the backend proxies (Luna tools: web search, fetch, blockchain, etc.)
  const extApis = [
    'https://*.helius-rpc.com',
    'https://api.mainnet-beta.solana.com',
    'https://api.devnet.solana.com',
    'https://api.coingecko.com',
    'https://api.duckduckgo.com',
    'https://html.duckduckgo.com',
    'https://*.githubusercontent.com',
    'https://raw.githubusercontent.com',
  ].join(' ')

  const cspDev = [
    "default-src 'self' 'unsafe-inline' 'unsafe-eval'",
    `connect-src 'self' http://localhost:* ws://localhost:* ${extApis}`,
    "font-src 'self' data:",
    "img-src 'self' data: blob: https:",
    "style-src 'self' 'unsafe-inline'",
    "media-src 'self' blob: data:",
  ].join('; ')

  const cspProd = [
    "default-src 'self'",
    "script-src 'self'",
    `connect-src 'self' ${extApis}`,
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self' data:",
    "img-src 'self' data: blob: https:",
    "media-src 'self' blob: data:",
  ].join('; ')

  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [isDev ? cspDev : cspProd],
      },
    })
  })

  // Block navigation and new windows for defense-in-depth (network isolation).
  app.on('web-contents-created', (_evt, contents) => {
    contents.on('will-navigate', (e, url) => {
      const allowed = url.startsWith('http://localhost:') ||
                      url.startsWith('http://127.0.0.1:') ||
                      url.startsWith('file://')
      if (!allowed) { e.preventDefault() }
    })
    contents.setWindowOpenHandler(({ url }) => {
      if (url.startsWith('http://') || url.startsWith('https://')) {
        try { require('electron').shell.openExternal(url) } catch { /* noop */ }
      }
      return { action: 'deny' }
    })
    // Deny all sensitive permission requests by default.
    contents.session.setPermissionRequestHandler((_wc, permission, cb) => {
      const allowed = ['clipboard-read', 'clipboard-sanitized-write']
      cb(allowed.includes(permission))
    })
  })

  startPythonBackend()
  createWindow()
  createMenu()
})

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.kill()
  }
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow()
  }
})

const createMenu = () => {
  const template: any[] = [
    {
      label: 'File',
      submenu: [
        { label: 'Exit', accelerator: 'CmdOrCtrl+Q', click: () => app.quit() }
      ]
    },
    {
      label: 'Edit',
      submenu: [
        { label: 'Undo', accelerator: 'CmdOrCtrl+Z', selector: 'undo:' },
        { label: 'Redo', accelerator: 'Shift+CmdOrCtrl+Z', selector: 'redo:' },
        { type: 'separator' },
        { label: 'Cut', accelerator: 'CmdOrCtrl+X', selector: 'cut:' },
        { label: 'Copy', accelerator: 'CmdOrCtrl+C', selector: 'copy:' },
        { label: 'Paste', accelerator: 'CmdOrCtrl+V', selector: 'paste:' }
      ]
    },
    {
      label: 'View',
      submenu: [
        { label: 'Reload', accelerator: 'CmdOrCtrl+R', click: () => mainWindow?.reload() },
        { label: 'Toggle DevTools', accelerator: 'CmdOrCtrl+Shift+I', click: () => mainWindow?.webContents.toggleDevTools() }
      ]
    }
  ]

  Menu.setApplicationMenu(Menu.buildFromTemplate(template))
}

// ── Shell IPC — abre URLs no browser padrão do SO ─────────────────────────
ipcMain.handle('shell:openExternal', (_e, url: string) => {
  // Aceita https (qualquer host) e http apenas para localhost/127.0.0.1
  const isHttps     = url.startsWith('https://')
  const isLocalHttp = url.startsWith('http://localhost') || url.startsWith('http://127.0.0.1')
  if (isHttps || isLocalHttp) {
    shell.openExternal(url)
    return { ok: true }
  }
  return { ok: false, error: 'URL não permitida — use https:// ou http://localhost' }
})

// ── Window IPC ─────────────────────────────────────────────────────────────
ipcMain.handle('get-app-version', () => app.getVersion())
ipcMain.handle('get-app-path', () => app.getAppPath())
ipcMain.handle('minimize-window', () => mainWindow?.minimize())
ipcMain.handle('maximize-window', () => mainWindow?.maximize())
ipcMain.handle('close-window', () => mainWindow?.close())

// ── Workspace / Dialog IPC ─────────────────────────────────────────────────

/** Opens a native OS folder picker — returns {filePaths, canceled} */
ipcMain.handle('dialog:openFolder', async () => {
  return dialog.showOpenDialog(mainWindow!, {
    properties: ['openDirectory', 'createDirectory'],
    title: 'Selecionar Pasta de Trabalho da Luna',
    buttonLabel: 'Usar esta pasta',
    defaultPath: app.getPath('documents'),
  })
})

/** Opens a folder picker to choose WHERE to create a new project.
 *  After the user picks a parent folder, we create <parent>/<name> */
ipcMain.handle('dialog:newProject', async (_e, projectName: string) => {
  const result = await dialog.showOpenDialog(mainWindow!, {
    properties: ['openDirectory', 'createDirectory'],
    title: `Escolha onde criar "${projectName}"`,
    buttonLabel: 'Criar aqui',
    defaultPath: app.getPath('documents'),
  })
  if (result.canceled || !result.filePaths[0]) return { canceled: true }
  const newDir = path.join(result.filePaths[0], projectName)
  try {
    fs.mkdirSync(newDir, { recursive: true })
    return { canceled: false, filePaths: [newDir] }
  } catch (err: any) {
    return { canceled: false, error: err.message, filePaths: [result.filePaths[0]] }
  }
})

// ── Filesystem IPC ─────────────────────────────────────────────────────────
// SECURITY: all fs handlers require a valid, confirmed workspace path.
// Without this, a compromised renderer could read/write/delete any file.

/** Returns the currently stored workspace path from Electron's store (persisted
 *  in the renderer via Zustand → we mirror it here via a simple module-level var
 *  that the renderer updates through a dedicated IPC channel). */
let _allowedWorkspacePath: string | null = null

/** Renderer calls this whenever the user picks/clears a workspace. */
ipcMain.handle('fs:setWorkspace', (_e, p: string | null) => {
  _allowedWorkspacePath = p ? path.resolve(p) : null
  return { ok: true }
})

/**
 * Check that `target` is inside the allowed workspace.
 * Returns the resolved absolute path or null if denied.
 */
function _guardPath(target: string): string | null {
  if (!_allowedWorkspacePath) return null
  const resolved = path.resolve(target)
  // Must start with workspace root (+ separator to avoid prefix attacks)
  const base = _allowedWorkspacePath + path.sep
  if (resolved !== _allowedWorkspacePath && !resolved.startsWith(base)) return null
  return resolved
}

ipcMain.handle('fs:readDir', (_e, dirPath: string) => {
  const safe = _guardPath(dirPath)
  if (!safe) return { error: 'Acesso negado: fora do workspace' }
  try {
    const entries = fs.readdirSync(safe, { withFileTypes: true })
    return entries
      .filter(e => !e.name.startsWith('.'))  // skip hidden
      .map(e => ({
        name: e.name,
        isDirectory: e.isDirectory(),
        path: path.join(safe, e.name),
      }))
  } catch (err: any) {
    return { error: err.message }
  }
})

ipcMain.handle('fs:readFile', (_e, filePath: string) => {
  const safe = _guardPath(filePath)
  if (!safe) return { error: 'Acesso negado: fora do workspace' }
  try {
    const content = fs.readFileSync(safe, 'utf-8')
    return { content }
  } catch (err: any) {
    return { error: err.message }
  }
})

ipcMain.handle('fs:writeFile', (_e, filePath: string, content: string) => {
  const safe = _guardPath(filePath)
  if (!safe) return { error: 'Acesso negado: fora do workspace' }
  try {
    fs.mkdirSync(path.dirname(safe), { recursive: true })
    fs.writeFileSync(safe, content, 'utf-8')
    return { success: true }
  } catch (err: any) {
    return { error: err.message }
  }
})

ipcMain.handle('fs:createDir', (_e, dirPath: string) => {
  const safe = _guardPath(dirPath)
  if (!safe) return { error: 'Acesso negado: fora do workspace' }
  try {
    fs.mkdirSync(safe, { recursive: true })
    return { success: true }
  } catch (err: any) {
    return { error: err.message }
  }
})

ipcMain.handle('fs:exists', (_e, p: string) => {
  const safe = _guardPath(p)
  if (!safe) return false
  return fs.existsSync(safe)
})

ipcMain.handle('fs:stat', (_e, p: string) => {
  const safe = _guardPath(p)
  if (!safe) return null
  try {
    const stat = fs.statSync(safe)
    return { size: stat.size, isDirectory: stat.isDirectory(), mtime: stat.mtimeMs }
  } catch {
    return null
  }
})

ipcMain.handle('fs:deleteFile', (_e, filePath: string) => {
  const safe = _guardPath(filePath)
  if (!safe) return { error: 'Acesso negado: fora do workspace' }
  // Extra safety: do NOT allow deleting the workspace root itself
  if (safe === _allowedWorkspacePath) return { error: 'Não é permitido deletar o workspace root' }
  try {
    fs.rmSync(safe, { recursive: true, force: true })
    return { success: true }
  } catch (err: any) {
    return { error: err.message }
  }
})

// ── Auth Token IPC ─────────────────────────────────────────────────────────

/** Renderer obtém o token para incluir em X-Luna-Token nas chamadas ao backend. */
ipcMain.handle('auth:getToken', () => LUNA_API_TOKEN)
