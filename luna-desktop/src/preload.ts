import { contextBridge, ipcRenderer } from 'electron'

const electronAPI = {
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  getAppPath: () => ipcRenderer.invoke('get-app-path'),
  minimizeWindow: () => ipcRenderer.invoke('minimize-window'),
  maximizeWindow: () => ipcRenderer.invoke('maximize-window'),
  closeWindow: () => ipcRenderer.invoke('close-window'),

  // Legacy Luna channels retained for compatibility with existing local flows.
  sendMessage: (message: string) => ipcRenderer.invoke('send-message', message),
  executeCommand: (command: string, args?: unknown) =>
    ipcRenderer.invoke('execute-command', { command, args }),
  getMemory: () => ipcRenderer.invoke('get-memory'),
  clearMemory: () => ipcRenderer.invoke('clear-memory'),

  onLunaResponse: (callback: (response: unknown) => void) => {
    ipcRenderer.on('luna-response', (_event, data) => callback(data))
  },
  onLunaThinking: (callback: (status: string) => void) => {
    ipcRenderer.on('luna-thinking', (_event, status) => callback(status))
  },
  onLunaError: (callback: (error: string) => void) => {
    ipcRenderer.on('luna-error', (_event, error) => callback(error))
  },

  workspace: {
    setWorkspace: (path: string | null): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke('fs:setWorkspace', path),
    openFolderDialog: (): Promise<{ canceled: boolean; filePaths: string[] }> =>
      ipcRenderer.invoke('dialog:openFolder'),
    newProjectDialog: (projectName: string): Promise<{ canceled: boolean; filePaths: string[]; error?: string }> =>
      ipcRenderer.invoke('dialog:newProject', projectName),
    readDir: (dirPath: string): Promise<Array<{ name: string; isDirectory: boolean; path: string }> | { error: string }> =>
      ipcRenderer.invoke('fs:readDir', dirPath),
    readFile: (filePath: string): Promise<{ content: string } | { error: string }> =>
      ipcRenderer.invoke('fs:readFile', filePath),
    writeFile: (filePath: string, content: string): Promise<{ success: true } | { error: string }> =>
      ipcRenderer.invoke('fs:writeFile', filePath, content),
    createDir: (dirPath: string): Promise<{ success: true } | { error: string }> =>
      ipcRenderer.invoke('fs:createDir', dirPath),
    exists: (path: string): Promise<boolean> =>
      ipcRenderer.invoke('fs:exists', path),
    stat: (path: string): Promise<{ size: number; isDirectory: boolean; mtime: number } | null> =>
      ipcRenderer.invoke('fs:stat', path),
    deleteFile: (path: string): Promise<{ success: true } | { error: string }> =>
      ipcRenderer.invoke('fs:deleteFile', path),
  },

  shell: {
    openExternal: (url: string): Promise<{ ok: boolean; error?: string }> =>
      ipcRenderer.invoke('shell:openExternal', url),
  },

  // Local security token only; this is not a remote account credential.
  auth: {
    getToken: (): Promise<string> => ipcRenderer.invoke('auth:getToken'),
  },
}

contextBridge.exposeInMainWorld('electronAPI', electronAPI)

declare global {
  interface Window {
    electronAPI: typeof electronAPI
  }
}
