import type { UploadResponse } from '../types'
import type { NotebookCellData } from '../types/notebook'
import { NotebookIcon } from './ui/Icons'
import { Notebook } from './Notebook'

interface ChatPanelProps {
  dataset: UploadResponse | null
  cells: NotebookCellData[]
  isLoading: boolean
  onSubmit: (query: string) => void
  onConfirm: (cell: NotebookCellData) => void
}

export function ChatPanel({ dataset, cells, isLoading, onSubmit, onConfirm }: ChatPanelProps) {
  const displayCells = cells.filter(c => c.status !== 'loading')

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Tab bar */}
      <div
        className="flex items-center shrink-0"
        style={{
          height: 36,
          background: 'var(--color-surface)',
          borderBottom: '1px solid var(--color-border)',
          paddingLeft: 8,
        }}
      >
        <div
          className="flex items-center gap-1.5 px-3 h-full"
          style={{
            borderRight: '1px solid var(--color-border)',
            borderBottom: '2px solid var(--color-accent)',
            background: 'var(--color-surface-1)',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.82rem',
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
        style={{
          height: 34,
          background: 'var(--color-surface-1)',
          borderBottom: '1px solid var(--color-border-subtle)',
        }}
      >
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
          {displayCells.length} cell{displayCells.length !== 1 ? 's' : ''}
        </span>
        <div className="flex-1" />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
          {dataset ? `${dataset.filename} · ${dataset.row_count.toLocaleString()} rows` : 'no dataset'}
        </span>
      </div>

      {/* Cell area */}
      <Notebook
        cells={cells}
        isLoading={isLoading}
        dataset={dataset}
        onSubmit={onSubmit}
        onConfirm={onConfirm}
      />
    </div>
  )
}
