import type { ChatResponse } from '../types'
import { ModeBadge } from './ModeBadge'

interface CellStatusHeaderProps {
  result?: ChatResponse
  cellStatus: string
}

function percent(value: unknown): string | null {
  if (typeof value !== 'number') return null
  return `${Math.round(value * 100)}% confidence`
}

function textValue(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null
}

export function CellStatusHeader({ result, cellStatus }: CellStatusHeaderProps) {
  const decision = result?.route_decision ?? {}
  const confidence = percent(decision.confidence)
  const tool = textValue(decision.selected_tool)
  const queryType = textValue(decision.query_type)

  return (
    <div
      data-testid="cell-status-header"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        marginBottom: 8,
        flexWrap: 'wrap',
      }}
    >
      <span style={{ color: 'var(--color-accent)', fontSize: '0.8rem', lineHeight: 1 }}>◉</span>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '0.7rem',
          color: 'var(--color-text-muted)',
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
        }}
      >
        DataCopilot
      </span>
      <ModeBadge result={result} cellStatus={cellStatus} />
      {tool && <HeaderPill label={tool} tone="tool" />}
      {queryType && <HeaderPill label={queryType} tone="muted" />}
      {confidence && <HeaderPill label={confidence} tone="confidence" />}
    </div>
  )
}

function HeaderPill({ label, tone }: { label: string; tone: 'tool' | 'muted' | 'confidence' }) {
  const color = tone === 'tool'
    ? 'var(--color-blue)'
    : tone === 'confidence'
      ? 'var(--color-yellow)'
      : 'var(--color-text-muted)'

  return (
    <span
      style={{
        borderRadius: 999,
        padding: '2px 8px',
        fontFamily: 'var(--font-mono)',
        fontSize: '0.68rem',
        border: `1px solid ${color}`,
        color,
        background: 'transparent',
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </span>
  )
}
