// ─── Dataset ─────────────────────────────────────────────────────────────────

export interface ColumnProfile {
  name: string
  dtype: string
  missing_count: number
  missing_pct: number
  sample_values?: (string | number | null)[]
}

export interface DatasetProfile {
  filename: string
  row_count: number
  column_count: number
  columns: ColumnProfile[]
  preview: Record<string, unknown>[]
}

export interface UploadResponse {
  dataset_id: string
  filename: string
  row_count: number
  column_count: number
  columns: ColumnProfile[]
  preview: Record<string, unknown>[]
}

// ─── Workflow ─────────────────────────────────────────────────────────────────

export interface WorkflowStep {
  type: string
  [key: string]: unknown
}

export interface StepLog {
  step_index: number
  step_type: string
  rows_before: number
  rows_after: number
  message: string
}

export interface ExecutionResult {
  row_count: number
  column_count: number
  columns: string[]
  preview: Record<string, unknown>[]
  logs: StepLog[]
  has_summary: boolean
  summary?: Record<string, unknown>
}

// ─── RAG ─────────────────────────────────────────────────────────────────────

export interface RetrievedDoc {
  type: string
  description: string
  keywords: string[]
  parameters: Record<string, unknown>[]
  example: Record<string, unknown>
  score: number
}

export interface DatasetSummary {
  filename: string
  row_count: number
  column_count: number
  columns: ColumnProfile[]
}

export interface RetrievalDebug {
  method: string
  query_tokens: string[]
  all_scores: Record<string, number>
}

export interface RAGContext {
  query: string
  retrieved_docs: RetrievedDoc[]
  dataset_summary: DatasetSummary
  debug: RetrievalDebug
}

// ─── Chat ─────────────────────────────────────────────────────────────────────

export interface ChatRequest {
  dataset_id: string
  query: string
}

export interface ChatResponse {
  query: string
  planned_steps: WorkflowStep[]
  execution_result: ExecutionResult
  rag_context: RAGContext
  explanation: string
}

// ─── API errors ───────────────────────────────────────────────────────────────

export interface ApiError {
  error: string
  detail?: string
}
