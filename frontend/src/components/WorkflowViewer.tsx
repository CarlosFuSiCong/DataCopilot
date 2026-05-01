import { useState } from 'react'
import type { WorkflowStep, StepResult } from '../types'
import { OutputBlock } from './ui/OutputBlock'

interface WorkflowViewerProps {
  steps: WorkflowStep[]
  stepResults?: StepResult[]
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

export function WorkflowViewer({ steps, stepResults }: WorkflowViewerProps) {
  const [expanded, setExpanded] = useState(false)

  const hasAnyIssues = stepResults?.some(sr => sr.issues?.length > 0)

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
                </div>
              </div>

              {/* Issue list below the step row */}
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

        <button
          onClick={() => setExpanded(v => !v)}
          style={{
            marginTop: 2, padding: '2px 8px', background: 'transparent',
            border: '1px solid var(--color-border)', borderRadius: 3,
            color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)',
            fontSize: '0.75rem', cursor: 'pointer', alignSelf: 'flex-start',
          }}
        >
          {expanded ? '▲ hide JSON' : '▼ show JSON'}
        </button>

        {expanded && (
          <pre style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-soft)', overflowX: 'auto' }}>
            {JSON.stringify(steps, null, 2)}
          </pre>
        )}
      </div>
    </OutputBlock>
  )
}
