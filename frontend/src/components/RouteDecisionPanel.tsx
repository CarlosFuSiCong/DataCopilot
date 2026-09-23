import { useState } from 'react'

interface RouteDecisionPanelProps {
  routeDecision: Record<string, unknown>
}

export function RouteDecisionPanel({ routeDecision: rd }: RouteDecisionPanelProps) {
  const [open, setOpen] = useState(false)

  const route = rd.route as string | undefined
  const queryType = rd.query_type as string | undefined
  const confidence = rd.confidence != null ? `${(Number(rd.confidence) * 100).toFixed(0)}%` : '—'
  const reason = rd.reason as string | undefined
  const selectedTool = (rd.selected_tool as string | null | undefined) ?? '—'
  const fallbackRoute = (rd.fallback_route as string | null | undefined) ?? '—'
  const evidence = rd.evidence as string[] | undefined

  const rows: [string, string][] = [
    ['route', route ?? '—'],
    ['query_type', queryType ?? '—'],
    ['confidence', confidence],
    ['reason', reason ?? '—'],
    ['selected_tool', selectedTool],
    ['fallback_route', fallbackRoute],
  ]

  return (
    <div style={{
      border: '1px solid var(--color-border)',
      borderRadius: 6,
      overflow: 'hidden',
      background: 'var(--color-surface-1)',
    }}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          width: '100%',
          padding: '6px 10px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
          fontFamily: 'var(--font-mono)',
          fontSize: '0.72rem',
          color: 'var(--color-text-muted)',
        }}
      >
        <span style={{
          fontSize: '0.58rem',
          display: 'inline-block',
          transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
          transition: 'transform 0.15s',
        }}>▶</span>
        <span>Route Decision Debug</span>
        {!open && route && (
          <span style={{ marginLeft: 'auto', color: 'var(--color-accent)', fontSize: '0.68rem' }}>
            {route}
            {queryType ? ` · ${queryType}` : ''}
          </span>
        )}
      </button>

      {open && (
        <div style={{
          padding: '8px 12px 10px',
          borderTop: '1px solid var(--color-border)',
          display: 'grid',
          gridTemplateColumns: 'auto 1fr',
          gap: '5px 12px',
          fontSize: '0.76rem',
          fontFamily: 'var(--font-mono)',
        }}>
          {rows.map(([label, value]) => (
            <div key={label} style={{ display: 'contents' }}>
              <span style={{ color: 'var(--color-text-muted)', whiteSpace: 'nowrap', alignSelf: 'start' }}>
                {label}
              </span>
              <span style={{ color: 'var(--color-text)', wordBreak: 'break-word' }}>
                {value}
              </span>
            </div>
          ))}
          {evidence && evidence.length > 0 && (
            <>
              <span style={{ color: 'var(--color-text-muted)', whiteSpace: 'nowrap', alignSelf: 'start' }}>
                evidence
              </span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {evidence.map(e => (
                  <span key={e} style={{
                    background: 'var(--color-surface-2)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 4,
                    padding: '1px 6px',
                    fontSize: '0.7rem',
                    color: 'var(--color-accent)',
                  }}>
                    {e}
                  </span>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
