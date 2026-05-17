import { useState } from 'react'
import type { AgentRunState, AgentActionType, WorkflowAttempt, WorkflowContextSummary, WorkflowRunState } from '../types'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function deriveAgentState(
  workflowState: WorkflowRunState | undefined,
  needsClarification: boolean | undefined,
  hasErrors: boolean,
): AgentRunState {
  if (needsClarification) return 'needs_clarification'
  if (workflowState === 'executed') return 'completed'
  if (workflowState === 'failed') return 'failed'
  if (workflowState === 'warning_review' || workflowState === 'preview_ready') return 'waiting_confirmation'
  if (hasErrors) return 'failed'
  return 'running'
}

function deriveStopReason(
  workflowState: WorkflowRunState | undefined,
  needsClarification: boolean | undefined,
  clarificationQuestion: string | null | undefined,
  hasErrors: boolean,
): string | null {
  if (needsClarification) return clarificationQuestion ?? 'Clarification required.'
  if (workflowState === 'executed') return 'Workflow executed successfully.'
  if (workflowState === 'failed' || hasErrors) return 'Workflow failed due to validation or execution errors.'
  if (workflowState === 'warning_review') return 'Workflow has warnings — awaiting user confirmation.'
  if (workflowState === 'preview_ready') return 'Preview ready — awaiting user confirmation.'
  return null
}

// ─── Badges ───────────────────────────────────────────────────────────────────

const STATE_BADGE: Record<AgentRunState, { label: string; color: string; bg: string }> = {
  created:              { label: 'created',       color: 'var(--color-text-muted)',  bg: 'var(--color-surface-2)' },
  running:              { label: 'running',        color: 'var(--color-accent)',      bg: 'rgba(97,175,239,0.08)' },
  needs_clarification:  { label: 'clarifying',     color: 'var(--color-blue)',        bg: 'rgba(97,175,239,0.10)' },
  waiting_confirmation: { label: 'needs confirm',  color: 'var(--color-yellow)',      bg: 'rgba(220,220,170,0.10)' },
  completed:            { label: 'completed',      color: 'var(--color-green)',       bg: 'rgba(152,195,121,0.10)' },
  failed:               { label: 'failed',         color: 'var(--color-red)',         bg: 'rgba(244,135,113,0.10)' },
  cancelled:            { label: 'cancelled',      color: 'var(--color-text-muted)',  bg: 'var(--color-surface-2)' },
  max_iterations_reached: { label: 'max iter',     color: 'var(--color-yellow)',      bg: 'rgba(220,220,170,0.10)' },
}

const ACTION_LABEL: Record<AgentActionType, string> = {
  clarify:           'clarify',
  plan_workflow:     'plan',
  preview_workflow:  'preview',
  confirm_required:  'confirm?',
  retry_preview:     'retry',
  replan_workflow:   'replan',
  select_new_tool:   'new tool',
  stop_with_result:  'done',
  stop_with_error:   'error',
}

const ACTION_COLOR: Record<AgentActionType, string> = {
  clarify:           'var(--color-blue)',
  plan_workflow:     'var(--color-accent)',
  preview_workflow:  'var(--color-accent)',
  confirm_required:  'var(--color-yellow)',
  retry_preview:     'var(--color-yellow)',
  replan_workflow:   'var(--color-yellow)',
  select_new_tool:   'var(--color-yellow)',
  stop_with_result:  'var(--color-green)',
  stop_with_error:   'var(--color-red)',
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function StateBadge({ state }: { state: AgentRunState }) {
  const s = STATE_BADGE[state] ?? STATE_BADGE.running
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      padding: '1px 7px', borderRadius: 4,
      fontFamily: 'var(--font-mono)', fontSize: '0.70rem',
      fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase',
      color: s.color, background: s.bg,
      border: `1px solid ${s.color}`,
    }}>
      {s.label}
    </span>
  )
}

function ValidationBadge({ status }: { status: 'not_run' | 'passed' | 'failed' | 'blocked' | string }) {
  const map: Record<string, { color: string; label: string }> = {
    passed:  { color: 'var(--color-green)',  label: '✓ valid' },
    repaired:{ color: 'var(--color-yellow)', label: '⚠ repaired' },
    failed:  { color: 'var(--color-red)',    label: '✗ invalid' },
    blocked: { color: 'var(--color-red)',    label: '✗ blocked' },
    not_run: { color: 'var(--color-text-muted)', label: '— not run' },
  }
  const s = map[status] ?? map.not_run
  return (
    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: s.color }}>
      {s.label}
    </span>
  )
}

function ObservationBadge({ status, warningCount, errorCount }: {
  status: string; warningCount: number; errorCount: number
}) {
  if (errorCount > 0) {
    return <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--color-red)' }}>
      ✗ {errorCount} error{errorCount > 1 ? 's' : ''}
    </span>
  }
  if (warningCount > 0) {
    return <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--color-yellow)' }}>
      ⚠ {warningCount} warning{warningCount > 1 ? 's' : ''}
    </span>
  }
  const ok = status === 'passed' || status === 'not_run'
  return <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: ok ? 'var(--color-green)' : 'var(--color-text-muted)' }}>
    {ok ? '✓ ok' : `— ${status}`}
  </span>
}

// ─── Iteration row ─────────────────────────────────────────────────────────────

function IterationRow({ attempt, isLast }: { attempt: WorkflowAttempt; isLast: boolean }) {
  const [open, setOpen] = useState(false)
  const summary = attempt.summary
  const stepTypes = attempt.parsed_steps.map(s => s.type as string)
  const actionLabel = stepTypes.length > 0
    ? ACTION_LABEL['plan_workflow']
    : ACTION_LABEL['clarify']
  const actionColor = stepTypes.length > 0
    ? ACTION_COLOR['plan_workflow']
    : ACTION_COLOR['clarify']

  return (
    <div style={{
      borderLeft: `2px solid ${isLast ? 'var(--color-accent)' : 'var(--color-border)'}`,
      paddingLeft: 10,
      paddingBottom: 6,
    }}>
      {/* Row header */}
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          display: 'flex', alignItems: 'center', gap: 8, width: '100%',
          background: 'none', border: 'none', padding: '3px 0',
          cursor: 'pointer', textAlign: 'left',
        }}
      >
        {/* Index */}
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
          color: 'var(--color-text-muted)', minWidth: 14,
        }}>
          {attempt.attempt_index + 1}
        </span>

        {/* Action badge */}
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.70rem',
          color: actionColor, minWidth: 38,
        }}>
          {actionLabel}
        </span>

        {/* Step types */}
        {stepTypes.length > 0 && (
          <div style={{ display: 'flex', gap: 4, flex: 1, flexWrap: 'wrap' }}>
            {stepTypes.slice(0, 5).map((t, i) => (
              <span key={i} style={{
                background: 'var(--color-surface-2)',
                border: '1px solid var(--color-border)',
                borderRadius: 3, padding: '0px 5px',
                fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
                color: 'var(--color-text-soft)',
              }}>{t}</span>
            ))}
            {stepTypes.length > 5 && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--color-text-muted)' }}>
                +{stepTypes.length - 5}
              </span>
            )}
          </div>
        )}

        {/* Observation */}
        <ObservationBadge
          status={summary.preview_status}
          warningCount={summary.warning_count}
          errorCount={summary.error_count}
        />

        {/* Expand arrow */}
        <span style={{
          marginLeft: 'auto', fontFamily: 'var(--font-mono)',
          fontSize: '0.65rem', color: 'var(--color-text-muted)',
        }}>
          {open ? '▲' : '▼'}
        </span>
      </button>

      {/* Expanded detail */}
      {open && (
        <div style={{
          marginTop: 6, paddingLeft: 22,
          display: 'flex', flexDirection: 'column', gap: 6,
        }}>
          {/* Validation */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.70rem', color: 'var(--color-text-muted)', minWidth: 70 }}>
              validation
            </span>
            <ValidationBadge status={summary.validation_status} />
          </div>

          {/* Observation detail */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.70rem', color: 'var(--color-text-muted)', minWidth: 70 }}>
              observation
            </span>
            <ObservationBadge
              status={summary.preview_status}
              warningCount={summary.warning_count}
              errorCount={summary.error_count}
            />
          </div>

          {/* Retrieved docs */}
          {summary.retrieved_docs && summary.retrieved_docs.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.70rem', color: 'var(--color-text-muted)', minWidth: 70 }}>
                rag docs
              </span>
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {summary.retrieved_docs.map((d, i) => (
                  <span key={i} style={{
                    background: 'var(--color-surface-2)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 3, padding: '0px 5px',
                    fontFamily: 'var(--font-mono)', fontSize: '0.62rem',
                    color: 'var(--color-text-muted)',
                  }}>{d}</span>
                ))}
              </div>
            </div>
          )}

          {/* Final status */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.70rem', color: 'var(--color-text-muted)', minWidth: 70 }}>
              outcome
            </span>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.70rem',
              color: summary.final_status === 'executed' ? 'var(--color-green)'
                : summary.final_status === 'failed' ? 'var(--color-red)'
                : 'var(--color-text-soft)',
            }}>
              {summary.final_status}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Context summary sections ─────────────────────────────────────────────────

function MonoBadge({ label, color }: { label: string; color: string }) {
  return (
    <span style={{
      display: 'inline-block',
      padding: '1px 6px', borderRadius: 3,
      fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
      color, border: `1px solid ${color}`,
      background: `${color}14`,
      whiteSpace: 'nowrap',
    }}>
      {label}
    </span>
  )
}

function ObservationSignalsRow({ signals }: { signals: string[] }) {
  if (!signals || signals.length === 0) return null
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 4 }}>
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: '0.70rem',
        color: 'var(--color-text-muted)', minWidth: 90, flexShrink: 0,
      }}>
        obs. signals
      </span>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {signals.map((s, i) => (
          <MonoBadge key={i} label={s} color="var(--color-yellow)" />
        ))}
      </div>
    </div>
  )
}

function ToolSuggestionsRow({ suggestions }: { suggestions: WorkflowContextSummary['tool_suggestions'] }) {
  if (!suggestions || suggestions.length === 0) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 4 }}>
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: '0.70rem',
        color: 'var(--color-text-muted)',
      }}>
        tool selection rationale
      </span>
      {suggestions.map((s, i) => (
        <div
          key={i}
          style={{
            display: 'flex', alignItems: 'flex-start', gap: 8,
            paddingLeft: 8,
            borderLeft: '2px solid var(--color-border)',
          }}
        >
          <MonoBadge label={s.tool_type} color="var(--color-accent)" />
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.70rem',
            color: 'var(--color-text-soft)', lineHeight: 1.5, flex: 1,
          }}>
            {s.reason}
          </span>
          {s.signal && (
            <MonoBadge label={s.signal} color="var(--color-yellow)" />
          )}
        </div>
      ))}
    </div>
  )
}

// ─── Main panel ───────────────────────────────────────────────────────────────

interface AgentTracePanelProps {
  attempts: WorkflowAttempt[]
  contextSummary: WorkflowContextSummary | null | undefined
  workflowState: WorkflowRunState | undefined
  needsClarification: boolean | undefined
  clarificationQuestion: string | null | undefined
  hasErrors: boolean
  hasWarnings: boolean
  stopReason?: string | null
}

export function AgentTracePanel({
  attempts,
  contextSummary,
  workflowState,
  needsClarification,
  clarificationQuestion,
  hasErrors,
  hasWarnings,
  stopReason,
}: AgentTracePanelProps) {
  const [expanded, setExpanded] = useState(false)

  const agentState = deriveAgentState(workflowState, needsClarification, hasErrors)
  const derivedStopReason = stopReason ?? deriveStopReason(
    workflowState, needsClarification, clarificationQuestion, hasErrors
  )

  const obsSignals = contextSummary?.last_observation?.signals ?? []
  const toolSuggestions = contextSummary?.tool_suggestions ?? []

  if (attempts.length === 0) return null

  return (
    <div style={{
      background: 'var(--color-surface)',
      border: '1px solid var(--color-border)',
      borderRadius: 8,
    }}>
      {/* Summary header */}
      <button
        onClick={() => setExpanded(v => !v)}
        style={{
          display: 'flex', alignItems: 'center', gap: 10,
          width: '100%', padding: '8px 12px',
          background: 'none', border: 'none', cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        {/* Icon */}
        <span style={{ fontSize: '0.75rem', color: 'var(--color-accent)' }}>◎</span>

        {/* Label */}
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
          color: 'var(--color-text-muted)', letterSpacing: '0.06em',
          textTransform: 'uppercase',
        }}>
          agent trace
        </span>

        {/* State badge */}
        <StateBadge state={agentState} />

        {/* Iteration count */}
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
          color: 'var(--color-text-muted)',
        }}>
          {attempts.length} iter{attempts.length !== 1 ? 's' : ''}
        </span>

        {/* Observation signal count */}
        {obsSignals.length > 0 && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.70rem', color: 'var(--color-yellow)' }}>
            ◆ {obsSignals.length} signal{obsSignals.length !== 1 ? 's' : ''}
          </span>
        )}

        {/* Warning/error count */}
        {hasErrors && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.70rem', color: 'var(--color-red)' }}>
            ✗ errors
          </span>
        )}
        {!hasErrors && hasWarnings && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.70rem', color: 'var(--color-yellow)' }}>
            ⚠ warnings
          </span>
        )}

        {/* Stop reason (truncated) */}
        {derivedStopReason && (
          <span style={{
            flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            fontFamily: 'var(--font-mono)', fontSize: '0.70rem',
            color: 'var(--color-text-muted)',
          }}>
            — {derivedStopReason}
          </span>
        )}

        {/* Expand toggle */}
        <span style={{
          marginLeft: 'auto', flexShrink: 0,
          fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
          color: 'var(--color-text-muted)',
        }}>
          {expanded ? '▲ collapse' : '▼ expand'}
        </span>
      </button>

      {/* Full trace */}
      {expanded && (
        <div style={{
          borderTop: '1px solid var(--color-border)',
          padding: '10px 12px',
          display: 'flex', flexDirection: 'column', gap: 4,
        }}>
          {/* Stop reason full text */}
          {derivedStopReason && (
            <div style={{
              padding: '6px 10px', marginBottom: 6,
              background: agentState === 'completed'   ? 'rgba(152,195,121,0.06)'
                        : agentState === 'failed'      ? 'rgba(244,135,113,0.06)'
                        : agentState === 'needs_clarification' ? 'rgba(97,175,239,0.06)'
                        : 'rgba(220,220,170,0.06)',
              border: `1px solid ${
                agentState === 'completed'   ? 'var(--color-green)'
                : agentState === 'failed'   ? 'var(--color-red)'
                : agentState === 'needs_clarification' ? 'var(--color-blue)'
                : 'var(--color-yellow)'}`,
              borderRadius: 6,
              fontFamily: 'var(--font-mono)', fontSize: '0.75rem',
              color: 'var(--color-text-soft)', lineHeight: 1.5,
            }}>
              <span style={{ color: 'var(--color-text-muted)', marginRight: 6 }}>stop reason</span>
              {derivedStopReason}
            </div>
          )}

          {/* Observation signals from context summary */}
          <ObservationSignalsRow signals={obsSignals} />

          {/* Observation message */}
          {contextSummary?.last_observation?.message && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 4 }}>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.70rem',
                color: 'var(--color-text-muted)', minWidth: 90, flexShrink: 0,
              }}>
                observation
              </span>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
                color: 'var(--color-text-soft)', lineHeight: 1.5,
              }}>
                {contextSummary.last_observation.message}
              </span>
            </div>
          )}

          {/* Observation-driven tool selection rationale */}
          <ToolSuggestionsRow suggestions={toolSuggestions} />

          {/* Iteration list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {attempts.map((attempt, i) => (
              <IterationRow
                key={attempt.attempt_index}
                attempt={attempt}
                isLast={i === attempts.length - 1}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
