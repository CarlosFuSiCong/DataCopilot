import type { ChatResponse } from '../types'

interface ModeInfo {
  label: string
  color: string
  bg: string
}

function getRouteModeInfo(result: ChatResponse | undefined, cellStatus: string): ModeInfo | null {
  if (!result) return null
  const route = result.route_decision?.route as string | undefined

  if (cellStatus === 'clarifying' || result.needs_clarification) {
    return { label: 'Clarification', color: 'var(--color-blue)', bg: 'rgba(97,175,239,0.08)' }
  }
  if (route === 'ask_mode' || result.is_read_only) {
    return { label: 'Ask Mode', color: 'var(--color-accent)', bg: 'rgba(152,195,121,0.08)' }
  }
  if (route === 'deterministic_tool') {
    return { label: 'Deterministic', color: '#7c9fcb', bg: 'rgba(124,159,203,0.08)' }
  }
  if (route === 'unsupported') {
    return { label: 'Unsupported', color: 'var(--color-red)', bg: 'rgba(224,108,117,0.08)' }
  }
  if (route === 'clarification') {
    return { label: 'Clarification', color: 'var(--color-blue)', bg: 'rgba(97,175,239,0.08)' }
  }
  if (route === 'llm_planner' || !route) {
    return { label: 'LLM Planner', color: '#c678dd', bg: 'rgba(198,120,221,0.08)' }
  }
  return null
}

function getStateModeInfo(state: string | undefined): ModeInfo | null {
  if (state === 'executed') {
    return { label: 'Executed', color: 'var(--color-accent)', bg: 'rgba(152,195,121,0.1)' }
  }
  if (state === 'preview_ready') {
    return { label: 'Preview', color: 'var(--color-yellow)', bg: 'rgba(229,192,123,0.08)' }
  }
  if (state === 'warning_review') {
    return { label: 'Warning', color: 'var(--color-yellow)', bg: 'rgba(229,192,123,0.08)' }
  }
  return null
}

const pillStyle = (color: string, bg: string): React.CSSProperties => ({
  borderRadius: 999,
  padding: '2px 8px',
  fontFamily: 'var(--font-mono)',
  fontSize: '0.68rem',
  border: `1px solid ${color}`,
  color,
  background: bg,
  letterSpacing: '0.04em',
  whiteSpace: 'nowrap' as const,
})

interface ModeBadgeProps {
  result?: ChatResponse
  cellStatus: string
}

export function ModeBadge({ result, cellStatus }: ModeBadgeProps) {
  const routeMode = getRouteModeInfo(result, cellStatus)
  const stateMode = getStateModeInfo(result?.state)

  if (!routeMode && !stateMode) return null

  return (
    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center' }}>
      {routeMode && (
        <span style={pillStyle(routeMode.color, routeMode.bg)}>
          {routeMode.label}
        </span>
      )}
      {stateMode && (
        <span style={pillStyle(stateMode.color, stateMode.bg)}>
          {stateMode.label}
        </span>
      )}
      {result?.is_read_only && (
        <span style={pillStyle('var(--color-text-muted)', 'transparent')}>
          read-only
        </span>
      )}
    </div>
  )
}
