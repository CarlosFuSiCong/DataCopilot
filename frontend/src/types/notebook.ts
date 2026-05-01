import type { ChatResponse, ConfirmResponse } from './index'

export interface NotebookCellData {
  id: string
  query: string
  status: 'loading' | 'preview' | 'confirming' | 'ok' | 'error'
  result?: ChatResponse
  confirmResult?: ConfirmResponse
  error?: string
}
