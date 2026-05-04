export function formatDatasetDims(rows: number, cols: number, compact: boolean): string {
  const r = rows.toLocaleString()
  const c = cols.toLocaleString()
  return compact ? `${r} · ${c}` : `${r} rows · ${c} cols`
}
