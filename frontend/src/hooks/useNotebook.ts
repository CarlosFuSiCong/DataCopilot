import { useEffect, useRef, useState } from 'react'
import type { UploadResponse, WorkflowStep } from '../types'
import type { NotebookCellData } from '../types/notebook'
import { ApiCallError, sendChat, confirmWorkflow, rerunWorkflow, previewWorkflow } from '../api/client'

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

// Extract previous steps from the last confirmed ok cell for workflow chaining.
function getPreviousSteps(cells: NotebookCellData[]) {
  const lastOkCell = [...cells].reverse().find(c => c.status === 'ok')
  return (
    lastOkCell?.confirmResult?.planned_steps ??
    lastOkCell?.result?.planned_steps ??
    []
  )
}

export function useNotebook(dataset: UploadResponse | null) {
  const [cells, setCells] = useState<NotebookCellData[]>([])
  // Ref always holds the latest cells so async functions never read stale closure state.
  const cellsRef = useRef<NotebookCellData[]>(cells)
  useEffect(() => {
    cellsRef.current = cells
  }, [cells])

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

    // Read latest cells via ref before any appendCell calls so we never see
    // stale closure state caused by pending React state updates.
    const previousSteps = getPreviousSteps(cellsRef.current)

    const id = nextId()
    appendCell({ id, query, status: 'loading' })

    try {
      const result = await sendChat({
        dataset_id: dataset.dataset_id,
        query,
        previous_steps: previousSteps.length > 0 ? previousSteps : undefined,
      })
      if (result.needs_clarification) {
        appendCell({ id, query, status: 'clarifying', clarificationQuestion: result.clarification_question ?? '' })
      } else if (result.execution_result !== null) {
        appendCell({ id, query, status: 'ok', result })
      } else {
        appendCell({ id, query, status: 'preview', result })
      }
    } catch (err) {
      appendCell(errorCell({ id, query }, err))
    }
  }

  async function handleClarify(cell: NotebookCellData, answer: string) {
    if (!dataset || !cell.clarificationQuestion) return

    // Read latest cells via ref before any appendCell calls.
    const previousSteps = getPreviousSteps(cellsRef.current)

    // Freeze the clarifying cell to show the submitted answer.
    appendCell({ ...cell, clarificationAnswer: answer })

    const id = nextId()
    appendCell({ id, query: cell.query, status: 'loading' })

    try {
      const result = await sendChat({
        dataset_id: dataset.dataset_id,
        query: cell.query,
        clarification_context: answer,
        previous_steps: previousSteps.length > 0 ? previousSteps : undefined,
      })
      if (result.needs_clarification) {
        // Another round of clarification needed.
        appendCell({ id, query: cell.query, status: 'clarifying', clarificationQuestion: result.clarification_question ?? '' })
      } else if (result.execution_result !== null) {
        appendCell({ id, query: cell.query, status: 'ok', result })
      } else {
        appendCell({ id, query: cell.query, status: 'preview', result })
      }
    } catch (err) {
      appendCell(errorCell({ id, query: cell.query }, err))
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
        parent_run_id: cell.parentRunId ?? undefined,
      })
      appendCell({ ...cell, status: 'ok', confirmResult })
    } catch (err) {
      appendCell(errorCell({ id: cell.id, query: cell.query }, err))
    }
  }

  // Rerun a workflow with (possibly edited) steps — always goes through
  // preview first; user must still confirm before results are persisted.
  async function handleRerun(steps: WorkflowStep[], query: string, runId?: string | null) {
    if (!dataset) return

    const id = nextId()
    appendCell({ id, query, status: 'loading' })

    try {
      const preview = runId
        ? await rerunWorkflow(runId, dataset.dataset_id, steps, query)
        : await previewWorkflow(dataset.dataset_id, steps)

      const syntheticResult = {
        query,
        planned_steps: steps,
        step_results: preview.step_results,
        has_warnings: preview.has_warnings,
        has_errors: preview.has_errors,
        rag_context: null,
        explanation: null,
        execution_result: null,
        run_id: null,
        needs_clarification: false,
      }

      appendCell({ id, query, status: 'preview', result: syntheticResult, parentRunId: runId ?? null })
    } catch (err) {
      appendCell(errorCell({ id, query }, err))
    }
  }

  const isLoading = cells.some(c => c.status === 'loading')

  return { cells, isLoading, handleSubmit, handleConfirm, handleClarify, handleRerun }
}
