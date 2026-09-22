export type BackendLogLevel = 'info' | 'warn' | 'error'

const ERROR_LINE = /(?:^|\s)(?:ERROR|CRITICAL)(?::|\s+-)|Traceback \(most recent call last\)|\b(?:Exception|Error):/i
const WARNING_LINE = /(?:^|\s)(?:WARN|WARNING)(?::|\s+-)/i

export function classifyBackendLog(line: string): BackendLogLevel {
  if (ERROR_LINE.test(line)) return 'error'
  if (WARNING_LINE.test(line)) return 'warn'
  return 'info'
}

export function backendLogLines(chunk: string): string[] {
  return chunk
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
}
