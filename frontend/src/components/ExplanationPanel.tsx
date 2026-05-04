import type { ExecutionResult } from '../types'
import { OutputBlock } from './ui/OutputBlock'

interface ExplanationPanelProps {
  text: string
  executionResult?: ExecutionResult
}

export function ExplanationPanel({ text, executionResult }: ExplanationPanelProps) {
  return (
    <OutputBlock label="explanation" accent="var(--color-accent)">
      <div className="flex flex-col gap-3">

        {/* Execution facts */}
        {executionResult && (
          <div
            className="flex flex-wrap gap-x-4 gap-y-1 rounded px-3 py-2"
            style={{
              background: 'var(--color-surface-2)',
              border: '1px solid var(--color-border-subtle)',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.75rem',
            }}
          >
            <Fact label="rows out" value={executionResult.row_count.toLocaleString()} color="var(--color-green)" />
            <Fact label="cols" value={String(executionResult.column_count)} color="var(--color-blue)" />
            <Fact label="steps" value={String(executionResult.step_results.length)} color="var(--color-yellow)" />
            {executionResult.step_results.length > 0 && (() => {
              const firstIn = executionResult.step_results[0].input_row_count
              return <Fact label="rows in" value={firstIn.toLocaleString()} color="var(--color-text-muted)" />
            })()}
            <Fact
              label="columns"
              value={executionResult.columns.slice(0, 4).join(', ') + (executionResult.columns.length > 4 ? ` +${executionResult.columns.length - 4}` : '')}
              color="var(--color-text-soft)"
            />
          </div>
        )}

        {/* Natural language summary */}
        <div>
          <div
            style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
              color: 'var(--color-text-muted)', letterSpacing: '0.06em',
              marginBottom: 6,
            }}
          >
            SUMMARY
          </div>
          <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--color-text)', lineHeight: 1.7, fontFamily: 'var(--font-ui)' }}>
            {text}
          </p>
        </div>

      </div>
    </OutputBlock>
  )
}

function Fact({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <span>
      <span style={{ color: 'var(--color-text-muted)' }}>{label} </span>
      <span style={{ color }}>{value}</span>
    </span>
  )
}
