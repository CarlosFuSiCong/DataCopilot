import type { StepResult, WorkflowStep } from '../types'

export const ANALYTICAL_STEP_TYPES = new Set([
  'profile_column',
  'distribution_summary',
  'summarize_numeric_column',
  'compare_groups',
  'correlation_summary',
  'inspect_unique_values',
  'detect_missing_values',
  'suggest_analysis_steps',
])

// ─── helpers ──────────────────────────────────────────────────────────────────

function statCard(stat: string, value: string, highlight: boolean) {
  const STAT_LABELS: Record<string, string> = {
    column: 'Column', dtype: 'Data type', total_rows: 'Total rows',
    non_null_count: 'Non-null', missing_pct: 'Missing %', unique_count: 'Unique values',
    top_values: 'Top values', min: 'Min', max: 'Max', mean: 'Mean',
    count: 'Count', median: 'Median', std: 'Std dev', q25: 'Q25', q75: 'Q75',
    skewness: 'Skewness', skew_label: 'Shape', outlier_count_iqr: 'IQR outliers',
  }
  return (
    <div key={stat} style={{
      background: 'var(--color-surface-1)',
      border: `1px solid ${highlight ? 'var(--color-accent)' : 'var(--color-border)'}`,
      borderRadius: 6,
      padding: '6px 10px',
    }}>
      <p style={{ margin: '0 0 2px', fontFamily: 'var(--font-mono)', fontSize: '0.66rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {STAT_LABELS[stat] ?? stat}
      </p>
      <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: highlight ? 'var(--color-accent)' : 'var(--color-text)', fontWeight: highlight ? 600 : 400, wordBreak: 'break-all' }}>
        {value}
      </p>
    </div>
  )
}

// ─── stat/value grid ──────────────────────────────────────────────────────────

function StatValuePanel({ rows, title }: { rows: Record<string, unknown>[]; title: string }) {
  const HIGHLIGHT = new Set(['dtype', 'missing_pct', 'unique_count', 'skew_label', 'outlier_count_iqr'])
  return (
    <div>
      <p style={{ margin: '0 0 8px', fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--color-text-muted)', fontWeight: 600 }}>
        {title}
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 6 }}>
        {rows.map(row => {
          const stat = String(row.stat ?? '')
          const value = String(row.value ?? '—')
          return statCard(stat, value, HIGHLIGHT.has(stat))
        })}
      </div>
    </div>
  )
}

// ─── compare_groups ───────────────────────────────────────────────────────────

function CompareGroupsPanel({ rows, message }: { rows: Record<string, unknown>[]; message: string }) {
  if (!rows.length) return null
  const cols = Object.keys(rows[0])
  const [groupCol, valueCol, countCol] = cols
  const maxVal = Math.max(...rows.map(r => Number(r[valueCol] ?? 0)))

  return (
    <div>
      <p style={{ margin: '0 0 4px', fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--color-text-muted)', fontWeight: 600 }}>
        Group Comparison
      </p>
      <p style={{ margin: '0 0 10px', fontFamily: 'var(--font-mono)', fontSize: '0.74rem', color: 'var(--color-text-muted)' }}>
        {message}
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {rows.slice(0, 12).map((row, i) => {
          const group = String(row[groupCol] ?? '')
          const val = Number(row[valueCol] ?? 0)
          const cnt = row[countCol] != null ? Number(row[countCol]) : null
          const pct = maxVal > 0 ? (val / maxVal) * 100 : 0
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                width: 130, fontFamily: 'var(--font-mono)', fontSize: '0.76rem',
                color: i === 0 ? 'var(--color-accent)' : 'var(--color-text)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flexShrink: 0,
              }}>
                {group}
              </span>
              <div style={{ flex: 1, height: 14, background: 'var(--color-surface-2)', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{
                  width: `${pct}%`, height: '100%',
                  background: i === 0 ? 'var(--color-accent)' : 'rgba(152,195,121,0.45)',
                  borderRadius: 3,
                  transition: 'width 0.3s',
                }} />
              </div>
              <span style={{ width: 80, fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--color-text)', textAlign: 'right', flexShrink: 0 }}>
                {typeof val === 'number' ? val.toLocaleString(undefined, { maximumFractionDigits: 2 }) : val}
              </span>
              {cnt != null && (
                <span style={{ width: 50, fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--color-text-muted)', textAlign: 'right', flexShrink: 0 }}>
                  n={cnt}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── correlation_summary ──────────────────────────────────────────────────────

function CorrelationPanel({ rows, message }: { rows: Record<string, unknown>[]; message: string }) {
  function strengthInfo(corr: number): { label: string; color: string } {
    const abs = Math.abs(corr)
    if (abs >= 0.8) return { label: 'strong', color: 'var(--color-accent)' }
    if (abs >= 0.5) return { label: 'moderate', color: 'var(--color-yellow)' }
    if (abs >= 0.3) return { label: 'weak', color: 'var(--color-text-muted)' }
    return { label: 'negligible', color: 'var(--color-border)' }
  }

  return (
    <div>
      <p style={{ margin: '0 0 4px', fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--color-text-muted)', fontWeight: 600 }}>
        Correlation Summary
      </p>
      <p style={{ margin: '0 0 10px', fontFamily: 'var(--font-mono)', fontSize: '0.74rem', color: 'var(--color-text-muted)' }}>
        {message}
      </p>
      {rows.length === 0 ? (
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--color-text-muted)' }}>
          No pairs computed.
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {rows.slice(0, 10).map((row, i) => {
            const colA = String(row.col_a ?? '')
            const colB = String(row.col_b ?? '')
            const corr = Number(row.correlation ?? 0)
            const { label, color } = strengthInfo(corr)
            const barPct = Math.abs(corr) * 100
            const isPos = corr >= 0
            return (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '4px 8px',
                background: 'var(--color-surface-1)',
                border: '1px solid var(--color-border)',
                borderRadius: 4,
              }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.74rem', color: 'var(--color-text)', flex: 1 }}>
                  {colA} ↔ {colB}
                </span>
                <div style={{ width: 80, height: 10, background: 'var(--color-surface-2)', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{
                    width: `${barPct}%`, height: '100%',
                    background: isPos ? 'var(--color-accent)' : 'var(--color-red)',
                    borderRadius: 3,
                  }} />
                </div>
                <span style={{ width: 52, fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--color-text)', textAlign: 'right', flexShrink: 0 }}>
                  {corr.toFixed(3)}
                </span>
                <span style={{ width: 68, fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color, textAlign: 'right', flexShrink: 0 }}>
                  {label}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ─── inspect_unique_values ────────────────────────────────────────────────────

function UniqueValuesPanel({ rows, title, message }: { rows: Record<string, unknown>[]; title: string; message: string }) {
  const maxCount = Math.max(...rows.map(r => Number(r.count ?? 0)))

  return (
    <div>
      <p style={{ margin: '0 0 4px', fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--color-text-muted)', fontWeight: 600 }}>
        {title}
      </p>
      <p style={{ margin: '0 0 10px', fontFamily: 'var(--font-mono)', fontSize: '0.74rem', color: 'var(--color-text-muted)' }}>
        {message}
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {rows.slice(0, 15).map((row, i) => {
          const val = row.value === null || row.value === undefined ? 'null' : String(row.value)
          const count = Number(row.count ?? 0)
          const pct = Number(row.pct ?? 0)
          const barPct = maxCount > 0 ? (count / maxCount) * 100 : 0
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                width: 110, fontFamily: 'var(--font-mono)', fontSize: '0.76rem',
                color: 'var(--color-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flexShrink: 0,
              }}>
                {val}
              </span>
              <div style={{ flex: 1, height: 12, background: 'var(--color-surface-2)', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${barPct}%`, height: '100%', background: 'var(--color-accent)', borderRadius: 3 }} />
              </div>
              <span style={{ width: 46, fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--color-text-muted)', textAlign: 'right', flexShrink: 0 }}>
                {pct.toFixed(1)}%
              </span>
              <span style={{ width: 46, fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--color-text-muted)', textAlign: 'right', flexShrink: 0 }}>
                {count}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── detect_missing_values ────────────────────────────────────────────────────

function DetectMissingPanel({ rows, message }: { rows: Record<string, unknown>[]; message: string }) {
  const hasNone = rows.length === 1 && rows[0].column === '(no missing values)'

  return (
    <div>
      <p style={{ margin: '0 0 8px', fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--color-text-muted)', fontWeight: 600 }}>
        Missing Values Check
      </p>
      {hasNone ? (
        <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--color-accent)' }}>
          ✓ No missing values found in any column.
        </p>
      ) : (
        <>
          <p style={{ margin: '0 0 8px', fontFamily: 'var(--font-mono)', fontSize: '0.74rem', color: 'var(--color-yellow)' }}>
            {message}
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {rows.map((row, i) => {
              const col = String(row.column ?? '')
              const pct = Number(row.missing_pct ?? 0)
              const cnt = Number(row.missing_count ?? 0)
              const dtype = String(row.dtype ?? '')
              const isHigh = pct > 20
              return (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 8, padding: '5px 8px',
                  background: isHigh ? 'rgba(244,135,113,0.06)' : 'var(--color-surface-1)',
                  border: `1px solid ${isHigh ? 'var(--color-red)' : 'var(--color-border)'}`,
                  borderRadius: 4,
                }}>
                  <span style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--color-accent)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {col}
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--color-text-muted)', flexShrink: 0 }}>
                    {dtype}
                  </span>
                  <div style={{ width: 80, height: 10, background: 'var(--color-surface-2)', borderRadius: 3, overflow: 'hidden', flexShrink: 0 }}>
                    <div style={{
                      width: `${Math.min(pct, 100)}%`, height: '100%',
                      background: isHigh ? 'var(--color-red)' : 'var(--color-yellow)',
                      borderRadius: 3,
                    }} />
                  </div>
                  <span style={{ width: 52, fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: isHigh ? 'var(--color-red)' : 'var(--color-yellow)', textAlign: 'right', flexShrink: 0 }}>
                    {pct.toFixed(1)}%
                  </span>
                  <span style={{ width: 54, fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--color-text-muted)', textAlign: 'right', flexShrink: 0 }}>
                    {cnt} missing
                  </span>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

// ─── suggest_analysis_steps ───────────────────────────────────────────────────

function SuggestionsPanel({ rows }: { rows: Record<string, unknown>[] }) {
  return (
    <div>
      <p style={{ margin: '0 0 8px', fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--color-text-muted)', fontWeight: 600 }}>
        Analysis Suggestions
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {rows.map((row, i) => (
          <div key={i} style={{
            padding: '6px 10px',
            background: 'var(--color-surface-1)',
            border: '1px solid var(--color-border)',
            borderRadius: 4,
            fontFamily: 'var(--font-mono)',
            fontSize: '0.78rem',
            color: 'var(--color-text)',
          }}>
            {String(row.suggestion ?? Object.values(row)[0] ?? '')}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── main export ──────────────────────────────────────────────────────────────

interface AnalyticsSummaryPanelProps {
  stepResult: StepResult
  plannedStep?: WorkflowStep
}

export function AnalyticsSummaryPanel({ stepResult, plannedStep }: AnalyticsSummaryPanelProps) {
  const { step_type, preview, message } = stepResult

  if (!ANALYTICAL_STEP_TYPES.has(step_type)) return null
  if (!preview || preview.length === 0) return null

  const col = typeof plannedStep?.column === 'string' ? plannedStep.column : ''

  const content = (() => {
    switch (step_type) {
      case 'profile_column':
        return <StatValuePanel rows={preview} title={`Column Profile${col ? ` · ${col}` : ''}`} />
      case 'distribution_summary':
        return <StatValuePanel rows={preview} title={`Distribution${col ? ` · ${col}` : ''}`} />
      case 'summarize_numeric_column':
        return <StatValuePanel rows={preview} title={`Numeric Summary${col ? ` · ${col}` : ''}`} />
      case 'compare_groups':
        return <CompareGroupsPanel rows={preview} message={message} />
      case 'correlation_summary':
        return <CorrelationPanel rows={preview} message={message} />
      case 'inspect_unique_values':
        return (
          <UniqueValuesPanel
            rows={preview}
            title={`Unique Values${col ? ` · ${col}` : ''}`}
            message={message}
          />
        )
      case 'detect_missing_values':
        return <DetectMissingPanel rows={preview} message={message} />
      case 'suggest_analysis_steps':
        return <SuggestionsPanel rows={preview} />
      default:
        return null
    }
  })()

  if (!content) return null

  return (
    <div
      data-testid="analytics-summary-panel"
      style={{
        background: 'var(--color-surface-1)',
        border: '1px solid var(--color-border)',
        borderRadius: 8,
        padding: '12px 14px',
      }}
    >
      {content}
    </div>
  )
}
