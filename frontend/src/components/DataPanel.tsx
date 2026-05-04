import { useEffect, useState } from 'react'
import type { ExecutionResult, UploadResponse, WorkflowStep } from '../types'
import { exportResultCsv } from '../api/client'
import { DataPreview } from './DataPreview'
import { DataPanelEmpty } from './dataPanel/DataPanelEmpty'
import { ResultView } from './dataPanel/ResultView'
import { DataPanelViewToggle, type ViewMode } from './dataPanel/DataPanelViewToggle'
import { formatDatasetDims } from './dataPanel/formatDatasetDims'
import { useCompactPanelDims } from './dataPanel/useCompactPanelDims'

interface DataPanelProps {
  dataset: UploadResponse | null
  lastExecutionResult: ExecutionResult | null
  lastConfirmedSteps: WorkflowStep[] | null
}

export function DataPanel({ dataset, lastExecutionResult, lastConfirmedSteps }: DataPanelProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('original')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  const { panelMeasureRef, viewToggleBarRef, compactDims } = useCompactPanelDims(
    dataset?.dataset_id,
    lastExecutionResult,
  )

  useEffect(() => {
    if (lastExecutionResult) setViewMode('result')
  }, [lastExecutionResult])

  useEffect(() => {
    setViewMode('original')
  }, [dataset?.dataset_id])

  async function handleDownload() {
    if (!dataset || !lastConfirmedSteps) return
    setExporting(true)
    setExportError(null)
    try {
      await exportResultCsv(dataset.dataset_id, lastConfirmedSteps, dataset.filename)
    } catch (err) {
      setExportError(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  const tabLabel = dataset?.filename ?? 'data.csv'
  const hasResult = !!lastExecutionResult

  return (
    <div
      className="flex flex-col flex-1 overflow-hidden min-h-0"
      style={{ borderRight: '1px solid var(--color-border)', background: 'var(--color-bg)' }}
    >
      <div
        className="flex items-center shrink-0"
        style={{
          height: 36, background: 'var(--color-surface)',
          borderBottom: '1px solid var(--color-border)', paddingLeft: 8,
        }}
      >
        <div
          className="flex items-center gap-1.5 px-3 h-full"
          style={{
            borderRight: '1px solid var(--color-border)',
            borderBottom: '2px solid var(--color-blue)',
            background: 'var(--color-surface-1)',
            fontFamily: 'var(--font-mono)', fontSize: '0.82rem',
            color: 'var(--color-blue)',
          }}
        >
          <span style={{ fontSize: '0.78rem' }}>⊞</span>
          <span style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {tabLabel}
          </span>
        </div>
        {dataset && lastConfirmedSteps && hasResult && (
          <button
            type="button"
            onClick={handleDownload}
            disabled={exporting}
            title="Download full transformed result as CSV"
            style={{
              marginLeft: 'auto', marginRight: 8,
              padding: '3px 10px', background: 'transparent',
              border: '1px solid var(--color-border)', borderRadius: 4,
              color: exporting ? 'var(--color-text-muted)' : 'var(--color-text-soft)',
              fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
              cursor: exporting ? 'not-allowed' : 'pointer', whiteSpace: 'nowrap',
            }}
          >
            {exporting ? '…' : '↓ Download CSV'}
          </button>
        )}
      </div>

      <div ref={panelMeasureRef} className="flex flex-col flex-1 min-h-0 overflow-hidden">
        {exportError && (
          <div style={{
            padding: '4px 12px', flexShrink: 0,
            background: 'rgba(244,135,113,0.08)', borderBottom: '1px solid var(--color-red)',
            fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-red)',
          }}>✕ {exportError}</div>
        )}

        {dataset && hasResult && (
          <div
            ref={viewToggleBarRef}
            className="flex items-center gap-3 shrink-0 px-4 min-w-0"
            style={{ height: 34, borderBottom: '1px solid var(--color-border-subtle)', background: 'var(--color-surface-1)' }}
          >
            <DataPanelViewToggle value={viewMode} onChange={setViewMode} />
            <span
              title={
                viewMode === 'original'
                  ? `${dataset.row_count.toLocaleString()} rows · ${dataset.column_count} cols`
                  : `${lastExecutionResult!.row_count.toLocaleString()} rows · ${lastExecutionResult!.column_count} cols`
              }
              style={{
                marginLeft: 'auto',
                flexShrink: 0,
                whiteSpace: 'nowrap',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.7rem',
                color: 'var(--color-text-muted)',
              }}
            >
              {viewMode === 'original'
                ? formatDatasetDims(dataset.row_count, dataset.column_count, compactDims)
                : formatDatasetDims(lastExecutionResult!.row_count, lastExecutionResult!.column_count, compactDims)}
            </span>
          </div>
        )}

        <div className="flex-1 overflow-hidden min-h-0">
          {!dataset && <DataPanelEmpty />}
          {dataset && viewMode === 'original' && <DataPreview dataset={dataset} />}
          {dataset && viewMode === 'result' && lastExecutionResult && lastConfirmedSteps && (
            <ResultView
              result={lastExecutionResult}
              dataset={dataset}
              datasetId={dataset.dataset_id}
              steps={lastConfirmedSteps}
              compactDims={compactDims}
            />
          )}
        </div>
      </div>
    </div>
  )
}
