import type { ApiErrorContext, ChatResponse, ClarificationContext, ConfirmResponse } from './index'

export interface NotebookCellData {
  id: string
  query: string
  status: 'loading' | 'preview' | 'confirming' | 'ok' | 'error' | 'clarifying'
  result?: ChatResponse
  confirmResult?: ConfirmResponse
  error?: string
  // Machine-readable error code from the backend for structured error UI.
  errorCode?: string
  errorContext?: ApiErrorContext
  // Clarification flow: question from the planner, answer from the user.
  clarificationQuestion?: string
  clarificationAnswer?: string
  clarificationContext?: ClarificationContext | null
  // Set when this cell was created by a rerun so the confirm call can
  // write parent_run_id into the new run record.
  parentRunId?: string | null
}
