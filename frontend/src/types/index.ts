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
  state?: WorkflowRunState
  attempts?: WorkflowAttempt[]
  context_summary?: WorkflowContextSummary | null
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

// ─── Agent Trace ──────────────────────────────────────────────────────────────

export type AgentRunState =
  | 'created'
  | 'running'
  | 'needs_clarification'
  | 'waiting_confirmation'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'max_iterations_reached'

export type AgentActionType =
  | 'clarify'
  | 'plan_workflow'
  | 'preview_workflow'
  | 'confirm_required'
  | 'retry_preview'
  | 'replan_workflow'
  | 'select_new_tool'
  | 'stop_with_result'
  | 'stop_with_error'

export interface AgentDecision {
  decision: AgentActionType
  rationale: string
  confidence: number | null
  requires_user_input: boolean
}

export interface AgentAction {
  type: AgentActionType
  parameters: Record<string, unknown>
  workflow_steps: WorkflowStep[]
}

export interface AgentValidationSummary {
  status: 'not_run' | 'passed' | 'failed' | 'blocked'
  error?: string | null
  details: Record<string, unknown>
}

export interface ObservationSummary {
  status: 'ok' | 'warning' | 'error' | 'blocked'
  message: string
  recommended_next_action?: string | null
}

export interface AgentIteration {
  iteration_index: number
  input: Record<string, unknown>
  decision: AgentDecision
  action: AgentAction
  validation: AgentValidationSummary
  observation: ObservationSummary
  stop_reason: string | null
}

export interface AgentTraceSummary {
  state: AgentRunState
  iteration_count: number
  max_iterations: number
  stop_reason: string | null
  last_action: AgentActionType | null
  last_observation: ObservationSummary | null
  workflow_context_summary: WorkflowContextSummary | null
  full_trace_available: boolean
}

export interface AgentTrace {
  state: AgentRunState
  max_iterations: number
  summary: AgentTraceSummary
  iterations: AgentIteration[]
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
