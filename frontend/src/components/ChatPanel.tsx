import type { UploadResponse } from '../types'
import type { NotebookCellData } from '../types/notebook'
import { Notebook } from './Notebook'

interface ChatPanelProps {
  dataset: UploadResponse | null
  cells: NotebookCellData[]
  isLoading: boolean
  onSubmit: (query: string) => void
  onConfirm: (cell: NotebookCellData) => void
  onClarify: (cell: NotebookCellData, answer: string) => void
  onSuggest: (query: string) => void
  suggestedQuery?: string
  onSuggestedQueryConsumed?: () => void
  width: number
}

export function ChatPanel({ dataset, cells, isLoading, onSubmit, onConfirm, onClarify, onSuggest, suggestedQuery, onSuggestedQueryConsumed, width }: ChatPanelProps) {
  return (
    <div className="flex flex-col shrink-0 overflow-hidden" style={{ width }}>
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
          className="flex items-center gap-2 px-3 h-full"
          style={{
            borderRight: '1px solid var(--color-border)',
            borderBottom: '2px solid var(--color-accent)',
            background: 'var(--color-surface-1)',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.82rem',
            color: 'var(--color-accent)',
          }}
        >
          <span style={{ fontSize: '0.75rem' }}>◉</span>
          <span>Chat</span>
        </div>
        {dataset && (
          <span
            style={{
              marginLeft: 'auto',
              paddingRight: 12,
              fontFamily: 'var(--font-mono)',
              fontSize: '0.72rem',
              color: 'var(--color-text-muted)',
            }}
          >
            {dataset.filename} · {dataset.row_count.toLocaleString()} rows
          </span>
        )}
      </div>

      {/* Chat area */}
      <Notebook
        cells={cells}
        isLoading={isLoading}
        dataset={dataset}
        onSubmit={onSubmit}
        onConfirm={onConfirm}
        onClarify={onClarify}
        onSuggest={onSuggest}
        suggestedQuery={suggestedQuery}
        onSuggestedQueryConsumed={onSuggestedQueryConsumed}
      />
    </div>
  )
}
