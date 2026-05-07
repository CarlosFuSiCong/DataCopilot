import type { ApiErrorContext, UploadResponse, DatasetProfile, DatasetRowsResponse, ChatRequest, ChatResponse, ConfirmRequest, ConfirmResponse, ApiError, PreviewResponse, RunRecord, WorkflowStep } from '../types'

export interface RunListResponse {
  runs: RunRecord[]
  total: number
}

export interface DiffRowsResponse {
  rows: (Record<string, unknown> & { _kept: boolean })[]
  total_original: number
  total_result: number
  offset: number
  limit: number
}

/** Thrown when the backend returns a non-OK status. Carries the machine-readable
 *  error_code and context from the backend for structured error UI rendering. */
export class ApiCallError extends Error {
  readonly errorCode: string | undefined
  readonly errorContext: ApiErrorContext | undefined

  constructor(message: string, errorCode?: string, errorContext?: ApiErrorContext) {
    super(message)
    this.name = 'ApiCallError'
    this.errorCode = errorCode
    this.errorContext = errorContext
  }
}

const BASE = '/api'

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText })) as ApiError
    throw new ApiCallError(
      body.error ?? res.statusText,
      body.error_code,
      body.context,
    )
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

export async function fetchDatasetRows(
  datasetId: string,
  offset: number,
  limit: number,
): Promise<DatasetRowsResponse> {
  const params = new URLSearchParams({ offset: String(offset), limit: String(limit) })
  const res = await fetch(`${BASE}/datasets/${datasetId}/rows?${params}`)
  return handleResponse<DatasetRowsResponse>(res)
}

export function downloadDataset(datasetId: string): void {
  const a = document.createElement('a')
  a.href = `${BASE}/datasets/${datasetId}/download`
  a.click()
}

export function downloadRun(runId: string): void {
  const a = document.createElement('a')
  a.href = `${BASE}/runs/${runId}/download`
  a.click()
}

export async function exportResultCsv(
  datasetId: string,
  steps: unknown[],
  filename: string,
): Promise<void> {
  const res = await fetch(`${BASE}/datasets/${datasetId}/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ steps, filename }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText })) as ApiError
    throw new ApiCallError(body.error ?? res.statusText, body.error_code, body.context)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const disposition = res.headers.get('Content-Disposition') ?? ''
  const match = disposition.match(/filename="([^"]+)"/)
  a.download = match ? match[1] : 'result.csv'
  a.click()
  URL.revokeObjectURL(url)
}

export async function fetchResultRows(
  datasetId: string,
  steps: unknown[],
  offset: number,
  limit: number,
): Promise<DatasetRowsResponse> {
  const res = await fetch(`${BASE}/datasets/${datasetId}/execute-rows`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ steps, offset, limit }),
  })
  return handleResponse<DatasetRowsResponse>(res)
}

export async function listRuns(datasetId: string, limit = 20): Promise<RunListResponse> {
  const params = new URLSearchParams({ dataset_id: datasetId, limit: String(limit) })
  const res = await fetch(`${BASE}/runs?${params}`)
  return handleResponse<RunListResponse>(res)
}

export async function getRun(runId: string): Promise<RunRecord> {
  const res = await fetch(`${BASE}/runs/${runId}`)
  return handleResponse<RunRecord>(res)
}

export async function rerunWorkflow(
  runId: string,
  datasetId: string,
  steps: WorkflowStep[],
  query?: string,
): Promise<PreviewResponse> {
  const res = await fetch(`${BASE}/runs/${runId}/rerun`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset_id: datasetId, steps, query }),
  })
  return handleResponse<PreviewResponse>(res)
}

export async function previewWorkflow(
  datasetId: string,
  steps: WorkflowStep[],
): Promise<PreviewResponse> {
  const res = await fetch(`${BASE}/workflows/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset_id: datasetId, steps }),
  })
  return handleResponse<PreviewResponse>(res)
}

export async function fetchDiffRows(
  datasetId: string,
  steps: unknown[],
  offset: number,
  limit: number,
): Promise<DiffRowsResponse> {
  const res = await fetch(`${BASE}/datasets/${datasetId}/execute-diff`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ steps, offset, limit }),
  })
  return handleResponse<DiffRowsResponse>(res)
}
