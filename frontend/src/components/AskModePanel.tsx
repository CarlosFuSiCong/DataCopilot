import type { ChatResponse, ColumnProfile } from '../types'

interface AskModePanelProps {
  result: ChatResponse
  onSuggest: (query: string) => void
}

function formatPct(value: number): string {
  return `${Number(value).toFixed(value >= 10 ? 1 : 2)}%`
}

function findUsefulColumns(columns: ColumnProfile[]) {
  const numeric = columns.find(col => /int|float|double|decimal/i.test(col.dtype))
  const categorical = columns.find(col => !/int|float|double|decimal/i.test(col.dtype))
  return { numeric, categorical }
}

export function AskModePanel({ result, onSuggest }: AskModePanelProps) {
  const summary = result.rag_context?.dataset_summary
  const columns = summary?.columns ?? []
  const missingColumns = columns.filter(col => col.missing_count > 0)
  const { numeric, categorical } = findUsefulColumns(columns)
  const followUps = [
    { label: 'Check missing values', query: 'Check for missing values' },
    numeric ? { label: `Profile ${numeric.name}`, query: `Profile the ${numeric.name} column` } : null,
    numeric && categorical
      ? { label: `Compare ${numeric.name} by ${categorical.name}`, query: `Compare average ${numeric.name} by ${categorical.name}` }
      : null,
  ].filter((item): item is { label: string; query: string } => item != null)

  return (
    <div
      data-testid="ask-mode-panel"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        padding: '12px 14px',
        background: 'linear-gradient(135deg, rgba(78,201,176,0.08), rgba(86,156,214,0.04))',
        border: '1px solid rgba(78,201,176,0.35)',
        borderRadius: 10,
        fontFamily: 'var(--font-mono)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start' }}>
        <div>
          <p style={{ margin: 0, color: 'var(--color-accent)', fontSize: '0.76rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Ask Mode Answer
          </p>
          {result.explanation && (
            <p style={{ margin: '6px 0 0', color: 'var(--color-text)', fontSize: '0.84rem', lineHeight: 1.6 }}>
              {result.explanation}
            </p>
          )}
        </div>
        {result.evidence_source && (
          <span style={{
            flexShrink: 0,
            border: '1px solid var(--color-border)',
            borderRadius: 999,
            padding: '2px 8px',
            color: 'var(--color-text-muted)',
            fontSize: '0.68rem',
          }}>
            evidence: {result.evidence_source}
          </span>
        )}
      </div>

      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 6 }}>
          <Metric label="Rows" value={summary.row_count.toLocaleString()} />
          <Metric label="Columns" value={summary.column_count.toLocaleString()} />
          <Metric label="Columns with missing" value={String(missingColumns.length)} />
        </div>
      )}

      {columns.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <p style={{ margin: 0, color: 'var(--color-text-muted)', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Schema evidence
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {columns.slice(0, 10).map(col => (
              <span
                key={col.name}
                style={{
                  border: '1px solid var(--color-border)',
                  borderRadius: 7,
                  padding: '3px 7px',
                  color: col.missing_count > 0 ? 'var(--color-yellow)' : 'var(--color-text-soft)',
                  background: 'rgba(19,22,26,0.35)',
                  fontSize: '0.7rem',
                }}
              >
                {col.name} · {col.dtype}
                {col.missing_count > 0 ? ` · ${formatPct(col.missing_pct)} missing` : ''}
              </span>
            ))}
          </div>
        </div>
      )}

      {followUps.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {followUps.map(item => (
            <button
              key={item.query}
              type="button"
              onClick={() => onSuggest(item.query)}
              style={{
                border: '1px solid var(--color-accent)',
                background: 'rgba(78,201,176,0.08)',
                color: 'var(--color-accent)',
                borderRadius: 7,
                padding: '4px 8px',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.72rem',
                cursor: 'pointer',
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: 'var(--color-surface-1)', border: '1px solid var(--color-border)', borderRadius: 8, padding: '7px 9px' }}>
      <p style={{ margin: 0, color: 'var(--color-text-muted)', fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {label}
      </p>
      <p style={{ margin: '2px 0 0', color: 'var(--color-text-heading)', fontSize: '0.9rem', fontWeight: 600 }}>
        {value}
      </p>
    </div>
  )
}
