import { useState } from 'react'
import type { UploadResponse } from '../types'
import type { NotebookCellData } from '../types/notebook'
import { ApiCallError, sendChat, confirmWorkflow } from '../api/client'

let _seq = 0
function nextId() { return `cell-${++_seq}` }

function errorCell(base: Pick<NotebookCellData, 'id' | 'query'>, err: unknown): NotebookCellData {
  if (err instanceof ApiCallError) {
    return {
      ...base,
      status: 'error',
      error: err.message,
      errorCode: err.errorCode,
      errorContext: err.errorContext,
    }
  }
  return {
    ...base,
    status: 'error',
    error: err instanceof Error ? err.message : 'Unknown error',
  }
}

export function useNotebook(dataset: UploadResponse | null) {
  const [cells, setCells] = useState<NotebookCellData[]>([])

  function appendCell(cell: NotebookCellData) {
    setCells(prev => {
      if (cell.status !== 'loading') {
        const idx = [...prev].reverse().findIndex(c => c.id === cell.id)
        if (idx !== -1) {
          const realIdx = prev.length - 1 - idx
          const next = [...prev]
          next[realIdx] = cell
          return next
        }
      }
      return [...prev, cell]
    })
  }

  async function handleSubmit(query: string) {
    if (!dataset || !query.trim()) return

    const id = nextId()
    appendCell({ id, query, status: 'loading' })

    // Chain from the last successfully executed cell so follow-up queries
    // operate on the prior result rather than the original dataset.
    const lastOkCell = [...cells].reverse().find(c => c.status === 'ok')
    const previousSteps =
      lastOkCell?.confirmResult?.planned_steps ??
      lastOkCell?.result?.planned_steps ??
      []

    try {
      const result = await sendChat({
        dataset_id: dataset.dataset_id,
        query,
        previous_steps: previousSteps.length > 0 ? previousSteps : undefined,
      })
      if (result.execution_result !== null) {
        appendCell({ id, query, status: 'ok', result })
      } else {
        appendCell({ id, query, status: 'preview', result })
      }
    } catch (err) {
      appendCell(errorCell({ id, query }, err))
    }
  }

  async function handleConfirm(cell: NotebookCellData) {
    if (!dataset || !cell.result) return

    appendCell({ ...cell, status: 'confirming' })

    try {
      const confirmResult = await confirmWorkflow({
        dataset_id: dataset.dataset_id,
        steps: cell.result.planned_steps,
        query: cell.result.query,
      })
      appendCell({ ...cell, status: 'ok', confirmResult })
    } catch (err) {
      appendCell(errorCell({ id: cell.id, query: cell.query }, err))
    }
  }

  const isLoading = cells.some(c => c.status === 'loading')

  return { cells, isLoading, handleSubmit, handleConfirm }
}
