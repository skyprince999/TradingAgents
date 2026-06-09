import type { TickerResult, AnalyzeRequest, Job, AppConfig } from './types'

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(text)
  }
  return res.json() as Promise<T>
}

export async function searchTickers(q: string): Promise<TickerResult[]> {
  if (!q.trim()) return []
  const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`)
  return json<TickerResult[]>(res)
}

export async function fetchConfig(): Promise<AppConfig> {
  const res = await fetch('/api/config')
  return json<AppConfig>(res)
}

export async function startAnalysis(req: AnalyzeRequest): Promise<{ job_id: string }> {
  const res = await fetch('/api/analyze', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(req),
  })
  return json<{ job_id: string }>(res)
}

export async function getJob(jobId: string): Promise<Job> {
  const res = await fetch(`/api/jobs/${jobId}`)
  return json<Job>(res)
}
