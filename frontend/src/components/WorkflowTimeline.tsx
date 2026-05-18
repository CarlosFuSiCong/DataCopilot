import type { WorkflowRunState } from '../types'

interface WorkflowTimelineProps {
  state: WorkflowRunState | undefined
  hasErrors?: boolean
  hasWarnings?: boolean
}

// The canonical stage order for a workflow run.
const STAGES = [
  { id: 'plan',    label: 'Plan' },
  { id: 'validate', label: 'Validate' },
  { id: 'preview', label: 'Preview' },
  { id: 'confirm', label: 'Confirm' },
  { id: 'execute', label: 'Execute' },
  { id: 'explain', label: 'Explain' },
] as const

type StageId = typeof STAGES[number]['id']

// Map a WorkflowRunState to the highest stage that has been reached.
function stateToStage(state: WorkflowRunState | undefined): StageId {
  switch (state) {
    case 'draft':
    case 'planned':
      return 'plan'
    case 'validation_failed':
    case 'repair_attempted':
      return 'validate'
    case 'preview_ready':
    case 'warning_review':
    case 'needs_clarification':
      return 'preview'
    case 'confirmed':
      return 'confirm'
    case 'executed':
      return 'execute'
    case 'failed':
      return 'validate'
    default:
      return 'plan'
  }
}

// Whether the current state represents an error/failure at its stage.
function isErrorState(state: WorkflowRunState | undefined): boolean {
  return state === 'validation_failed' || state === 'failed'
}

type StageStatus = 'done' | 'active' | 'active-warn' | 'active-error' | 'pending'

function stageStatus(
  stageId: StageId,
  activeStage: StageId,
  isError: boolean,
  hasWarnings: boolean,
): StageStatus {
  const order = STAGES.map(s => s.id)
  const stageIdx = order.indexOf(stageId)
  const activeIdx = order.indexOf(activeStage)

  if (stageIdx < activeIdx) return 'done'
  if (stageIdx === activeIdx) {
    if (isError) return 'active-error'
    if (hasWarnings) return 'active-warn'
    return 'active'
  }
  return 'pending'
}

const STATUS_STYLE: Record<StageStatus, { bg: string; text: string; border: string; dot: string }> = {
  done:         { bg: '#f0fdf4', text: '#166534', border: '#86efac', dot: '#22c55e' },
  active:       { bg: '#eff6ff', text: '#1e40af', border: '#93c5fd', dot: '#3b82f6' },
  'active-warn':{ bg: '#fffbeb', text: '#92400e', border: '#fde68a', dot: '#f59e0b' },
  'active-error':{ bg: '#fff5f5', text: '#991b1b', border: '#fca5a5', dot: '#ef4444' },
  pending:      { bg: 'var(--color-surface-1)', text: 'var(--color-text-muted)', border: 'var(--color-border)', dot: 'var(--color-border)' },
}

export function WorkflowTimeline({ state, hasErrors = false, hasWarnings = false }: WorkflowTimelineProps) {
  const activeStage = stateToStage(state)
  const errorState = isErrorState(state) || hasErrors

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 0,
      overflowX: 'auto',
      padding: '4px 0',
      fontFamily: 'var(--font-mono)',
      fontSize: '0.75rem',
    }}>
      {STAGES.map((stage, i) => {
        const status = stageStatus(stage.id, activeStage, errorState, hasWarnings)
        const style = STATUS_STYLE[status]
        const isLast = i === STAGES.length - 1

        return (
          <div key={stage.id} style={{ display: 'flex', alignItems: 'center' }}>
            {/* Stage pill */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              padding: '3px 10px',
              borderRadius: 12,
              background: style.bg,
              border: `1px solid ${style.border}`,
              color: style.text,
              fontWeight: status === 'pending' ? 400 : 600,
              whiteSpace: 'nowrap',
            }}>
              {/* Status dot */}
              <span style={{
                display: 'inline-block',
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: style.dot,
                flexShrink: 0,
              }} />
              {stage.label}
              {status === 'done' && (
                <span style={{ fontSize: '0.65rem', marginLeft: 1 }}>✓</span>
              )}
            </div>

            {/* Connector arrow */}
            {!isLast && (
              <span style={{
                color: 'var(--color-text-muted)',
                padding: '0 3px',
                fontSize: '0.7rem',
                flexShrink: 0,
              }}>
                →
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
