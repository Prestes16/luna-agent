import { contextBridge, ipcRenderer } from 'electron'

const electronAPI = {
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  getAppPath:    () => ipcRenderer.invoke('get-app-path'),
  minimizeWindow: () => ipcRenderer.invoke('minimize-window'),
  maximizeWindow: () => ipcRenderer.invoke('maximize-window'),
  closeWindow:    () => ipcRenderer.invoke('close-window'),

  // Luna-specific APIs (legacy)
  sendMessage:    (message: string) => ipcRenderer.invoke('send-message', message),
  executeCommand: (command: string, args?: unknown) => ipcRenderer.invoke('execute-command', { command, args }),
  getMemory:      () => ipcRenderer.invoke('get-memory'),
  clearMemory:    () => ipcRenderer.invoke('clear-memory'),

  // Event listeners
  onLunaResponse: (callback: (response: unknown) => void) => {
    ipcRenderer.on('luna-response', (_event, data) => callback(data))
  },
  onLunaThinking: (callback: (status: string) => void) => {
    ipcRenderer.on('luna-thinking', (_event, status) => callback(status))
  },
  onLunaError: (callback: (error: string) => void) => {
    ipcRenderer.on('luna-error', (_event, error) => callback(error))
  },

  // ── Workspace / Filesystem API ────────────────────────────────────────────
  workspace: {
    /** Tell the main process which workspace is active (for fs handler guards). */
    setWorkspace: (p: string | null): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke('fs:setWorkspace', p),

    /** Open native OS folder picker — returns {canceled, filePaths} */
    openFolderDialog: (): Promise<{ canceled: boolean; filePaths: string[] }> =>
      ipcRenderer.invoke('dialog:openFolder'),

    /** Create a new project folder after picking a parent — returns {canceled, filePaths, error?} */
    newProjectDialog: (projectName: string): Promise<{ canceled: boolean; filePaths: string[]; error?: string }> =>
      ipcRenderer.invoke('dialog:newProject', projectName),

    /** List directory entries (name, isDirectory, path) */
    readDir: (dirPath: string): Promise<Array<{ name: string; isDirectory: boolean; path: string }> | { error: string }> =>
      ipcRenderer.invoke('fs:readDir', dirPath),

    /** Read file content as UTF-8 string */
    readFile: (filePath: string): Promise<{ content: string } | { error: string }> =>
      ipcRenderer.invoke('fs:readFile', filePath),

    /** Write content to a file (creates dirs if needed) */
    writeFile: (filePath: string, content: string): Promise<{ success: true } | { error: string }> =>
      ipcRenderer.invoke('fs:writeFile', filePath, content),

    /** Create a directory recursively */
    createDir: (dirPath: string): Promise<{ success: true } | { error: string }> =>
      ipcRenderer.invoke('fs:createDir', dirPath),

    /** Check whether a path exists */
    exists: (p: string): Promise<boolean> =>
      ipcRenderer.invoke('fs:exists', p),

    /** Get file stats (size, isDirectory, mtime) */
    stat: (p: string): Promise<{ size: number; isDirectory: boolean; mtime: number } | null> =>
      ipcRenderer.invoke('fs:stat', p),

    /** Delete a file or directory */
    deleteFile: (p: string): Promise<{ success: true } | { error: string }> =>
      ipcRenderer.invoke('fs:deleteFile', p),
  },

  // ── Shell API — abre URLs no browser padrão do sistema operacional ────────
  shell: {
    /** Abre uma URL https no browser padrão do SO (não no Electron). */
    openExternal: (url: string): Promise<{ ok: boolean; error?: string }> =>
      ipcRenderer.invoke('shell:openExternal', url),
  },

  // ── Auth API ─────────────────────────────────────────────────────────────
  auth: {
    /** Obtém o token de autenticação gerado no startup para incluir em X-Luna-Token */
    getToken: (): Promise<string> => ipcRenderer.invoke('auth:getToken'),

    /** Persiste tokens Supabase no safeStorage (chamado após login OAuth) */
    saveSession: (accessToken: string, refreshToken: string): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke('auth:saveSession', accessToken, refreshToken),

    /** Recupera tokens Supabase do safeStorage ao iniciar o app */
    loadSession: (): Promise<{ accessToken: string; refreshToken: string } | null> =>
      ipcRenderer.invoke('auth:loadSession'),

    /** Remove tokens Supabase do safeStorage (logout) */
    clearSession: (): Promise<void> =>
      ipcRenderer.invoke('auth:clearSession'),

    /** Escuta deep links OAuth — luna-agent://auth/callback#access_token=... */
    onDeepLink: (callback: (url: string) => void) => {
      ipcRenderer.on('auth:deeplink', (_event, url) => callback(url))
    },
  },

  // ── User ID API — ID único e persistente por instalação ──────────────────
  /** Retorna o user ID desta instalação (gerado uma vez, salvo via safeStorage). */
  getUserId: (): Promise<string> => ipcRenderer.invoke('get-user-id'),

  // ── Secure Keys API (safeStorage) ────────────────────────────────────────
  // Armazena API keys usando Keychain/DPAPI/libsecret — nunca em texto plano
  keys: {
    /** Salva uma API key de forma segura pelo nome do provedor */
    set: (name: string, value: string): Promise<{ ok: boolean; error?: string }> =>
      ipcRenderer.invoke('keys:set', name, value),

    /** Recupera uma API key pelo nome do provedor */
    get: (name: string): Promise<{ value?: string; error?: string }> =>
      ipcRenderer.invoke('keys:get', name),

    /** Remove uma API key */
    delete: (name: string): Promise<{ ok: boolean; error?: string }> =>
      ipcRenderer.invoke('keys:delete', name),

    /** Lista os nomes dos provedores com keys salvas */
    list: (): Promise<string[]> => ipcRenderer.invoke('keys:list'),
  },
}

contextBridge.exposeInMainWorld('electronAPI', electronAPI)

declare global {
  interface Window {
    electronAPI: typeof electronAPI
  }
}
