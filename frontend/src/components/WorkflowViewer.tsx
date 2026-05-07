import { useState } from 'react'
import type { WorkflowStep, StepResult } from '../types'
import { OutputBlock } from './ui/OutputBlock'

interface WorkflowViewerProps {
  steps: WorkflowStep[]
  stepResults?: StepResult[]
  /** Called when the user edits the JSON and clicks Rerun. */
  onRerun?: (steps: WorkflowStep[]) => void
}

function StatusBadge({ status }: { status: 'success' | 'warning' | 'error' }) {
  const map = {
    success: { symbol: '✓', color: 'var(--color-green)' },
    warning: { symbol: '⚠', color: 'var(--color-yellow)' },
    error:   { symbol: '✗', color: 'var(--color-red)' },
  }
  const { symbol, color } = map[status]
  return (
    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color }}>
      {symbol}
    </span>
  )
}

const btnBase: React.CSSProperties = {
  padding: '2px 8px',
  background: 'transparent',
  border: '1px solid var(--color-border)',
  borderRadius: 3,
  color: 'var(--color-text-muted)',
  fontFamily: 'var(--font-mono)',
  fontSize: '0.75rem',
  cursor: 'pointer',
}

export function WorkflowViewer({ steps, stepResults, onRerun }: WorkflowViewerProps) {
  const [jsonExpanded, setJsonExpanded] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [editValue, setEditValue] = useState('')
  const [editError, setEditError] = useState<string | null>(null)

  const hasAnyIssues = stepResults?.some(sr => sr.issues?.length > 0)

  function enterEdit() {
    setEditValue(JSON.stringify(steps, null, 2))
    setEditError(null)
    setEditMode(true)
    setJsonExpanded(true)
  }

  function cancelEdit() {
    setEditMode(false)
    setEditError(null)
  }

  function handleRerun() {
    setEditError(null)
    let parsed: unknown
    try {
      parsed = JSON.parse(editValue)
    } catch {
      setEditError('Invalid JSON — fix syntax errors before rerunning.')
      return
    }
    if (!Array.isArray(parsed)) {
      setEditError('Workflow must be a JSON array of steps.')
      return
    }
    setEditMode(false)
    onRerun?.(parsed as WorkflowStep[])
  }

  return (
    <OutputBlock
      label={`workflow · ${steps.length} step${steps.length !== 1 ? 's' : ''}${hasAnyIssues ? ' · has issues' : ''}`}
      accent="var(--color-yellow)"
    >
      <div className="flex flex-col gap-1.5">
        {steps.map((step, i) => {
          const sr = stepResults?.[i]
          const borderColor =
            sr?.status === 'error' ? 'var(--color-red)' :
            sr?.status === 'warning' ? 'var(--color-yellow)' :
            'var(--color-border-subtle)'

          return (
            <div key={i}>
              <div
                className="flex items-start gap-2 rounded px-2 py-1.5"
                style={{
                  background: 'var(--color-surface-2)',
                  border: `1px solid ${borderColor}`,
                }}
              >
                <span
                  style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
                    color: 'var(--color-text-muted)', minWidth: 20, paddingTop: 1,
                  }}
                >
                  {i + 1}.
                </span>
                <div className="flex flex-col gap-0.5 flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--color-yellow)', fontWeight: 500 }}>
                      {step.type}
                    </span>
                    {sr && <StatusBadge status={sr.status} />}
                    {sr && (
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                        {sr.input_row_count}→{sr.output_row_count} rows
                      </span>
                    )}
                    {sr?.match_rate != null && (
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                        match {Math.round(sr.match_rate * 100)}%
                      </span>
                    )}
                    {sr?.affected_rate != null && (
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                        affected {Math.round(sr.affected_rate * 100)}%
                      </span>
                    )}
                  </div>
                  {Object.entries(step)
                    .filter(([k]) => k !== 'type')
                    .map(([k, v]) => (
                      <span key={k} style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-soft)' }}>
                        <span style={{ color: 'var(--color-blue)' }}>{k}</span>
                        {': '}
                        <span style={{ color: 'var(--color-orange)' }}>{JSON.stringify(v)}</span>
                      </span>
                    ))}
                  {sr?.message && (
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: 1 }}>
                      ↳ {sr.message}
                    </span>
                  )}
                </div>
              </div>

              {sr?.issues?.map((issue, j) => (
                <div
                  key={j}
                  className="flex items-start gap-2 rounded px-2 py-1 ml-6 mt-0.5"
                  style={{
                    background: issue.severity === 'error'
                      ? 'rgba(244,135,113,0.08)'
                      : 'rgba(220,220,170,0.07)',
                    border: `1px solid ${issue.severity === 'error' ? 'var(--color-red)' : 'var(--color-yellow)'}`,
                  }}
                >
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
                      color: issue.severity === 'error' ? 'var(--color-red)' : 'var(--color-yellow)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    [{issue.code}]
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--color-text-soft)' }}>
                    {issue.message}
                  </span>
                </div>
              ))}
            </div>
          )
        })}

        {/* JSON toolbar */}
        <div className="flex items-center gap-2 flex-wrap" style={{ marginTop: 2 }}>
          <button
            onClick={() => {
              if (!jsonExpanded) setEditMode(false)
              setJsonExpanded(v => !v)
            }}
            style={btnBase}
          >
            {jsonExpanded ? '▲ hide JSON' : '▼ show JSON'}
          </button>

          {jsonExpanded && !editMode && onRerun && (
            <button onClick={enterEdit} style={{ ...btnBase, color: 'var(--color-accent)', borderColor: 'var(--color-accent-dim)' }}>
              ✎ Edit &amp; Rerun
            </button>
          )}

          {editMode && (
            <>
              <button
                onClick={handleRerun}
                style={{ ...btnBase, color: 'var(--color-green)', borderColor: 'var(--color-green)' }}
              >
                ▶ Rerun
              </button>
              <button onClick={cancelEdit} style={btnBase}>
                ✕ Cancel
              </button>
            </>
          )}
        </div>

        {jsonExpanded && !editMode && (
          <pre style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-soft)', overflowX: 'auto' }}>
            {JSON.stringify(steps, null, 2)}
          </pre>
        )}

        {editMode && (
          <div className="flex flex-col gap-1">
            <textarea
              value={editValue}
              onChange={e => { setEditValue(e.target.value); setEditError(null) }}
              spellCheck={false}
              rows={Math.min(Math.max(editValue.split('\n').length, 8), 30)}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '0.75rem',
                color: 'var(--color-text)',
                background: 'var(--color-surface-2)',
                border: `1px solid ${editError ? 'var(--color-red)' : 'var(--color-border)'}`,
                borderRadius: 4,
                padding: '8px 10px',
                resize: 'vertical',
                outline: 'none',
                width: '100%',
                lineHeight: 1.6,
              }}
            />
            {editError && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--color-red)' }}>
                ✗ {editError}
              </span>
            )}
          </div>
        )}
      </div>
    </OutputBlock>
  )
}
