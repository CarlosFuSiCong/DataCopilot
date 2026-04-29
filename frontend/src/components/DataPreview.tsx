import { useState } from 'react'
import type { UploadResponse } from '../types'

interface DataPreviewProps {
  dataset: UploadResponse
}

const PAGE_SIZE = 5

export function DataPreview({ dataset }: DataPreviewProps) {
  const [page, setPage] = useState(0)

  const { filename, row_count, column_count, columns, preview } = dataset

  // Client-side pagination over the preview rows we have
  const totalPages = Math.ceil(preview.length / PAGE_SIZE)
  const pageRows = preview.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const colNames = columns.map(c => c.name)

  return (
    <div className="flex flex-col gap-3 p-6 flex-1 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.85rem',
              color: 'var(--color-accent)',
              fontWeight: 600,
            }}
          >
            {filename}
          </span>
          <span
            className="px-2 py-0.5 rounded"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.72rem',
              background: 'var(--color-surface-2)',
              color: 'var(--color-text-muted)',
              border: '1px solid var(--color-border-subtle)',
            }}
          >
            {row_count.toLocaleString()} rows · {column_count} cols
          </span>
        </div>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.72rem',
            color: 'var(--color-text-muted)',
          }}
        >
          Preview · first {preview.length} rows
        </span>
      </div>

      {/* Table */}
      <div
        className="rounded overflow-hidden"
        style={{ border: '1px solid var(--color-border)' }}
      >
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', fontFamily: 'var(--font-mono)', fontSize: '0.82rem' }}>
            <thead>
              <tr style={{ background: 'var(--color-surface-2)' }}>
                {/* Row index header */}
                <th
                  style={{
                    padding: '6px 10px',
                    textAlign: 'right',
                    borderBottom: '1px solid var(--color-border)',
                    borderRight: '1px solid var(--color-border)',
                    color: 'var(--color-text-muted)',
                    fontWeight: 400,
                    minWidth: 40,
                  }}
                >
                  #
                </th>
                {colNames.map(col => (
                  <th
                    key={col}
                    style={{
                      padding: '6px 12px',
                      textAlign: 'left',
                      whiteSpace: 'nowrap',
                      borderBottom: '1px solid var(--color-border)',
                      borderRight: '1px solid var(--color-border-subtle)',
                      color: 'var(--color-blue)',
                      fontWeight: 500,
                    }}
                  >
                    <div className="flex flex-col gap-0.5">
                      <span>{col}</span>
                      <span style={{ fontSize: '0.65rem', color: 'var(--color-purple)', fontWeight: 400 }}>
                        {columns.find(c => c.name === col)?.dtype ?? ''}
                      </span>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pageRows.map((row, i) => {
                const absoluteIndex = page * PAGE_SIZE + i
                return (
                  <tr
                    key={absoluteIndex}
                    style={{ background: i % 2 === 0 ? 'transparent' : 'var(--color-surface-2)' }}
                  >
                    <td
                      style={{
                        padding: '4px 10px',
                        textAlign: 'right',
                        borderBottom: '1px solid var(--color-border-subtle)',
                        borderRight: '1px solid var(--color-border)',
                        color: 'var(--color-text-muted)',
                        fontSize: '0.72rem',
                      }}
                    >
                      {absoluteIndex}
                    </td>
                    {colNames.map(col => (
                      <td
                        key={col}
                        style={{
                          padding: '4px 12px',
                          whiteSpace: 'nowrap',
                          borderBottom: '1px solid var(--color-border-subtle)',
                          borderRight: '1px solid var(--color-border-subtle)',
                          color: row[col] == null ? 'var(--color-text-muted)' : 'var(--color-text)',
                        }}
                      >
                        {row[col] == null ? 'null' : String(row[col])}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination footer */}
        <div
          className="flex items-center justify-between px-3 py-2"
          style={{
            borderTop: '1px solid var(--color-border)',
            background: 'var(--color-surface-2)',
          }}
        >
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--color-text-muted)' }}>
            Rows {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, preview.length)} of {preview.length} previewed
            {row_count > preview.length && (
              <span> ({row_count.toLocaleString()} total in dataset)</span>
            )}
          </span>
          {totalPages > 1 && (
            <div className="flex items-center gap-1">
              <PaginationBtn
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
              >
                ‹
              </PaginationBtn>
              {Array.from({ length: totalPages }, (_, i) => (
                <PaginationBtn
                  key={i}
                  onClick={() => setPage(i)}
                  active={i === page}
                >
                  {i + 1}
                </PaginationBtn>
              ))}
              <PaginationBtn
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page === totalPages - 1}
              >
                ›
              </PaginationBtn>
            </div>
          )}
        </div>
      </div>

      {/* Prompt hint */}
      <p
        style={{
          margin: 0,
          fontFamily: 'var(--font-mono)',
          fontSize: '0.78rem',
          color: 'var(--color-text-muted)',
        }}
      >
        ↓ Enter a query below to run the pipeline
      </p>
    </div>
  )
}

function PaginationBtn({
  children,
  onClick,
  disabled,
  active,
}: {
  children: React.ReactNode
  onClick: () => void
  disabled?: boolean
  active?: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        width: 24, height: 24,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'var(--font-mono)', fontSize: '0.75rem',
        borderRadius: 3,
        border: '1px solid var(--color-border)',
        background: active ? 'var(--color-accent-subtle)' : 'transparent',
        color: active ? 'var(--color-accent)' : disabled ? 'var(--color-text-muted)' : 'var(--color-text-soft)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.4 : 1,
      }}
    >
      {children}
    </button>
  )
}
