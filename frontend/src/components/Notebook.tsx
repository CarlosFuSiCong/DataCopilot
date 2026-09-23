import { useEffect, useRef } from 'react'
import type { QueryModeHint, UploadResponse, WorkflowStep } from '../types'
import type { NotebookCellData } from '../types/notebook'
import { NotebookIcon } from './ui/Icons'
import { NotebookCell } from './NotebookCell'
import { InputCell } from './InputCell'
import { DemoGuidePanel } from './DemoGuidePanel'

interface NotebookProps {
  cells: NotebookCellData[]
  isLoading: boolean
  dataset: UploadResponse | null
  onSubmit: (query: string, modeHint?: QueryModeHint) => void
  onConfirm: (cell: NotebookCellData) => void
  onClarify: (cell: NotebookCellData, answer: string) => void
  onSuggest: (query: string) => void
  onRerun: (steps: WorkflowStep[], query: string, runId?: string | null) => void
  suggestedQuery?: string
  onSuggestedQueryConsumed?: () => void
}

export function Notebook({ cells, dataset, onSubmit, onConfirm, onClarify, onSuggest, onRerun, suggestedQuery, onSuggestedQueryConsumed }: NotebookProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const lastCellStatus = cells.at(-1)?.status

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [cells.length, lastCellStatus])

  const isEmpty = cells.length === 0

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
        background: 'var(--color-bg)',
      }}
    >
      {/* Message list */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: isEmpty ? 0 : '16px 0 8px',
        }}
      >
        {/* Empty: no dataset */}
        {!dataset && isEmpty && <NotebookEmpty />}

        {/* Empty: dataset loaded, no messages */}
        {dataset && isEmpty && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              gap: 8,
              color: 'var(--color-text-muted)',
            }}
          >
            <span style={{ color: 'var(--color-accent)', fontSize: '1.2rem' }}>◉</span>
            <p
              style={{
                margin: 0,
                fontFamily: 'var(--font-mono)',
                fontSize: '0.82rem',
                textAlign: 'center',
                lineHeight: 1.8,
                color: 'var(--color-text-muted)',
              }}
            >
              Dataset ready. Ask a question about your data.
            </p>
          </div>
        )}

        {/* All cells, including loading ones */}
        {cells.map(cell => (
          <NotebookCell key={cell.id} cell={cell} onConfirm={onConfirm} onClarify={onClarify} onSuggest={onSuggest} onRerun={onRerun} />
        ))}

        <div ref={bottomRef} style={{ height: 4 }} />
      </div>

      {dataset && <DemoGuidePanel onSuggest={onSuggest} />}

      {/* Chat input bar — always at the bottom */}
      <InputCell
        disabled={!dataset || cells.some(c => c.status === 'loading' || c.status === 'confirming' || (c.status === 'clarifying' && !c.clarificationAnswer))}
        onSubmit={onSubmit}
        suggestedQuery={suggestedQuery}
        onSuggestedQueryConsumed={onSuggestedQueryConsumed}
      />
    </div>
  )
}

function NotebookEmpty() {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        gap: 12,
        color: 'var(--color-text-muted)',
      }}
    >
      <NotebookIcon size={32} />
      <p
        style={{
          margin: 0,
          fontFamily: 'var(--font-mono)',
          fontSize: '0.85rem',
          textAlign: 'center',
          lineHeight: 1.8,
        }}
      >
        Upload a CSV in the sidebar,<br />then ask a question.
      </p>
    </div>
  )
}
