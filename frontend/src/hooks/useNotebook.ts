import { useState } from 'react'
import type { UploadResponse } from '../types'
import type { NotebookCellData } from '../types/notebook'
import { sendChat, confirmWorkflow } from '../api/client'

let _seq = 0
function nextId() { return `cell-${++_seq}` }

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

    try {
      const result = await sendChat({ dataset_id: dataset.dataset_id, query })
      if (result.execution_result !== null) {
        appendCell({ id, query, status: 'ok', result })
      } else {
        appendCell({ id, query, status: 'preview', result })
      }
    } catch (err) {
      appendCell({ id, query, status: 'error', error: err instanceof Error ? err.message : 'Unknown error' })
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
      appendCell({
        ...cell,
        status: 'error',
        error: err instanceof Error ? err.message : 'Confirm failed',
      })
    }
  }

  const isLoading = cells.some(c => c.status === 'loading')

  return { cells, isLoading, handleSubmit, handleConfirm }
}
