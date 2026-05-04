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

export interface DatasetRowsResponse {
  rows: Record<string, unknown>[]
  total_rows: number
  offset: number
  limit: number
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
  affected_rows: number
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
  // Steps from the last confirmed workflow. When present the new query chains
  // onto the prior result instead of starting from the raw dataset.
  previous_steps?: WorkflowStep[]
  // User's answer to a clarification question, merged into the planner query.
  clarification_context?: string
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
  // UUID for the persisted run; used to download the result via GET /api/runs/{id}/download.
  run_id?: string | null
  // True when the planner needs clarification before producing a workflow.
  needs_clarification?: boolean
  clarification_question?: string | null
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
  run_id?: string | null
}

// ─── API errors ───────────────────────────────────────────────────────────────

export interface ApiError {
  error: string
  detail?: string
  error_code?: string
  context?: ApiErrorContext
}

export interface RelevantStepHint {
  step_type: string
  description: string
  example: Record<string, unknown>
}

export interface ApiErrorContext {
  available_columns?: string[]
  // RAG-retrieved operations relevant to this specific query (preferred over supported_steps).
  relevant_steps?: RelevantStepHint[]
  // Generic fallback when RAG returned nothing useful.
  supported_steps?: string[]
  example_queries?: string[]
  failed_step_index?: number
  failed_step_type?: string
  suggestion?: string
  retrieval_method?: string
  query?: string
  size_bytes?: number
  limit_bytes?: number
}
