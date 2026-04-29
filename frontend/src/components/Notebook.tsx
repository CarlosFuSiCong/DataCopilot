import { useState } from 'react'
import type { UploadResponse } from '../types'
import type { NotebookCellData } from '../types/notebook'
import { sendChat } from '../api/client'

let _seq = 0
function nextId() { return `cell-${++_seq}` }
import { NotebookIcon, Spinner } from './ui/Icons'
import { Gutter, OutputBlock } from './ui/OutputBlock'
import { WorkflowViewer } from './WorkflowViewer'
import { ResultTable } from './ResultTable'
import { ExplanationPanel } from './ExplanationPanel'
import { DataPreview } from './DataPreview'

// ─── Notebook container ───────────────────────────────────────────────────────

interface NotebookProps {
  cells: NotebookCellData[]
  onAppendCell: (cell: NotebookCellData) => void
  dataset: UploadResponse | null
}

export function Notebook({ cells, onAppendCell, dataset }: NotebookProps) {
  async function handleSubmit(query: string) {
    if (!dataset || !query.trim()) return

    const id = nextId()
    onAppendCell({ id, query, status: 'loading' })

    try {
      const result = await sendChat({ dataset_id: dataset.dataset_id, query })
      onAppendCell({ id, query, status: 'ok', result })
    } catch (err) {
      onAppendCell({ id, query, status: 'error', error: err instanceof Error ? err.message : 'Unknown error' })
    }
  }

  const displayCells = cells.filter(c => c.status !== 'loading')
  const isLoading = cells.some(c => c.status === 'loading')

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Tab bar */}
      <div
        className="flex items-center shrink-0"
        style={{ background: 'var(--color-surface)', borderBottom: '1px solid var(--color-border)', height: 36, paddingLeft: 8 }}
      >
        <div
          className="flex items-center gap-1.5 px-3 h-full"
          style={{
            borderRight: '1px solid var(--color-border)',
            borderBottom: '2px solid var(--color-accent)',
            background: 'var(--color-surface-1)',
            fontFamily: 'var(--font-mono)', fontSize: '0.82rem',
            color: 'var(--color-accent)',
          }}
        >
          <NotebookIcon size={11} />
          <span>notebook.dc</span>
        </div>
      </div>

      {/* Toolbar */}
      <div
        className="flex items-center gap-2 px-4 shrink-0"
        style={{ height: 34, background: 'var(--color-surface-1)', borderBottom: '1px solid var(--color-border-subtle)' }}
      >
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
          {displayCells.length} cell{displayCells.length !== 1 ? 's' : ''}
        </span>
        <div className="flex-1" />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
          {dataset ? `${dataset.filename} · ${dataset.row_count.toLocaleString()} rows` : 'no dataset'}
        </span>
      </div>

      {/* Cell scroll area */}
      <div className="flex-1 overflow-y-auto" style={{ background: 'var(--color-bg)' }}>
        {/* No dataset: show empty hint */}
        {!dataset && displayCells.length === 0 && !isLoading && (
          <EmptyNotebook />
        )}

        {/* Dataset loaded, no cells yet: show data preview */}
        {dataset && displayCells.length === 0 && !isLoading && (
          <DataPreview dataset={dataset} />
        )}

        {/* Result cells */}
        {displayCells.length > 0 && (
          <div style={{ padding: '16px 0' }}>
            {displayCells.map((cell, i) => (
              <NotebookCell key={cell.id} index={i + 1} cell={cell} />
            ))}
          </div>
        )}

        {isLoading && (
          <div style={{ padding: displayCells.length === 0 ? '16px 0' : '0' }}>
            <LoadingCell index={displayCells.length + 1} />
          </div>
        )}

        <div style={{ padding: '0 0 16px' }}>
          <InputCell disabled={!dataset || isLoading} onSubmit={handleSubmit} />
        </div>
      </div>
    </div>
  )
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyNotebook() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20" style={{ color: 'var(--color-text-muted)' }}>
      <NotebookIcon size={32} />
      <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.85rem', textAlign: 'center', lineHeight: 1.8 }}>
        Upload a CSV, then type a query below.<br />
        Each exchange becomes a notebook cell.
      </p>
    </div>
  )
}

// ─── Loading cell ─────────────────────────────────────────────────────────────

function LoadingCell({ index }: { index: number }) {
  return (
    <div className="flex" style={{ padding: '4px 0' }}>
      <Gutter label={`In [${index}]:`} color="var(--color-blue)" />
      <div
        className="flex-1 mr-4 flex items-center gap-2 rounded px-3 py-2"
        style={{ background: 'var(--color-cell-in)', border: '1px solid var(--color-border)' }}
      >
        <Spinner />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
          Running pipeline…
        </span>
      </div>
    </div>
  )
}

// ─── Input cell ───────────────────────────────────────────────────────────────

function InputCell({ disabled, onSubmit }: { disabled: boolean; onSubmit: (q: string) => void }) {
  const [query, setQuery] = useState('')

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (query.trim()) {
        onSubmit(query.trim())
        setQuery('')
      }
    }
  }

  return (
    <div className="flex" style={{ padding: '4px 0', marginTop: 8 }}>
      <Gutter label="In [ ]:" color={disabled ? 'var(--color-text-muted)' : 'var(--color-blue)'} />
      <div
        className="flex-1 mr-4 rounded"
        style={{
          background: 'var(--color-cell-in)',
          border: `1px solid ${disabled ? 'var(--color-border-subtle)' : 'var(--color-blue)'}`,
          opacity: disabled ? 0.45 : 1,
        }}
      >
        <textarea
          disabled={disabled}
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
          placeholder={disabled ? 'Upload a dataset to start…' : 'Enter a query… (Enter to run, Shift+Enter for new line)'}
          style={{
            width: '100%', background: 'transparent', border: 'none', outline: 'none',
            resize: 'none', padding: '10px 12px',
            fontFamily: 'var(--font-mono)', fontSize: '0.9rem',
            color: 'var(--color-text)', lineHeight: 1.6,
          }}
        />
      </div>
    </div>
  )
}

// ─── Result cell ──────────────────────────────────────────────────────────────

function NotebookCell({ index, cell }: { index: number; cell: NotebookCellData }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div className="flex" style={{ padding: '2px 0' }}>
        <Gutter label={`In [${index}]:`} color="var(--color-blue)" />
        <div
          className="flex-1 mr-4 rounded px-3 py-2"
          style={{ background: 'var(--color-cell-in)', border: '1px solid var(--color-border)', fontFamily: 'var(--font-mono)', fontSize: '0.9rem', color: 'var(--color-text)' }}
        >
          {cell.query}
        </div>
      </div>

      <div className="flex" style={{ padding: '2px 0' }}>
        <Gutter label={`Out[${index}]:`} color={cell.status === 'error' ? 'var(--color-red)' : 'var(--color-accent)'} />
        <div className="flex-1 mr-4 flex flex-col gap-2">
          {cell.status === 'error' && (
            <OutputBlock label="error" accent="var(--color-red)">
              <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.85rem', color: 'var(--color-red)' }}>
                {cell.error}
              </p>
            </OutputBlock>
          )}

          {cell.status === 'ok' && cell.result && (
            <>
              <WorkflowViewer steps={cell.result.planned_steps} />
              <ResultTable
                columns={cell.result.execution_result.columns}
                rows={cell.result.execution_result.preview}
                rowCount={cell.result.execution_result.row_count}
                logs={cell.result.execution_result.logs}
              />
              <ExplanationPanel text={cell.result.explanation} />
            </>
          )}
        </div>
      </div>
    </div>
  )
}
