import { useCallback, useEffect, useRef, useState } from 'react'
import type { ExecutionResult } from '../../types'
import { PANEL_DIMS_COMPACT_BREAKPOINT_PX } from './constants'

/**
 * Track middle-panel width vs toggle bar width; compact UI when the narrower edge is below breakpoint.
 */
export function useCompactPanelDims(datasetId: string | undefined, lastExecutionResult: ExecutionResult | null) {
  const panelMeasureRef = useRef<HTMLDivElement>(null)
  const viewToggleBarRef = useRef<HTMLDivElement>(null)
  const [compactDims, setCompactDims] = useState(false)

  const recomputeCompactDims = useCallback(() => {
    const panelEl = panelMeasureRef.current
    if (!panelEl) return
    const pw = panelEl.getBoundingClientRect().width
    const toggleEl = viewToggleBarRef.current
    const tw = toggleEl?.getBoundingClientRect().width
    const w = tw != null && tw > 0 ? Math.min(pw, tw) : pw
    setCompactDims(w < PANEL_DIMS_COMPACT_BREAKPOINT_PX)
  }, [])

  useEffect(() => {
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => {
      recomputeCompactDims()
    })
    const p = panelMeasureRef.current
    const v = viewToggleBarRef.current
    if (p) ro.observe(p)
    if (v) ro.observe(v)
    recomputeCompactDims()
    const id = requestAnimationFrame(recomputeCompactDims)
    return () => {
      cancelAnimationFrame(id)
      ro.disconnect()
    }
  }, [recomputeCompactDims, datasetId, lastExecutionResult])

  return { panelMeasureRef, viewToggleBarRef, compactDims }
}
