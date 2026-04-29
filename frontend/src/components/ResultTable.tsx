import { useState } from 'react'
import type { StepLog } from '../types'
import { OutputBlock } from './ui/OutputBlock'

interface ResultTableProps {
  columns: string[]
  rows: Record<string, unknown>[]
  rowCount: number
  logs: StepLog[]
}

export function ResultTable({ columns, rows, rowCount, logs }: ResultTableProps) {
  const [showLogs, setShowLogs] = useState(false)

  return (
    <OutputBlock label={`result · ${rowCount.toLocaleString()} rows`} accent="var(--color-accent)">
      <div className="flex flex-col gap-2">
        {rows.length === 0 ? (
          <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--color-text-muted)' }}>
            No rows returned.
          </p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%', fontFamily: 'var(--font-mono)', fontSize: '0.82rem' }}>
              <thead>
                <tr>
                  {columns.map(col => (
                    <th
                      key={col}
                      style={{
                        padding: '5px 10px', textAlign: 'left', whiteSpace: 'nowrap',
                        borderBottom: '1px solid var(--color-border)',
                        color: 'var(--color-blue)', fontWeight: 500,
                        background: 'var(--color-surface-2)',
                      }}
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, rowIdx) => (
                  <tr
                    key={rowIdx}
                    style={{ background: rowIdx % 2 === 0 ? 'transparent' : 'var(--color-surface-2)' }}
                  >
                    {columns.map(col => (
                      <td
                        key={col}
                        style={{
                          padding: '4px 10px', whiteSpace: 'nowrap',
                          borderBottom: '1px solid var(--color-border-subtle)',
                          color: 'var(--color-text)',
                        }}
                      >
                        {row[col] == null
                          ? <span style={{ color: 'var(--color-text-muted)' }}>null</span>
                          : String(row[col])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {rowCount > rows.length && (
          <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}>
            Showing {rows.length} of {rowCount.toLocaleString()} rows.
          </p>
        )}

        {logs.length > 0 && (
          <>
            <button
              onClick={() => setShowLogs(v => !v)}
              style={{
                padding: '2px 8px', background: 'transparent',
                border: '1px solid var(--color-border)', borderRadius: 3,
                color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)',
                fontSize: '0.75rem', cursor: 'pointer', alignSelf: 'flex-start',
              }}
            >
              {showLogs ? '▲ hide logs' : `▼ show logs (${logs.length})`}
            </button>
            {showLogs && (
              <div className="flex flex-col gap-1">
                {logs.map((log, i) => (
                  <div key={i} style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-soft)' }}>
                    <span style={{ color: 'var(--color-text-muted)' }}>[{log.step_type}]</span>
                    {' '}{log.message}
                    {' · '}
                    <span style={{ color: 'var(--color-green)' }}>{log.rows_before}→{log.rows_after} rows</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </OutputBlock>
  )
}
