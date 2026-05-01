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

export interface StepIssue {
  severity: 'warning' | 'error'
  code: string
  message: string
}

export interface StepResult {
  step_index: number
  step_type: string
  status: 'success' | 'warning' | 'error'
  issues: StepIssue[]
  input_row_count: number
  output_row_count: number
  input_column_count: number
  output_column_count: number
  match_rate: number | null
  affected_rate: number | null
  preview: Record<string, unknown>[]
  message: string
}

export interface ExecutionResult {
  row_count: number
  column_count: number
  columns: string[]
  preview: Record<string, unknown>[]
  step_results: StepResult[]
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
  auto_confirm?: boolean
}

export interface ChatResponse {
  query: string
  planned_steps: WorkflowStep[]
  step_results: StepResult[]
  has_warnings: boolean
  has_errors: boolean
  rag_context: RAGContext
  // Null when execution_result is not yet available (preview-only mode).
  // The client should show a Confirm button and call POST /api/workflows/confirm.
  explanation: string | null
  execution_result: ExecutionResult | null
}

export interface ConfirmRequest {
  dataset_id: string
  steps: WorkflowStep[]
  query: string
}

export interface ConfirmResponse {
  query: string
  planned_steps: WorkflowStep[]
  execution_result: ExecutionResult
  explanation: string
}

// ─── API errors ───────────────────────────────────────────────────────────────

export interface ApiError {
  error: string
  detail?: string
}
