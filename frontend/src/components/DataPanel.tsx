import type { UploadResponse } from '../types'
import { DataPreview } from './DataPreview'
import { NotebookIcon } from './ui/Icons'

interface DataPanelProps {
  dataset: UploadResponse | null
  width: number
}

export function DataPanel({ dataset, width }: DataPanelProps) {
  const tabLabel = dataset?.filename ?? 'data.csv'

  return (
    <div
      className="flex flex-col overflow-hidden shrink-0"
      style={{
        width,
        borderRight: '1px solid var(--color-border)',
        background: 'var(--color-bg)',
      }}
    >
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
            borderBottom: '2px solid var(--color-blue)',
            background: 'var(--color-surface-1)',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.82rem',
            color: 'var(--color-blue)',
          }}
        >
          <span style={{ fontSize: '0.78rem' }}>⊞</span>
          <span className="truncate" style={{ maxWidth: 160 }}>{tabLabel}</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {dataset ? (
          <DataPreview dataset={dataset} />
        ) : (
          <DataPanelEmpty />
        )}
      </div>
    </div>
  )
}

function DataPanelEmpty() {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 h-full"
      style={{ color: 'var(--color-text-muted)', padding: 32 }}
    >
      <NotebookIcon size={36} />
      <p style={{
        margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.82rem',
        textAlign: 'center', lineHeight: 1.8,
      }}>
        Upload a CSV file<br />to preview the data here.
      </p>
    </div>
  )
}
