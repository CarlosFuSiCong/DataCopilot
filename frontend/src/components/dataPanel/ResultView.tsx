import { useCallback, useEffect, useRef, useState } from 'react'
import type { ExecutionResult, UploadResponse, WorkflowStep } from '../../types'
import { fetchDiffRows, fetchResultRows } from '../../api/client'
import {
  RESULT_DELTA_BADGE_MIN_HEADER_PX,
  RESULT_PAGE_SIZE,
} from './constants'
import { formatDatasetDims } from './formatDatasetDims'
import { buildPreviewDiff, mapDiffApiRows, type DiffTableRow } from './previewDiff'
import {
  backBtnStyle,
  browseBtnStyle,
  PanelTableFooter,
  td,
  tdIdx,
  th,
  thIdx,
} from './tablePrimitives'

export function ResultView({
  result,
  dataset,
  datasetId,
  steps,
  compactDims,
}: {
  result: ExecutionResult
  dataset: UploadResponse
  datasetId: string
  steps: WorkflowStep[]
  compactDims: boolean
}) {
  const pageSize = RESULT_PAGE_SIZE

  const [mode, setMode] = useState<'preview' | 'full'>('preview')
  const [offset, setOffset] = useState(0)
  const [rows, setRows] = useState(result.preview)
  const [total, setTotal] = useState(result.row_count)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showDiff, setShowDiff] = useState(false)
  const [fullDiffRows, setFullDiffRows] = useState<DiffTableRow[]>([])
  const [diffOriginalTotal, setDiffOriginalTotal] = useState(0)
  const [diffOffset, setDiffOffset] = useState(0)
  const headerToolbarRef = useRef<HTMLDivElement>(null)
  const [showDeltaBadge, setShowDeltaBadge] = useState(true)

  const originalCols = dataset.columns.map(c => c.name)
  const resultColSet = new Set(result.columns)
  const originalColSet = new Set(originalCols)
  const addedCols = result.columns.filter(c => !originalColSet.has(c))
  const removedCols = originalCols.filter(c => !resultColSet.has(c))
  const allCols = [...result.columns, ...removedCols]

  const rowDelta = result.row_count - dataset.row_count
  const colDelta = result.column_count - dataset.column_count

  const fetchPage = useCallback(async (off: number) => {
    setLoading(true); setError(null)
    try {
      const resp = await fetchResultRows(datasetId, steps, off, pageSize)
      setRows(resp.rows); setTotal(resp.total_rows); setOffset(off)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally { setLoading(false) }
  }, [datasetId, steps, pageSize])

  const fetchDiffPage = useCallback(async (off: number) => {
    setLoading(true); setError(null)
    try {
      const resp = await fetchDiffRows(datasetId, steps, off, pageSize)
      setFullDiffRows(mapDiffApiRows(resp.rows))
      setDiffOriginalTotal(resp.total_original)
      setDiffOffset(resp.offset)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load diff')
    } finally { setLoading(false) }
  }, [datasetId, steps, pageSize])

  useEffect(() => {
    if (mode !== 'full') return
    if (showDiff) {
      fetchDiffPage(0)
      return
    }
    if (rows === result.preview) fetchPage(0)
  }, [mode, showDiff]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const el = headerToolbarRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const apply = (w: number) => {
      setShowDeltaBadge(w >= RESULT_DELTA_BADGE_MIN_HEADER_PX)
    }
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? el.offsetWidth
      apply(w)
    })
    ro.observe(el)
    apply(el.offsetWidth)
    return () => ro.disconnect()
  }, [])

  const totalPages = Math.ceil(total / pageSize)
  const currentPage = Math.floor(offset / pageSize)
  const diffTotalPages = Math.ceil(diffOriginalTotal / pageSize)
  const diffCurrentPage = Math.floor(diffOffset / pageSize)

  const previewDiffRows = buildPreviewDiff(
    dataset.preview,
    result.preview,
    originalCols,
    result.columns,
    result.row_count === dataset.row_count,
  )

  const previewLen = result.preview.length

  const rowsRangeLabel = (from: number, to: number, ofTotal: number) =>
    `Rows ${from.toLocaleString()}\u2013${to.toLocaleString()} of ${ofTotal.toLocaleString()}`

  const subtitleShort =
    showDiff && mode === 'preview'
      ? 'diff · preview'
      : showDiff && mode === 'full'
        ? loading
          ? '…'
          : `diff · ${rowsRangeLabel(
              diffOffset + 1,
              Math.min(diffOffset + pageSize, diffOriginalTotal),
              diffOriginalTotal,
            )}`
        : mode === 'preview'
          ? previewLen < result.row_count
            ? `Preview · first ${previewLen} rows`
            : null
          : loading
            ? '…'
            : rowsRangeLabel(offset + 1, Math.min(offset + pageSize, total), total)

  let vsUploadLong: string
  let vsUploadShort: string
  const shapeExtras: string[] = []
  if (addedCols.length === 1) shapeExtras.push(`+${addedCols[0]}`)
  else if (addedCols.length > 1) shapeExtras.push(`+${addedCols.length}`)
  if (removedCols.length === 1) shapeExtras.push(`−${removedCols[0]}`)
  else if (removedCols.length > 1) shapeExtras.push(`−${removedCols.length}`)

  if (rowDelta === 0 && colDelta === 0 && shapeExtras.length === 0) {
    vsUploadLong =
      `same as upload · ${dataset.row_count.toLocaleString()} rows · ${dataset.column_count} cols`
    vsUploadShort = 'same'
  } else {
    const rowSeg =
      rowDelta === 0
        ? `${result.row_count.toLocaleString()} rows`
        : `${dataset.row_count.toLocaleString()}\u2192${result.row_count.toLocaleString()} rows`
    const colSeg =
      colDelta === 0
        ? `${result.column_count} cols`
        : `${dataset.column_count}\u2192${result.column_count} cols`
    vsUploadLong =
      shapeExtras.length > 0 ? `${rowSeg} · ${colSeg} · ${shapeExtras.join(' · ')}` : `${rowSeg} · ${colSeg}`

    const brief: string[] = []
    if (rowDelta !== 0) brief.push(`${dataset.row_count}\u2192${result.row_count}`)
    if (colDelta !== 0) brief.push(`${dataset.column_count}\u2192${result.column_count}`)
    if (shapeExtras.length > 0) brief.push(shapeExtras.join(' · '))
    vsUploadShort = brief.join(' · ')
  }

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ padding: '16px 20px 0' }}>
      <div
        ref={headerToolbarRef}
        className="flex items-center justify-between gap-2 shrink-0 min-w-0 w-full"
        style={{ flexWrap: 'nowrap', paddingBottom: 8 }}
      >
        <div
          className="flex items-center gap-2 min-w-0 flex-1"
          style={{ flexWrap: 'nowrap', overflow: 'hidden' }}
        >
          <span
            style={{
              flex: '1 1 0%',
              minWidth: 0,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.85rem',
              color: 'var(--color-accent)',
              fontWeight: 600,
            }}
            title={dataset.filename}
          >
            {dataset.filename}
          </span>
          {showDeltaBadge && (
            <span
              className="px-2 py-0.5 rounded shrink-0"
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '0.68rem',
                background: 'rgba(74,158,255,0.06)',
                color: 'var(--color-blue)',
                border: '1px solid var(--color-border-subtle)',
                whiteSpace: 'nowrap',
                maxWidth: 'min(160px, 32vw)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
              title={vsUploadLong}
            >
              {vsUploadShort}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0" style={{ flexWrap: 'nowrap' }}>
          {mode === 'preview' && result.row_count > previewLen && (
            <button
              type="button"
              onClick={() => setMode('full')}
              style={browseBtnStyle()}
              title={`Browse all ${result.row_count.toLocaleString()} rows`}
            >
              {compactDims ? 'Browse all' : `Browse all ${result.row_count.toLocaleString()} rows`}
            </button>
          )}
          {mode === 'full' && (
            <button
              type="button"
              onClick={() => {
                setMode('preview')
                setRows(result.preview)
                setTotal(result.row_count)
                setOffset(0)
              }}
              style={backBtnStyle()}
              title="Back to preview"
            >
              {compactDims ? '← Back' : '← Back to preview'}
            </button>
          )}
          <button
            type="button"
            onClick={() => setShowDiff(v => !v)}
            style={{
              padding: '3px 10px',
              borderRadius: 3,
              background: showDiff ? 'rgba(220,220,170,0.12)' : 'transparent',
              border: `1px solid ${showDiff ? 'var(--color-yellow)' : 'var(--color-border)'}`,
              color: showDiff ? 'var(--color-yellow)' : 'var(--color-text-soft)',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.72rem',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              fontWeight: showDiff ? 600 : 400,
            }}
            title={showDiff ? 'Hide diff' : 'Show diff'}
          >
            {compactDims ? (showDiff ? '⊖' : '⊕') : (showDiff ? '⊖ Hide diff' : '⊕ Show diff')}
          </button>
        </div>
      </div>

      {subtitleShort !== null && (
        <span
          className="shrink-0 block"
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.7rem',
            color: 'var(--color-text-muted)',
            paddingBottom: 10,
          }}
        >
          {subtitleShort}
        </span>
      )}

      {error && (
        <p className="shrink-0" style={{ margin: '0 0 6px', fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--color-red)' }}>
          ✕ {error}
        </p>
      )}

      <div
        className="flex flex-col flex-1 rounded overflow-hidden"
        style={{ border: '1px solid var(--color-border)', minHeight: 0, opacity: loading ? 0.6 : 1 }}
      >
        <div style={{ flex: 1, overflowY: 'auto', overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', fontFamily: 'var(--font-mono)', fontSize: '0.82rem' }}>
            <thead style={{ position: 'sticky', top: 0, zIndex: 1 }}>
              <tr style={{ background: 'var(--color-surface-2)' }}>
                <th style={thIdx()}>#</th>
                {allCols.map(col => {
                  const isRemoved = removedCols.includes(col)
                  const isAdded = addedCols.includes(col)
                  return (
                    <th key={col} style={{
                      ...th(),
                      color: isRemoved ? '#f48771' : isAdded ? '#4ec97a' : 'var(--color-accent)',
                      textDecoration: isRemoved ? 'line-through' : 'none',
                      opacity: isRemoved ? 0.55 : 1,
                      background: isAdded ? 'rgba(78,201,122,0.07)' : isRemoved ? 'rgba(244,135,113,0.07)' : 'var(--color-surface-2)',
                    }}>
                      {col}{isRemoved && <span style={{ fontSize: '0.62rem', marginLeft: 4, fontWeight: 400 }}>(removed)</span>}
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {showDiff
                ? (mode === 'preview' ? previewDiffRows : fullDiffRows).map((drow, i) => {
                  const rowIndex = mode === 'preview' ? i : diffOffset + i
                  const rowBg =
                    drow.type === 'removed' ? 'rgba(244,135,113,0.1)' :
                    drow.type === 'added' ? 'rgba(78,201,122,0.1)' :
                    i % 2 === 0 ? 'transparent' : 'var(--color-surface-2)'
                  const diffMark =
                    drow.type === 'kept' ? '·' : drow.type === 'removed' ? '✗' : '+'
                  const markColor =
                    drow.type === 'kept'
                      ? 'var(--color-text-muted)'
                      : drow.type === 'removed'
                        ? '#f48771'
                        : '#4ec97a'
                  return (
                    <tr key={`${mode}-${rowIndex}-${i}`} style={{ background: rowBg, opacity: drow.type === 'removed' ? 0.7 : 1 }}>
                      <td style={{ ...tdIdx(), whiteSpace: 'nowrap' }}>
                        <span style={{ color: markColor, fontWeight: 600, marginRight: 6 }}>{diffMark}</span>
                        <span style={{ color: 'var(--color-text-muted)', fontWeight: 400 }}>{rowIndex}</span>
                      </td>
                      {allCols.map(col => {
                        const isRemoved = removedCols.includes(col)
                        const cellVal = isRemoved ? drow.originalData?.[col] : drow.data[col]
                        const origVal = drow.originalData?.[col]
                        const changed = mode === 'preview' && drow.type === 'kept' && !isRemoved && String(origVal ?? '') !== String(drow.data[col] ?? '') && origVal !== undefined
                        return (
                          <td key={col} style={{
                            ...td(false),
                            textDecoration: (drow.type === 'removed' || isRemoved) ? 'line-through' : 'none',
                            background: changed ? 'rgba(220,220,170,0.15)' : 'transparent',
                            color: isRemoved ? 'var(--color-text-muted)'
                              : drow.type === 'removed' ? '#f48771'
                              : drow.type === 'added' ? '#4ec97a'
                              : changed ? 'var(--color-yellow)'
                              : cellVal == null ? 'var(--color-text-muted)' : 'var(--color-text)',
                            opacity: isRemoved ? 0.4 : 1,
                          }}>
                            {isRemoved ? '—' : cellVal == null ? 'null' : String(cellVal)}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })
                : rows.map((row, i) => (
                    <tr key={offset + i} style={{ background: i % 2 === 0 ? 'transparent' : 'var(--color-surface-2)' }}>
                      <td style={tdIdx()}>{offset + i}</td>
                      {allCols.map(col => {
                        const isRemoved = removedCols.includes(col)
                        return (
                          <td key={col} style={{
                            ...td(isRemoved || row[col] == null),
                            color: isRemoved ? 'var(--color-text-muted)' : row[col] == null ? 'var(--color-text-muted)' : 'var(--color-text)',
                            opacity: isRemoved ? 0.35 : 1,
                            fontStyle: isRemoved ? 'italic' : 'normal',
                          }}>
                            {isRemoved ? '—' : row[col] == null ? 'null' : String(row[col])}
                          </td>
                        )
                      })}
                    </tr>
                  ))
              }
            </tbody>
          </table>
        </div>
        <PanelTableFooter
          label={
            showDiff && mode === 'preview'
              ? `diff preview · ${dataset.preview.length} rows`
              : showDiff && mode === 'full'
                ? `diff · ${diffOriginalTotal.toLocaleString()} rows · p.${diffTotalPages ? diffCurrentPage + 1 : 1}/${Math.max(1, diffTotalPages)}`
                : mode === 'full'
                  ? `${currentPage + 1}/${totalPages} · ${total.toLocaleString()} rows`
                  : formatDatasetDims(total, result.column_count, compactDims)
          }
          page={
            mode === 'full' && showDiff ? diffCurrentPage
              : mode === 'full' ? currentPage
              : undefined
          }
          totalPages={
            mode === 'full' && showDiff ? Math.max(1, diffTotalPages)
              : mode === 'full' ? totalPages
              : undefined
          }
          onPageChange={
            mode === 'full' && showDiff ? p => fetchDiffPage(p * pageSize)
              : mode === 'full' ? p => fetchPage(p * pageSize)
              : undefined
          }
          disabled={loading}
        />
      </div>
    </div>
  )
}
