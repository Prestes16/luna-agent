import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchLessonStats } from './lessons'

describe('fetchLessonStats', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('envia o token técnico local para a rota protegida', async () => {
    const payload = { total_lessons: 0, by_type: {} }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(payload),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchLessonStats('http://127.0.0.1:8000', 'local-token')).resolves.toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/lessons',
      expect.objectContaining({ headers: { 'X-Luna-Token': 'local-token' } }),
    )
  })

  it('não chama a rota sem token', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchLessonStats('http://127.0.0.1:8000', '')).rejects.toThrow(
      'Token técnico local indisponível',
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
