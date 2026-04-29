import type { ChatResponse } from './index'

export interface NotebookCellData {
  id: string
  query: string
  status: 'loading' | 'ok' | 'error'
  result?: ChatResponse
  error?: string
}
