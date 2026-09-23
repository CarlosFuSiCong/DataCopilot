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

export type WorkflowRunState =
  | 'draft'
  | 'needs_clarification'
  | 'planned'
  | 'validation_failed'
  | 'repair_attempted'
  | 'preview_ready'
  | 'warning_review'
  | 'confirmed'
  | 'executed'
  | 'failed'

export interface AttemptSummary {
  attempt_index: number
  query: string
  retrieval_method?: string | null
  retrieved_docs: string[]
  planner_raw_output?: string | null
  parsed_step_types: string[]
  validation_status: 'not_run' | 'passed' | 'failed'
  preview_status: 'not_run' | 'passed' | 'warning' | 'error'
  warning_count: number
  error_count: number
  repair_reason?: string | null
  final_status: WorkflowRunState
}

export interface WorkflowAttempt {
  attempt_index: number
  query: string
  retrieval_method?: string | null
  retrieved_docs: Record<string, unknown>[]
  planner_raw_output?: string | null
  parsed_steps: WorkflowStep[]
  validation_result?: Record<string, unknown> | null
  repair_reason?: string | null
  final_status: WorkflowRunState
  summary: AttemptSummary
}

export interface WorkflowContextSummary {
  query: string
  dataset_hash: string
  schema_columns: string[]
  row_count: number
  retrieved_docs: string[]
  planned_step_types: string[]
  status: WorkflowRunState
  boundary: string
  validation_status?: string | null
  warning_count: number
  error_count: number
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

// ─── Observation ─────────────────────────────────────────────────────────────

export type CandidateFixAction = 'suggest_query' | 'inspect_column' | 'back_to_preview' | 'relax_filter'

export interface CandidateFix {
  id: string
  label: string
  description: string
  action_type: CandidateFixAction
  query?: string | null
}

export interface ObservationSummary {
  status: 'not_observed' | 'ok' | 'warning' | 'error'
  signals: string[]
  message?: string | null
  diagnostic_explanation?: string | null
  possible_causes: string[]
  candidate_fixes: CandidateFix[]
  recommended_next_action?: string | null
  workflow_state?: string | null
}

// ─── Chat ─────────────────────────────────────────────────────────────────────

export interface ChatRequest {
  dataset_id: string
  query: string
  mode_hint?: QueryModeHint
  auto_confirm?: boolean
  // Steps from the last confirmed workflow. When present the new query chains
  // onto the prior result instead of starting from the raw dataset.
  previous_steps?: WorkflowStep[]
  // User's answer to a clarification question, merged into the planner query.
  clarification_context?: string | ClarificationContext
}

export type QueryModeHint = 'auto' | 'ask' | 'analysis' | 'workflow'

export interface ClarificationContext {
  dataset_id: string
  original_query: string
  question?: string | null
  user_answer?: string | null
  resolved_parameter?: string | null
  affected_step?: WorkflowStep | null
  status: 'pending' | 'resolved'
  scope_key: string
  clarification_type?: string | null
  choices?: ClarificationChoice[] | null
}

export interface ClarificationChoice {
  id: string
  label: string
  description: string
  query: string
  tool?: string | null
}

export interface PreviewResponse {
  step_results: StepResult[]
  has_warnings: boolean
  has_errors: boolean
  blocked_at_step: number | null
}

export interface ChatResponse {
  query: string
  planned_steps: WorkflowStep[]
  step_results: StepResult[]
  has_warnings: boolean
  has_errors: boolean
  // Optional: absent when the result comes from a rerun preview (no RAG context).
  rag_context?: RAGContext | null
  // Null when execution_result is not yet available (preview-only mode).
  // The client should show a Confirm button and call POST /api/workflows/confirm.
  explanation: string | null
  execution_result: ExecutionResult | null
  // UUID for the persisted run; used to download the result via GET /api/runs/{id}/download.
  run_id?: string | null
  // True when the planner needs clarification before producing a workflow.
  needs_clarification?: boolean
  clarification_question?: string | null
  clarification_type?: 'slot_validation' | 'planning' | string | null
  clarification_context?: ClarificationContext | null
  // Suggested analysis directions for broad / ambiguous requests (rendered as buttons).
  clarification_choices?: ClarificationChoice[] | null
  state?: WorkflowRunState
  attempts?: WorkflowAttempt[]
  context_summary?: WorkflowContextSummary | null
  // Read-only analytical result fields (task 3).
  is_read_only?: boolean
  ask_mode_type?: string | null
  evidence_source?: string | null
  // Route decision debug info from the query classifier (task 5).
  route_decision?: Record<string, unknown> | null
  // Structured observation from the preview pass (task 6).
  observation?: ObservationSummary | null
}

// ─── Run history ──────────────────────────────────────────────────────────────

export interface RunRecord {
  run_id: string
  dataset_id: string
  query: string | null
  status: string
  step_count: number | null
  row_count: number | null
  created_at: string
  parent_run_id: string | null
  explanation?: string | null
  planned_steps?: WorkflowStep[] | null
  state?: WorkflowRunState | null
  attempts?: WorkflowAttempt[] | null
  context_summary?: WorkflowContextSummary | null
}

export interface ConfirmRequest {
  dataset_id: string
  steps: WorkflowStep[]
  query: string
  // Populated when confirming after a rerun so the backend can record lineage.
  parent_run_id?: string | null
}

export interface ConfirmResponse {
  query: string
  planned_steps: WorkflowStep[]
  execution_result: ExecutionResult
  explanation: string
  run_id?: string | null
  state?: WorkflowRunState
  attempts?: WorkflowAttempt[]
  context_summary?: WorkflowContextSummary | null
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
  // Specific hint from the planner (e.g. column not found + did-you-mean suggestion).
  planner_hint?: string | null
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
