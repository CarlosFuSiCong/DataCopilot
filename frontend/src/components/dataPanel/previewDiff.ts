export type DiffRowType = 'kept' | 'removed' | 'added'

export interface DiffTableRow {
  type: DiffRowType
  data: Record<string, unknown>
  originalData?: Record<string, unknown>
}

export function buildPreviewDiff(
  originalRows: Record<string, unknown>[],
  resultRows: Record<string, unknown>[],
  originalCols: string[],
  resultCols: string[],
  sameRowCount: boolean,
): DiffTableRow[] {
  if (sameRowCount) {
    const maxLen = Math.max(originalRows.length, resultRows.length)
    const out: DiffTableRow[] = []
    for (let i = 0; i < maxLen; i++) {
      const orig = originalRows[i]
      const res = resultRows[i]
      if (orig && res) out.push({ type: 'kept', data: res, originalData: orig })
      else if (orig) out.push({ type: 'removed', data: orig })
      else if (res) out.push({ type: 'added', data: res })
    }
    return out
  }

  const sharedCols = resultCols.filter(c => originalCols.includes(c))
  const makeKey = (row: Record<string, unknown>) =>
    sharedCols.map(c => String(row[c] ?? '')).join('|')

  const resultMap = new Map<string, { row: Record<string, unknown>; used: boolean }>()
  for (const row of resultRows) {
    const k = makeKey(row)
    if (!resultMap.has(k)) resultMap.set(k, { row, used: false })
  }

  const out: DiffTableRow[] = []
  for (const row of originalRows) {
    const entry = resultMap.get(makeKey(row))
    if (entry && !entry.used) {
      out.push({ type: 'kept', data: entry.row, originalData: row })
      entry.used = true
    } else {
      out.push({ type: 'removed', data: row })
    }
  }
  for (const entry of resultMap.values()) {
    if (!entry.used) out.push({ type: 'added', data: entry.row })
  }
  return out
}

/** Paginated execute-diff rows: original cells + `_kept`. */
export function mapDiffApiRows(rows: (Record<string, unknown> & { _kept: boolean })[]): DiffTableRow[] {
  return rows.map(r => {
    const { _kept: kept, ...rest } = r
    return kept
      ? { type: 'kept', data: rest, originalData: rest }
      : { type: 'removed', data: rest }
  })
}
