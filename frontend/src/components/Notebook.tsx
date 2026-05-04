import { useEffect, useRef } from 'react'
import type { UploadResponse } from '../types'
import type { NotebookCellData } from '../types/notebook'
import { NotebookIcon, Spinner } from './ui/Icons'
import { Gutter } from './ui/OutputBlock'
import { NotebookCell } from './NotebookCell'
import { InputCell } from './InputCell'

interface NotebookProps {
  cells: NotebookCellData[]
  isLoading: boolean
  dataset: UploadResponse | null
  onSubmit: (query: string) => void
  onConfirm: (cell: NotebookCellData) => void
}

export function Notebook({ cells, isLoading, dataset, onSubmit, onConfirm }: NotebookProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const displayCells = cells.filter(c => c.status !== 'loading')

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [cells.length, cells.at(-1)?.status])

  return (
    <div className="flex-1 overflow-y-auto" style={{ background: 'var(--color-bg)' }}>

      {/* Empty states */}
      {!dataset && displayCells.length === 0 && !isLoading && <NotebookEmpty />}

      {dataset && displayCells.length === 0 && !isLoading && (
        <div className="flex flex-col items-center justify-center gap-2 py-20" style={{ color: 'var(--color-text-muted)' }}>
          <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.82rem', textAlign: 'center', lineHeight: 1.8 }}>
            Dataset loaded. Type a query below<br />to start the pipeline.
          </p>
        </div>
      )}

      {/* Cell list */}
      {displayCells.length > 0 && (
        <div style={{ padding: '16px 0' }}>
          {displayCells.map((cell, i) => (
            <NotebookCell key={cell.id} index={i + 1} cell={cell} onConfirm={onConfirm} />
          ))}
        </div>
      )}

      {/* Loading placeholder */}
      {isLoading && (
        <div style={{ padding: displayCells.length === 0 ? '16px 0' : '0' }}>
          <LoadingCell index={displayCells.length + 1} />
        </div>
      )}

      {/* Input */}
      <div style={{ padding: '0 0 16px' }}>
        <InputCell disabled={!dataset || isLoading} onSubmit={onSubmit} />
      </div>

      {/* Scroll anchor */}
      <div ref={bottomRef} style={{ height: 1 }} />
    </div>
  )
}

function NotebookEmpty() {
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
