import type { LessonStats } from '@store/appStore'

export async function fetchLessonStats(
  backendUrl: string,
  lunaApiToken: string,
  signal?: AbortSignal,
): Promise<LessonStats> {
  if (!lunaApiToken) throw new Error('Token técnico local indisponível')

  const response = await fetch(`${backendUrl}/lessons`, {
    headers: { 'X-Luna-Token': lunaApiToken },
    signal,
  })
  if (!response.ok) {
    throw new Error(`Lessons local respondeu HTTP ${response.status}`)
  }
  return await response.json() as LessonStats
}
