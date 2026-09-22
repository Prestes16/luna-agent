
/**
 * Luna Voice Service
 * ─────────────────────────────────────────────────────────────────────────────
 * TTS  — Web Speech API / voz instalada no sistema
 * STT  — Web Speech API (browser nativo, sem custo, sem API key)
 * ─────────────────────────────────────────────────────────────────────────────
 */

// ── Types ─────────────────────────────────────────────────────────────────────

export type VoiceId = 'nova' | 'shimmer' | 'coral' | 'alloy' | 'echo' | 'fable' | 'onyx'

export interface VoiceOptions {
  voice?:  VoiceId
  speed?:  number   // 0.25 – 4.0
  model?:  'tts-1' | 'tts-1-hd'
}

export interface SpeakResult {
  ok:      boolean
  error?:  string
  duration?: number   // ms
}

// ── State ─────────────────────────────────────────────────────────────────────

let _utterance:     SpeechSynthesisUtterance | null = null
let _isSpeaking     = false
let _onStateChange: ((speaking: boolean) => void) | null = null

export function onSpeakingChange(cb: (speaking: boolean) => void) {
  _onStateChange = cb
}

function _setState(v: boolean) {
  _isSpeaking = v
  _onStateChange?.(v)
}

export function isSpeaking() { return _isSpeaking }

// ── Markdown → plain text for TTS ─────────────────────────────────────────────

export function stripMarkdown(text: string): string {
  return text
    // Remove code blocks entirely — never read source code aloud
    .replace(/```[\s\S]*?```/g, ', bloco de código omitido,')
    // Inline code → read just the content, no backticks
    .replace(/`([^`]+)`/g, '$1')
    // Headers → just the text, add a natural pause
    .replace(/^#{1,6}\s+(.+)$/gm, '$1.')
    // Bold/italic → plain text
    .replace(/\*\*\*(.+?)\*\*\*/g, '$1')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    .replace(/_(.+?)_/g, '$1')
    // Links → just the label
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    // Images → remove entirely
    .replace(/!\[[^\]]*\]\([^)]+\)/g, '')
    // Horizontal rules → short pause
    .replace(/^[-*_]{3,}$/gm, '')
    // Numbered lists → convert to natural speech ("Primeiro: ..., Segundo: ...,")
    .replace(/^\s*(\d+)\.\s+(.+)$/gm, (_, _n, content) => `${content}.`)
    // Bullet points → just the content with a pause
    .replace(/^\s*[-*+▸•]\s+(.+)$/gm, '$1.')
    // Blockquotes
    .replace(/^>\s*/gm, '')
    // HTML tags
    .replace(/<[^>]+>/g, '')
    // Unicode dividers/decorators (━, ─, etc.)
    .replace(/[━─═]{3,}/g, '')
    // Checkmarks and emoji bullets that sound bad in TTS
    .replace(/[✅✓✗✦⚠🔓📁📄📂🌐🔍]/g, '')
    // Multiple newlines → single pause
    .replace(/\n{2,}/g, '. ')
    .replace(/\n/g, ', ')
    // Multiple spaces/dots
    .replace(/\.\s*\.\s*\./g, '.')
    .replace(/,\s*,/g, ',')
    .replace(/[ \t]{2,}/g, ' ')
    .trim()
}

// ── TTS — speak via backend ────────────────────────────────────────────────────

export async function speak(
  rawText: string,
  _backendUrl: string,
  opts: VoiceOptions = {},
): Promise<SpeakResult> {
  const text = stripMarkdown(rawText).slice(0, 4000)
  if (!text) return { ok: true }
  if (!('speechSynthesis' in window) || typeof SpeechSynthesisUtterance === 'undefined') {
    return { ok: false, error: 'Síntese de voz não disponível neste sistema.' }
  }

  stop()
  const startedAt = Date.now()
  const utterance = new SpeechSynthesisUtterance(text)
  const preferences: Record<VoiceId, string[]> = {
    nova: ['Microsoft Francisca', 'Luciana', 'Google português do Brasil'],
    shimmer: ['Microsoft Maria', 'Helena'],
    coral: ['Microsoft Letícia', 'Camila'],
    alloy: ['Microsoft Daniel', 'Google US English'],
    echo: ['Microsoft Antonio', 'Ricardo'],
    fable: ['Microsoft Duarte', 'Google UK English Male'],
    onyx: ['Microsoft Fabio', 'Felipe'],
  }

  utterance.lang = 'pt-BR'
  utterance.rate = Math.min(2, Math.max(0.5, opts.speed ?? 1))
  const voices = window.speechSynthesis.getVoices()
  const preferred = preferences[opts.voice ?? 'nova']
  utterance.voice = voices.find((voice) =>
    preferred.some((name) => voice.name.toLocaleLowerCase().includes(name.toLocaleLowerCase())),
  ) ?? voices.find((voice) => voice.lang.toLocaleLowerCase().startsWith('pt-br')) ?? null

  _utterance = utterance
  _setState(true)

  return new Promise<SpeakResult>((resolve) => {
    utterance.onend = () => {
      if (_utterance === utterance) _utterance = null
      _setState(false)
      resolve({ ok: true, duration: Date.now() - startedAt })
    }
    utterance.onerror = (event) => {
      if (_utterance === utterance) _utterance = null
      _setState(false)
      resolve({ ok: false, error: event.error || 'Falha na síntese de voz local.' })
    }
    window.speechSynthesis.speak(utterance)
  })
}

export function stop() {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
  _utterance = null
  _setState(false)
}

// ── STT — Speech-to-Text via Web Speech API ───────────────────────────────────

export type STTState = 'idle' | 'listening' | 'processing' | 'error'

interface STTHandlers {
  onResult:      (transcript: string, final: boolean) => void
  onStateChange: (state: STTState) => void
  onError:       (msg: string) => void
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyRec = any

class LunaSTT {
  private rec: AnyRec | null = null
  private handlers: STTHandlers | null = null
  private _state: STTState = 'idle'

  readonly supported = typeof window !== 'undefined' &&
    ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)

  get state() { return this._state }

  private setState(s: STTState) {
    this._state = s
    this.handlers?.onStateChange(s)
  }

  start(handlers: STTHandlers, lang = 'pt-BR') {
    if (!this.supported) {
      handlers.onError('Web Speech API não suportada neste browser.')
      return
    }
    this.stop()
    this.handlers = handlers

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const SR = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition
    this.rec = new SR()

    this.rec.lang            = lang
    this.rec.continuous      = false
    this.rec.interimResults  = true
    this.rec.maxAlternatives = 1

    this.rec.onstart = () => this.setState('listening')

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    this.rec.onresult = (ev: any) => {
      const result     = ev.results[ev.results.length - 1]
      const transcript = result[0].transcript as string
      const final      = result.isFinal as boolean
      if (final) this.setState('processing')
      handlers.onResult(transcript, final)
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    this.rec.onerror = (ev: any) => {
      const msgs: Record<string, string> = {
        'not-allowed': 'Permissão de microfone negada.',
        'no-speech':   'Nenhuma fala detectada.',
        'network':     'Erro de rede no reconhecimento.',
        'aborted':     '',
      }
      const msg = msgs[ev.error as string] ?? `Erro STT: ${ev.error}`
      if (msg) handlers.onError(msg)
      this.setState('idle')
    }

    this.rec.onend = () => {
      if (this._state !== 'processing') this.setState('idle')
    }

    try {
      this.rec.start()
    } catch (e: unknown) {
      handlers.onError((e as Error).message)
      this.setState('idle')
    }
  }

  stop() {
    try { this.rec?.stop() } catch { /* ignore */ }
    this.rec = null
    this.setState('idle')
  }
}

export const stt = new LunaSTT()

// ── Available voices metadata ─────────────────────────────────────────────────

export const VOICES: Array<{ id: VoiceId; label: string; style: string; feminine: boolean }> = [
  { id: 'nova',    label: 'Nova',    style: 'Calorosa, clara, natural',        feminine: true  },
  { id: 'shimmer', label: 'Shimmer', style: 'Suave, expressiva, gentil',       feminine: true  },
  { id: 'coral',   label: 'Coral',   style: 'Energética, jovem, direta',       feminine: true  },
  { id: 'alloy',   label: 'Alloy',   style: 'Neutra, profissional',            feminine: false },
  { id: 'fable',   label: 'Fable',   style: 'Narrativa, dramática',            feminine: false },
  { id: 'echo',    label: 'Echo',    style: 'Masculina, profunda',             feminine: false },
  { id: 'onyx',    label: 'Onyx',    style: 'Masculina, grave, autoritativa',  feminine: false },
]
