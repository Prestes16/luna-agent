import { describe, expect, it } from 'vitest'
import { stripMarkdown } from './voiceService'

describe('stripMarkdown', () => {
  it('keeps mentor guidance speakable and omits command blocks', () => {
    const spoken = stripMarkdown(
      'PRÓXIMO PASSO:\n1. Abra o Network.\n2. Clique na requisição.\n```bash\ncurl -i http://127.0.0.1:8080/\n```',
    )

    expect(spoken).toContain('PRÓXIMO PASSO')
    expect(spoken).toContain('Abra o Network')
    expect(spoken).toContain('Clique na requisição')
    expect(spoken).toContain('bloco de código omitido')
    expect(spoken).not.toContain('```')
    expect(spoken).not.toContain('http://127.0.0.1:8080')
  })
})
