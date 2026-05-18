import { useState } from 'react'
import type { ObservationSummary, CandidateFix } from '../types'

interface ObservationPanelProps {
  observation: ObservationSummary
  onSuggest?: (query: string) => void
  onBackToPreview?: () => void
}

// ─── Signal badges ────────────────────────────────────────────────────────────

const SIGNAL_LABELS: Record<string, string> = {
  empty_result: 'Empty result',
  large_row_removal: 'Large row removal',
  no_rows_matched: 'No rows matched',
  high_warning_rate: 'High warning rate',
  execution_error: 'Execution error',
  validation_failed: 'Validation failed',
  schema_changed: 'Schema changed',
  missing_column: 'Missing column',
}

const SIGNAL_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  empty_result:      { bg: '#fef3c7', text: '#92400e', border: '#fde68a' },
  large_row_removal: { bg: '#fef3c7', text: '#92400e', border: '#fde68a' },
  no_rows_matched:   { bg: '#fef3c7', text: '#92400e', border: '#fde68a' },
  high_warning_rate: { bg: '#fef3c7', text: '#92400e', border: '#fde68a' },
  execution_error:   { bg: '#fee2e2', text: '#991b1b', border: '#fca5a5' },
  validation_failed: { bg: '#fee2e2', text: '#991b1b', border: '#fca5a5' },
  schema_changed:    { bg: '#e0f2fe', text: '#0c4a6e', border: '#7dd3fc' },
  missing_column:    { bg: '#fee2e2', text: '#991b1b', border: '#fca5a5' },
}

// ─── Status icon ──────────────────────────────────────────────────────────────

function StatusIcon({ status }: { status: ObservationSummary['status'] }) {
  if (status === 'error') return <span style={{ color: 'var(--color-red)', fontSize: '0.9rem' }}>✗</span>
  if (status === 'warning') return <span style={{ color: '#d97706', fontSize: '0.9rem' }}>⚠</span>
  if (status === 'ok') return <span style={{ color: 'var(--color-green)', fontSize: '0.9rem' }}>✓</span>
  return null
}

// ─── Candidate fix button ─────────────────────────────────────────────────────

function FixButton({
  fix,
  onSuggest,
  onBackToPreview,
}: {
  fix: CandidateFix
  onSuggest?: (query: string) => void
  onBackToPreview?: () => void
}) {
  function handleClick() {
    if (fix.action_type === 'back_to_preview') {
      onBackToPreview?.()
    } else if (fix.query && onSuggest) {
      onSuggest(fix.query)
    }
  }

  const isClickable =
    (fix.action_type === 'back_to_preview' && onBackToPreview != null) ||
    ((fix.action_type === 'suggest_query' || fix.action_type === 'inspect_column' || fix.action_type === 'relax_filter') &&
      fix.query != null &&
      onSuggest != null)

  return (
    <button
      onClick={handleClick}
      disabled={!isClickable}
      title={fix.description}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '4px 10px',
        borderRadius: 6,
        border: '1px solid var(--color-border)',
        background: 'var(--color-surface-1)',
        color: isClickable ? 'var(--color-accent)' : 'var(--color-text-muted)',
        fontFamily: 'var(--font-mono)',
        fontSize: '0.78rem',
        cursor: isClickable ? 'pointer' : 'default',
        whiteSpace: 'nowrap',
        transition: 'background 0.15s',
      }}
    >
      {fix.action_type === 'back_to_preview' && '↩ '}
      {fix.action_type === 'inspect_column' && '🔍 '}
      {fix.action_type === 'relax_filter' && '↕ '}
      {fix.action_type === 'suggest_query' && '→ '}
      {fix.label}
    </button>
  )
}

// ─── Main panel ───────────────────────────────────────────────────────────────

export function ObservationPanel({ observation, onSuggest, onBackToPreview }: ObservationPanelProps) {
  const [expanded, setExpanded] = useState(false)

  if (observation.status === 'not_observed' || observation.status === 'ok') return null

  const isError = observation.status === 'error'
  const borderColor = isError ? '#fca5a5' : '#fde68a'
  const bgColor = isError ? '#fff5f5' : '#fffbeb'
  const headerBg = isError ? '#fee2e2' : '#fef3c7'

  return (
    <div
      data-testid="observation-panel"
      style={{
        border: `1px solid ${borderColor}`,
        borderRadius: 8,
        overflow: 'hidden',
        marginTop: 8,
        fontFamily: 'var(--font-mono)',
        fontSize: '0.82rem',
      }}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(v => !v)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          width: '100%',
          padding: '7px 12px',
          background: headerBg,
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        <StatusIcon status={observation.status} />
        <span style={{ flex: 1, color: isError ? '#991b1b' : '#92400e', fontWeight: 600 }}>
          {observation.message ?? (isError ? 'Execution error' : 'Workflow warnings')}
        </span>

        {/* Signal chips (always visible) */}
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {observation.signals.slice(0, 3).map(sig => {
            const c = SIGNAL_COLORS[sig] ?? { bg: '#f1f5f9', text: '#475569', border: '#cbd5e1' }
            return (
              <span key={sig} style={{
                padding: '1px 7px',
                borderRadius: 10,
                background: c.bg,
                color: c.text,
                border: `1px solid ${c.border}`,
                fontSize: '0.73rem',
              }}>
                {SIGNAL_LABELS[sig] ?? sig}
              </span>
            )
          })}
        </div>

        <span style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem', marginLeft: 4 }}>
          {expanded ? '▲' : '▼'}
        </span>
      </button>

      {/* Expanded body */}
      {expanded && (
        <div style={{ padding: '10px 14px', background: bgColor, display: 'flex', flexDirection: 'column', gap: 10 }}>

          {/* Diagnostic explanation */}
          {observation.diagnostic_explanation && (
            <div>
              <p style={{ margin: '0 0 3px', color: 'var(--color-text-muted)', fontSize: '0.73rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                What happened
              </p>
              <p style={{ margin: 0, color: 'var(--color-text)', lineHeight: 1.5 }}>
                {observation.diagnostic_explanation}
              </p>
            </div>
          )}

          {/* Possible causes */}
          {observation.possible_causes.length > 0 && (
            <div>
              <p style={{ margin: '0 0 3px', color: 'var(--color-text-muted)', fontSize: '0.73rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Why it may happen
              </p>
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {observation.possible_causes.map((cause, i) => (
                  <li key={i} style={{ color: 'var(--color-text)', lineHeight: 1.5 }}>{cause}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Evidence signals */}
          {observation.signals.length > 0 && (
            <div>
              <p style={{ margin: '0 0 4px', color: 'var(--color-text-muted)', fontSize: '0.73rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Evidence
              </p>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {observation.signals.map(sig => {
                  const c = SIGNAL_COLORS[sig] ?? { bg: '#f1f5f9', text: '#475569', border: '#cbd5e1' }
                  return (
                    <span key={sig} style={{
                      padding: '2px 9px',
                      borderRadius: 10,
                      background: c.bg,
                      color: c.text,
                      border: `1px solid ${c.border}`,
                      fontSize: '0.75rem',
                    }}>
                      {SIGNAL_LABELS[sig] ?? sig}
                    </span>
                  )
                })}
              </div>
            </div>
          )}

          {/* Candidate fix buttons */}
          {observation.candidate_fixes.length > 0 && (
            <div>
              <p style={{ margin: '0 0 5px', color: 'var(--color-text-muted)', fontSize: '0.73rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Suggested next actions
              </p>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {observation.candidate_fixes.map(fix => (
                  <FixButton
                    key={fix.id}
                    fix={fix}
                    onSuggest={onSuggest}
                    onBackToPreview={onBackToPreview}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
