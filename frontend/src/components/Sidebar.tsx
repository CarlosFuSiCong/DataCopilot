import { useRef, useState, useEffect } from 'react'
import type { UploadResponse, WorkflowStep, RunRecord } from '../types'
import { uploadDataset, listRuns, getRun } from '../api/client'
import { ChevronIcon } from './ui/Icons'

interface SidebarProps {
  dataset: UploadResponse | null
  onDatasetChange: (d: UploadResponse | null) => void
  onRerun: (steps: WorkflowStep[], query: string, runId?: string | null) => void
  historyRefreshKey?: number
  width: number
}

export function Sidebar({ dataset, onDatasetChange, onRerun, historyRefreshKey, width }: SidebarProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadError(null)
    try {
      const result = await uploadDataset(file)
      onDatasetChange(result)
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div
      className="flex flex-col shrink-0 overflow-y-auto"
      style={{ width, background: 'var(--color-surface)', borderRight: '1px solid var(--color-border)' }}
    >
      <div
        className="flex items-center gap-2 px-3 py-2 uppercase tracking-widest"
        style={{
          fontSize: '0.68rem', fontWeight: 600,
          color: 'var(--color-text-muted)',
          borderBottom: '1px solid var(--color-border-subtle)',
          fontFamily: 'var(--font-mono)',
        }}
      >
        Explorer
      </div>

      <SidebarSection label="DATASET">
        <input
          ref={fileRef}
          type="file"
          accept=".csv"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />

        {dataset ? (
          <div className="px-3 py-2 flex flex-col gap-1">
            <div
              className="flex items-center gap-1.5 rounded px-2 py-1.5"
              style={{ background: 'var(--color-surface-2)' }}
            >
              <span style={{ color: 'var(--color-green)', fontSize: '0.68rem' }}>●</span>
              <span
                className="truncate"
                style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--color-text)' }}
              >
                {dataset.filename}
              </span>
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)', paddingLeft: 8 }}>
              {dataset.row_count.toLocaleString()} rows · {dataset.column_count} cols
            </div>
            <button
              onClick={() => fileRef.current?.click()}
              style={{
                marginTop: 4, padding: '4px 8px', borderRadius: 3,
                background: 'transparent', border: '1px solid var(--color-border)',
                color: 'var(--color-text-soft)', fontFamily: 'var(--font-mono)',
                fontSize: '0.75rem', cursor: 'pointer', textAlign: 'left',
              }}
            >
              ↺ Replace file
            </button>
          </div>
        ) : (
          <div className="px-3 py-2 flex flex-col gap-2">
            <p style={{ fontSize: '0.82rem', color: 'var(--color-text-muted)', margin: 0 }}>
              No file loaded.
            </p>
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              style={{
                padding: '5px 8px', borderRadius: 3,
                background: 'var(--color-accent-subtle)',
                border: '1px solid var(--color-accent-dim)',
                color: 'var(--color-accent)',
                fontFamily: 'var(--font-mono)', fontSize: '0.75rem',
                cursor: uploading ? 'not-allowed' : 'pointer',
                opacity: uploading ? 0.6 : 1,
              }}
            >
              {uploading ? '⟳ Uploading…' : '+ Upload CSV'}
            </button>
            {uploadError && (
              <p style={{ fontSize: '0.75rem', color: 'var(--color-red)', margin: 0 }}>
                ✕ {uploadError}
              </p>
            )}
          </div>
        )}
      </SidebarSection>

      {dataset && (
        <SidebarSection label="SCHEMA">
          <div className="px-3 py-1.5 flex flex-col gap-0.5">
            {dataset.columns.slice(0, 10).map(col => (
              <div key={col.name} className="flex items-center justify-between gap-2">
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {col.name}
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--color-purple)', flexShrink: 0 }}>
                  {col.dtype}
                </span>
              </div>
            ))}
            {dataset.columns.length > 10 && (
              <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                +{dataset.columns.length - 10} more
              </span>
            )}
          </div>
        </SidebarSection>
      )}

      <SidebarSection label="KERNEL">
        <div className="px-3 py-1.5 flex items-center gap-2">
          <span style={{ color: 'var(--color-green)', fontSize: '0.68rem' }}>●</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-soft)' }}>
            Python · FastAPI
          </span>
        </div>
      </SidebarSection>

      {dataset && (
        <RunHistorySection
          datasetId={dataset.dataset_id}
          onRerun={onRerun}
          refreshKey={historyRefreshKey ?? 0}
        />
      )}
    </div>
  )
}

function timeAgo(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function statusColor(status: string) {
  if (status === 'executed' || status === 'confirmed' || status === 'success') return 'var(--color-green)'
  if (status === 'failed' || status === 'error') return 'var(--color-red)'
  if (status === 'warning_review' || status === 'preview_ready') return 'var(--color-yellow)'
  return 'var(--color-yellow)'
}

function statusLabel(status: string) {
  return status.replace(/_/g, ' ')
}

interface RunHistorySectionProps {
  datasetId: string
  onRerun: (steps: WorkflowStep[], query: string, runId?: string | null) => void
  refreshKey: number
}

function RunHistorySection({ datasetId, onRerun, refreshKey }: RunHistorySectionProps) {
  const [runs, setRuns] = useState<RunRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [loadingRerun, setLoadingRerun] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('all')
  const [detailsById, setDetailsById] = useState<Record<string, RunRecord>>({})

  useEffect(() => {
    let cancelled = false
    queueMicrotask(() => {
      if (cancelled) return
      setLoading(true)
      listRuns(datasetId, 20, statusFilter).then(resp => {
        if (!cancelled) { setRuns(resp.runs); setLoading(false) }
      }).catch(() => { if (!cancelled) setLoading(false) })
    })
    return () => { cancelled = true }
  }, [datasetId, refreshKey, statusFilter])

  async function toggleExpanded(run: RunRecord) {
    const nextId = expandedId === run.run_id ? null : run.run_id
    setExpandedId(nextId)
    if (nextId && !detailsById[run.run_id]) {
      const full = await getRun(run.run_id)
      setDetailsById(prev => ({ ...prev, [run.run_id]: full }))
    }
  }

  async function handleRerun(run: RunRecord) {
    setLoadingRerun(run.run_id)
    try {
      let steps = run.planned_steps
      if (!steps) {
        const full = await getRun(run.run_id)
        steps = full.planned_steps ?? []
      }
      onRerun(steps ?? [], run.query ?? '', run.run_id)
    } finally {
      setLoadingRerun(null)
    }
  }

  return (
    <SidebarSection label="HISTORY">
      <div className="flex flex-col px-2 py-1.5 gap-0.5">
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          style={{
            margin: '0 2px 6px',
            background: 'var(--color-surface-1)',
            border: '1px solid var(--color-border)',
            borderRadius: 4,
            color: 'var(--color-text-soft)',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.7rem',
            padding: '3px 6px',
          }}
        >
          <option value="all">all statuses</option>
          <option value="executed">executed</option>
          <option value="warning_review">warning review</option>
          <option value="failed">failed</option>
        </select>
        {!loading && runs.length === 0 && (
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
            color: 'var(--color-text-muted)', padding: '2px 4px',
          }}>
            no runs yet
          </span>
        )}
        {runs.map(run => {
          const isExpanded = expandedId === run.run_id
          const detail = detailsById[run.run_id] ?? run
          const summary = detail.context_summary
          const attempts = detail.attempts ?? []
          return (
            <div key={run.run_id}>
              <button
                data-testid={`run-history-${run.run_id}`}
                onClick={() => void toggleExpanded(run)}
                style={{
                  width: '100%', textAlign: 'left', background: 'transparent',
                  border: 'none', cursor: 'pointer', padding: '3px 4px',
                  borderRadius: 3,
                }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-surface-2)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <div className="flex items-center gap-1.5">
                  <span style={{ fontSize: '0.6rem', color: statusColor(run.status) }}>●</span>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)', fontSize: '0.75rem',
                      color: 'var(--color-text)', flex: 1,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}
                  >
                    {run.query ? run.query.slice(0, 30) + (run.query.length > 30 ? '…' : '') : '(no query)'}
                  </span>
                </div>
                <div
                  style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.67rem',
                    color: 'var(--color-text-muted)', paddingLeft: 16, marginTop: 1,
                  }}
                >
                  {timeAgo(run.created_at)}
                  {run.row_count != null ? ` · ${run.row_count.toLocaleString()} rows` : ''}
                  {run.step_count != null ? ` · ${run.step_count} steps` : ''}
                  {run.status ? ` · ${statusLabel(run.status)}` : ''}
                </div>
              </button>

              {isExpanded && (
                <div
                  style={{
                    marginTop: 3, marginLeft: 8, marginBottom: 4, padding: '6px 8px',
                    background: 'var(--color-surface-2)',
                    border: '1px solid var(--color-border-subtle)',
                    borderRadius: 4,
                  }}
                >
                  {detail.explanation && (
                    <p
                      style={{
                        margin: '0 0 6px', fontFamily: 'var(--font-mono)',
                        fontSize: '0.72rem', color: 'var(--color-text-soft)',
                        lineHeight: 1.5,
                        display: '-webkit-box',
                        WebkitLineClamp: 3,
                        WebkitBoxOrient: 'vertical',
                        overflow: 'hidden',
                      }}
                    >
                      {detail.explanation}
                    </p>
                  )}
                  {summary && (
                    <div style={{ marginBottom: 6, fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--color-text-muted)', lineHeight: 1.6 }}>
                      <div>state: <span style={{ color: statusColor(summary.status) }}>{statusLabel(summary.status)}</span></div>
                      <div>boundary: {summary.boundary}</div>
                      <div>validation: {summary.validation_status ?? 'n/a'} · warnings: {summary.warning_count} · errors: {summary.error_count}</div>
                      <div>schema: {summary.schema_columns.slice(0, 4).join(', ')}{summary.schema_columns.length > 4 ? '…' : ''}</div>
                      {summary.planned_step_types.length > 0 && (
                        <div>steps: {summary.planned_step_types.join(' → ')}</div>
                      )}
                      {summary.retrieved_docs.length > 0 && (
                        <div>docs: {summary.retrieved_docs.slice(0, 2).join(', ')}</div>
                      )}
                    </div>
                  )}
                  {attempts.length > 0 && (
                    <div style={{ marginBottom: 6, display: 'flex', flexDirection: 'column', gap: 3 }}>
                      {attempts.map(attempt => (
                        <div key={attempt.attempt_index} style={{ fontFamily: 'var(--font-mono)', fontSize: '0.67rem', color: 'var(--color-text-muted)' }}>
                          attempt {attempt.attempt_index}: {attempt.summary.validation_status} / {attempt.summary.preview_status} → {statusLabel(attempt.final_status)}
                          {attempt.repair_reason ? ` · repair: ${attempt.repair_reason}` : ''}
                          {attempt.planner_raw_output ? ` · planner: ${attempt.planner_raw_output.slice(0, 80)}` : ''}
                        </div>
                      ))}
                    </div>
                  )}
                  <button
                    onClick={() => handleRerun(run)}
                    disabled={loadingRerun === run.run_id}
                    style={{
                      padding: '3px 10px', borderRadius: 3,
                      background: 'transparent',
                      border: '1px solid var(--color-accent-dim)',
                      color: 'var(--color-accent)',
                      fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
                      cursor: loadingRerun === run.run_id ? 'not-allowed' : 'pointer',
                      opacity: loadingRerun === run.run_id ? 0.6 : 1,
                    }}
                  >
                    {loadingRerun === run.run_id ? '⟳ Loading…' : '▶ Rerun'}
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </SidebarSection>
  )
}

export function SidebarSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
      <div
        className="px-3 py-1.5 flex items-center gap-1"
        style={{
          fontSize: '0.68rem', fontWeight: 600,
          color: 'var(--color-text-muted)',
          letterSpacing: '0.1em',
          fontFamily: 'var(--font-mono)',
        }}
      >
        <ChevronIcon />
        {label}
      </div>
      {children}
    </div>
  )
}
