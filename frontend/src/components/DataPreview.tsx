import { useCallback, useEffect, useState } from 'react'
import type { UploadResponse } from '../types'
import { fetchDatasetRows, downloadDataset } from '../api/client'

interface DataPreviewProps {
  dataset: UploadResponse
}

const PREVIEW_PAGE_SIZE = 5
const FULL_PAGE_SIZE = 50

export function DataPreview({ dataset }: DataPreviewProps) {
  const [mode, setMode] = useState<'preview' | 'full'>('preview')

  // ── preview mode state (client-side, over the small preview array) ──────
  const [previewPage, setPreviewPage] = useState(0)

  // ── full-browse mode state (server-side pagination) ──────────────────────
  const [fullOffset, setFullOffset] = useState(0)
  const [fullRows, setFullRows] = useState<Record<string, unknown>[]>([])
  const [fullTotal, setFullTotal] = useState(dataset.row_count)
  const [loading, setLoading] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)

  const { filename, row_count, column_count, columns, preview, dataset_id } = dataset
  const colNames = columns.map(c => c.name)

  // Fetch a page of full rows from the backend
  const fetchPage = useCallback(
    async (offset: number) => {
      setLoading(true)
      setFetchError(null)
      try {
        const resp = await fetchDatasetRows(dataset_id, offset, FULL_PAGE_SIZE)
        setFullRows(resp.rows)
        setFullTotal(resp.total_rows)
        setFullOffset(offset)
      } catch (err) {
        setFetchError(err instanceof Error ? err.message : 'Failed to load rows.')
      } finally {
        setLoading(false)
      }
    },
    [dataset_id],
  )

  // Load the first page when entering full mode
  useEffect(() => {
    if (mode === 'full' && fullRows.length === 0) {
      fetchPage(0)
    }
  }, [mode, fullRows.length, fetchPage])

  // ── preview-mode pagination ───────────────────────────────────────────────
  const totalPreviewPages = Math.ceil(preview.length / PREVIEW_PAGE_SIZE)
  const pageRows = preview.slice(
    previewPage * PREVIEW_PAGE_SIZE,
    (previewPage + 1) * PREVIEW_PAGE_SIZE,
  )

  // ── full-mode pagination ──────────────────────────────────────────────────
  const fullTotalPages = Math.ceil(fullTotal / FULL_PAGE_SIZE)
  const fullCurrentPage = Math.floor(fullOffset / FULL_PAGE_SIZE)

  const rows = mode === 'preview' ? pageRows : fullRows
  const rowIndexBase = mode === 'preview' ? previewPage * PREVIEW_PAGE_SIZE : fullOffset

  return (
    <div className="flex flex-col gap-3 p-6 flex-1 overflow-y-auto">
      {/* ── Header ── */}
      <div className="flex items-center justify-between flex-wrap gap-2">
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

        {/* Download + mode toggle */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => downloadDataset(dataset_id)}
            style={{
              padding: '3px 10px', borderRadius: 3,
              background: 'transparent',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-soft)',
              fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
              cursor: 'pointer',
            }}
          >
            ↓ Download CSV
          </button>
          {mode === 'preview' ? (
            <button
              onClick={() => setMode('full')}
              style={{
                padding: '3px 10px', borderRadius: 3,
                background: 'var(--color-accent-subtle)',
                border: '1px solid var(--color-accent-dim)',
                color: 'var(--color-accent)',
                fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
                cursor: 'pointer',
              }}
            >
              Browse all {row_count.toLocaleString()} rows
            </button>
          ) : (
            <button
              onClick={() => setMode('preview')}
              style={{
                padding: '3px 10px', borderRadius: 3,
                background: 'transparent',
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-soft)',
                fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
                cursor: 'pointer',
              }}
            >
              ← Back to preview
            </button>
          )}
        </div>
      </div>

      {/* ── Mode label ── */}
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '0.72rem',
          color: 'var(--color-text-muted)',
        }}
      >
        {mode === 'preview'
          ? `Preview · first ${preview.length} rows`
          : loading
            ? 'Loading…'
            : `Rows ${fullOffset + 1}–${Math.min(fullOffset + FULL_PAGE_SIZE, fullTotal).toLocaleString()} of ${fullTotal.toLocaleString()}`}
      </span>

      {/* ── Error banner ── */}
      {fetchError && (
        <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--color-red)', fontFamily: 'var(--font-mono)' }}>
          ✕ {fetchError}
        </p>
      )}

      {/* ── Table ── */}
      <div className="rounded overflow-hidden" style={{ border: '1px solid var(--color-border)', opacity: loading ? 0.5 : 1 }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', fontFamily: 'var(--font-mono)', fontSize: '0.82rem' }}>
            <thead>
              <tr style={{ background: 'var(--color-surface-2)' }}>
                <th
                  style={{
                    padding: '6px 10px', textAlign: 'right',
                    borderBottom: '1px solid var(--color-border)',
                    borderRight: '1px solid var(--color-border)',
                    color: 'var(--color-text-muted)', fontWeight: 400, minWidth: 40,
                  }}
                >
                  #
                </th>
                {colNames.map(col => (
                  <th
                    key={col}
                    style={{
                      padding: '6px 12px', textAlign: 'left', whiteSpace: 'nowrap',
                      borderBottom: '1px solid var(--color-border)',
                      borderRight: '1px solid var(--color-border-subtle)',
                      color: 'var(--color-blue)', fontWeight: 500,
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
              {rows.map((row, i) => {
                const absoluteIndex = rowIndexBase + i
                return (
                  <tr
                    key={absoluteIndex}
                    style={{ background: i % 2 === 0 ? 'transparent' : 'var(--color-surface-2)' }}
                  >
                    <td
                      style={{
                        padding: '4px 10px', textAlign: 'right',
                        borderBottom: '1px solid var(--color-border-subtle)',
                        borderRight: '1px solid var(--color-border)',
                        color: 'var(--color-text-muted)', fontSize: '0.72rem',
                      }}
                    >
                      {absoluteIndex}
                    </td>
                    {colNames.map(col => (
                      <td
                        key={col}
                        style={{
                          padding: '4px 12px', whiteSpace: 'nowrap',
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
              {rows.length === 0 && !loading && (
                <tr>
                  <td
                    colSpan={colNames.length + 1}
                    style={{ padding: '12px', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: '0.78rem' }}
                  >
                    No rows to display.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* ── Pagination footer ── */}
        <div
          className="flex items-center justify-between px-3 py-2"
          style={{ borderTop: '1px solid var(--color-border)', background: 'var(--color-surface-2)' }}
        >
          {mode === 'preview' ? (
            <>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--color-text-muted)' }}>
                Rows {previewPage * PREVIEW_PAGE_SIZE + 1}–{Math.min((previewPage + 1) * PREVIEW_PAGE_SIZE, preview.length)} of {preview.length} previewed
                {row_count > preview.length && (
                  <span> ({row_count.toLocaleString()} total in dataset)</span>
                )}
              </span>
              {totalPreviewPages > 1 && (
                <PaginationControls
                  page={previewPage}
                  totalPages={totalPreviewPages}
                  onPageChange={setPreviewPage}
                />
              )}
            </>
          ) : (
            <>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--color-text-muted)' }}>
                Page {fullCurrentPage + 1} of {fullTotalPages} · {fullTotal.toLocaleString()} total rows
              </span>
              <PaginationControls
                page={fullCurrentPage}
                totalPages={fullTotalPages}
                onPageChange={p => fetchPage(p * FULL_PAGE_SIZE)}
                disabled={loading}
              />
            </>
          )}
        </div>
      </div>

      {/* ── Prompt hint ── */}
      {mode === 'preview' && (
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
      )}
    </div>
  )
}

// ── Shared pagination controls ────────────────────────────────────────────────

function PaginationControls({
  page,
  totalPages,
  onPageChange,
  disabled = false,
}: {
  page: number
  totalPages: number
  onPageChange: (page: number) => void
  disabled?: boolean
}) {
  // Show at most 5 page buttons centred around current page
  const window = 2
  const start = Math.max(0, page - window)
  const end = Math.min(totalPages - 1, page + window)
  const pageNums = Array.from({ length: end - start + 1 }, (_, i) => start + i)

  return (
    <div className="flex items-center gap-1">
      <PaginationBtn onClick={() => onPageChange(0)} disabled={disabled || page === 0}>«</PaginationBtn>
      <PaginationBtn onClick={() => onPageChange(page - 1)} disabled={disabled || page === 0}>‹</PaginationBtn>
      {start > 0 && <span style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', padding: '0 2px' }}>…</span>}
      {pageNums.map(p => (
        <PaginationBtn key={p} onClick={() => onPageChange(p)} active={p === page} disabled={disabled}>
          {p + 1}
        </PaginationBtn>
      ))}
      {end < totalPages - 1 && <span style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', padding: '0 2px' }}>…</span>}
      <PaginationBtn onClick={() => onPageChange(page + 1)} disabled={disabled || page === totalPages - 1}>›</PaginationBtn>
      <PaginationBtn onClick={() => onPageChange(totalPages - 1)} disabled={disabled || page === totalPages - 1}>»</PaginationBtn>
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
