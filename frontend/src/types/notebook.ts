import type { ApiErrorContext, ChatResponse, ConfirmResponse } from './index'

export interface NotebookCellData {
  id: string
  query: string
  status: 'loading' | 'preview' | 'confirming' | 'ok' | 'error'
  result?: ChatResponse
  confirmResult?: ConfirmResponse
  error?: string
  // Machine-readable error code from the backend for structured error UI.
  errorCode?: string
  errorContext?: ApiErrorContext
}
