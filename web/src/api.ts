export type JobStatus = 'pending' | 'running' | 'completed' | 'failed'

export type Job = {
  id: string
  source_url: string
  status: JobStatus
  progress: number
  title?: string | null
  output_dir?: string | null
  metadata_path?: string | null
  description_path?: string | null
  file_manifest: string[]
  error?: string | null
  telegram_chat_id?: number | null
  watched: boolean
  starred: boolean
  created_at: string
  updated_at: string
}

const normalizeBase = () => {
  const raw = import.meta.env.VITE_API_BASE_URL ?? ''
  return raw.endsWith('/') ? raw.slice(0, -1) : raw
}

export const API_BASE = normalizeBase()

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || `Request failed with status ${response.status}`)
  }
  return response.json()
}

export async function listJobs(): Promise<Job[]> {
  return request<Job[]>('/jobs/')
}

export async function createJob(url: string, telegramChatId?: number): Promise<Job> {
  return request<Job>('/jobs/', {
    method: 'POST',
    body: JSON.stringify({ url, telegram_chat_id: telegramChatId }),
  })
}

export type RemovedJob = {
  id: string
  source_url: string
}

export async function deleteJob(id: string): Promise<RemovedJob> {
  return request<RemovedJob>(`/jobs/${id}`, { method: 'DELETE' })
}

export function buildDownloadUrl(relativePath: string): string {
  const trimmed = relativePath.replace(/^\/+/, '')
  return `${API_BASE}/downloads/${trimmed}`
}

export type JobUpdateFlags = {
  watched?: boolean
  starred?: boolean
}

export async function updateJobFlags(id: string, flags: JobUpdateFlags): Promise<Job> {
  return request<Job>(`/jobs/${id}/flags`, {
    method: 'PATCH',
    body: JSON.stringify(flags),
  })
}
