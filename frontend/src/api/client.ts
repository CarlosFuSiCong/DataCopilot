import type { UploadResponse, DatasetProfile, ChatRequest, ChatResponse, ConfirmRequest, ConfirmResponse, ApiError } from '../types'

const BASE = '/api'

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText })) as ApiError
    throw new Error(body.error ?? res.statusText)
  }
  return res.json() as Promise<T>
}

interface RawUploadResponse {
  dataset_id: string
  profile: DatasetProfile
}

export async function uploadDataset(file: File): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/datasets/upload`, { method: 'POST', body: form })
  // Backend returns { dataset_id, profile: { filename, row_count, ... } }
  // Flatten to { dataset_id, filename, row_count, ... } for component convenience
  const raw = await handleResponse<RawUploadResponse>(res)
  return { dataset_id: raw.dataset_id, ...raw.profile }
}

export async function sendChat(req: ChatRequest): Promise<ChatResponse> {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  return handleResponse<ChatResponse>(res)
}

export async function confirmWorkflow(req: ConfirmRequest): Promise<ConfirmResponse> {
  const res = await fetch(`${BASE}/workflows/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  return handleResponse<ConfirmResponse>(res)
}
