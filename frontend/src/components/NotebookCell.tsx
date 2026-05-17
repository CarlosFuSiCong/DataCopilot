import { useRef, useState } from 'react'
import type { ApiErrorContext } from '../types'
import type { NotebookCellData } from '../types/notebook'
import { OutputBlock } from './ui/OutputBlock'
import { Spinner } from './ui/Icons'
import { WorkflowViewer } from './WorkflowViewer'
import { ResultTable } from './ResultTable'
import { ExplanationPanel } from './ExplanationPanel'
import { RAGPanel } from './RAGPanel'

import type { WorkflowStep } from '../types'

interface NotebookCellProps {
  cell: NotebookCellData
  onConfirm: (cell: NotebookCellData) => void
  onClarify: (cell: NotebookCellData, answer: string) => void
  onSuggest: (query: string) => void
  onRerun: (steps: WorkflowStep[], query: string, runId?: string | null) => void
}

// ---------------------------------------------------------------------------
// Structured error panels per error_code
// ---------------------------------------------------------------------------

function ErrorMissingColumn({ message, context }: { message: string; context?: ApiErrorContext }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div className="flex items-start gap-2">
        <span style={{ color: 'var(--color-red)', fontSize: '1rem', lineHeight: 1 }}>✗</span>
        <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.85rem', color: 'var(--color-red)', lineHeight: 1.5 }}>
          {message}
        </p>
      </div>
      {context?.available_columns && context.available_columns.length > 0 && (
        <div style={{
          background: 'var(--color-surface-1)',
          border: '1px solid var(--color-border)',
          borderRadius: 6,
          padding: '8px 12px',
        }}>
          <p style={{ margin: '0 0 6px', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
            Available columns:
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {context.available_columns.map(col => (
              <span key={col} style={{
                background: 'var(--color-surface-2)',
                border: '1px solid var(--color-border)',
                borderRadius: 4,
                padding: '2px 8px',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.75rem',
                color: 'var(--color-accent)',
              }}>{col}</span>
            ))}
          </div>
          <p style={{ margin: '8px 0 0', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
            Rewrite your query using one of the columns listed above.
          </p>
        </div>
      )}
    </div>
  )
}

function ErrorEmptyWorkflow({
  message,
  context,
  onSuggest,
}: {
  message: string
  context?: ApiErrorContext
  onSuggest: (q: string) => void
}) {
  const hasRelevant = context?.relevant_steps && context.relevant_steps.length > 0
  const plannerHint = context?.planner_hint

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div className="flex items-start gap-2">
        <span style={{ color: 'var(--color-yellow)', fontSize: '1rem', lineHeight: 1 }}>⚠</span>
        <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.85rem', color: 'var(--color-yellow)', lineHeight: 1.5 }}>
          {message}
        </p>
      </div>

      {/* Specific planner hint (e.g. column not found + did-you-mean) — shown before generic suggestions */}
      {plannerHint && (
        <div style={{
          padding: '8px 12px',
          background: 'var(--color-surface-2)',
          border: '1px solid var(--color-yellow)',
          borderRadius: 4,
          fontFamily: 'var(--font-mono)',
          fontSize: '0.8rem',
          color: 'var(--color-text)',
          lineHeight: 1.6,
        }}>
          {plannerHint}
        </div>
      )}

      {/* RAG-relevant operation cards — primary path */}
      {hasRelevant && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
            Based on your query, you may have meant one of these:
          </p>
          {context!.relevant_steps!.map(hint => {
            // Extract a representative example query string from the example dict.
            const exampleQuery: string = (() => {
              const ex = hint.example
              if (!ex || typeof ex !== 'object') return ''
              // Most step examples follow the format used in the corpus docs.
              const stepType = hint.step_type
              const col = (ex['column'] ?? ex['columns']) as string | string[] | undefined
              const val = ex['value'] as unknown
              const op = ex['operator'] as string | undefined
              if (stepType === 'filter_rows' && col && op && val !== undefined)
                return `Filter rows where ${Array.isArray(col) ? col[0] : col} ${op} ${val}`
              if (stepType === 'group_by') {
                const target = ex['target'] as string | undefined
                const agg = ex['agg'] as string | undefined
                return `Group by ${Array.isArray(col) ? col.join(', ') : col ?? '...'} and ${agg ?? 'sum'} the ${target ?? '...'}`
              }
              if (stepType === 'sort_values')
                return `Sort by ${Array.isArray(col) ? col[0] : col ?? '...'}`
              if (stepType === 'select_columns')
                return `Select columns ${Array.isArray(col) ? col.join(', ') : col ?? '...'}`
              if (stepType === 'drop_columns')
                return `Drop columns ${Array.isArray(col) ? col.join(', ') : col ?? '...'}`
              return ''
            })()

            return (
              <div
                key={hint.step_type}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 10,
                  background: 'var(--color-surface-1)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 8,
                  padding: '10px 12px',
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ margin: '0 0 2px', fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--color-accent)', fontWeight: 600 }}>
                    {hint.step_type}
                  </p>
                  <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--color-text-muted)', lineHeight: 1.5 }}>
                    {hint.description}
                  </p>
                  {exampleQuery && (
                    <p style={{ margin: '4px 0 0', fontFamily: 'var(--font-mono)', fontSize: '0.74rem', color: 'var(--color-text-soft)', fontStyle: 'italic' }}>
                      e.g. "{exampleQuery}"
                    </p>
                  )}
                </div>
                {exampleQuery && (
                  <button
                    type="button"
                    onClick={() => onSuggest(exampleQuery)}
                    style={{
                      flexShrink: 0,
                      padding: '4px 10px',
                      background: 'transparent',
                      border: '1px solid var(--color-accent)',
                      borderRadius: 5,
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.72rem',
                      color: 'var(--color-accent)',
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    Use this ↗
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Fallback: generic lists when RAG returned nothing relevant */}
      {!hasRelevant && context?.example_queries && context.example_queries.length > 0 && (
        <div style={{
          background: 'var(--color-surface-1)',
          border: '1px solid var(--color-border)',
          borderRadius: 6,
          padding: '8px 12px',
        }}>
          <p style={{ margin: '0 0 6px', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
            Example queries you can try:
          </p>
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            {context.example_queries.map(q => (
              <li key={q} style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--color-text-soft)', lineHeight: 1.8 }}>
                <span
                  style={{ cursor: 'pointer', textDecoration: 'underline dotted', textUnderlineOffset: 3 }}
                  onClick={() => onSuggest(q)}
                >
                  {q}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {!hasRelevant && context?.supported_steps && context.supported_steps.length > 0 && (
        <div style={{
          background: 'var(--color-surface-1)',
          border: '1px solid var(--color-border)',
          borderRadius: 6,
          padding: '8px 12px',
        }}>
          <p style={{ margin: '0 0 6px', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
            Supported operations:
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {context.supported_steps.map(s => (
              <span key={s} style={{
                background: 'var(--color-surface-2)',
                border: '1px solid var(--color-border)',
                borderRadius: 4,
                padding: '2px 8px',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.72rem',
                color: 'var(--color-text-muted)',
              }}>{s}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function ErrorExecutionStep({ message, context }: { message: string; context?: ApiErrorContext }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div className="flex items-start gap-2">
        <span style={{ color: 'var(--color-red)', fontSize: '1rem', lineHeight: 1 }}>✗</span>
        <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.85rem', color: 'var(--color-red)', lineHeight: 1.5 }}>
          {message}
        </p>
      </div>
      {(context?.failed_step_type != null || context?.suggestion) && (
        <div style={{
          background: 'var(--color-surface-1)',
          border: '1px solid var(--color-border)',
          borderRadius: 6,
          padding: '8px 12px',
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
        }}>
          {context?.failed_step_type != null && (
            <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--color-text-muted)' }}>
              Failed at step {(context.failed_step_index ?? 0) + 1}: <span style={{ color: 'var(--color-accent)' }}>{context.failed_step_type}</span>
            </p>
          )}
          {context?.suggestion && (
            <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--color-text-soft)', lineHeight: 1.5 }}>
              {context.suggestion}
            </p>
          )}
        </div>
      )}
      {context?.available_columns && context.available_columns.length > 0 && (
        <div style={{
          background: 'var(--color-surface-1)',
          border: '1px solid var(--color-border)',
          borderRadius: 6,
          padding: '8px 12px',
        }}>
          <p style={{ margin: '0 0 6px', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
            Columns available at the failing step:
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {context.available_columns.map(col => (
              <span key={col} style={{
                background: 'var(--color-surface-2)',
                border: '1px solid var(--color-border)',
                borderRadius: 4,
                padding: '2px 8px',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.75rem',
                color: 'var(--color-accent)',
              }}>{col}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function ErrorRagNoHits({ message, context }: { message: string; context?: ApiErrorContext }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div className="flex items-start gap-2">
        <span style={{ color: 'var(--color-yellow)', fontSize: '1rem', lineHeight: 1 }}>⚠</span>
        <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.85rem', color: 'var(--color-yellow)', lineHeight: 1.5 }}>
          {message}
        </p>
      </div>
      <div style={{
        background: 'var(--color-surface-1)',
        border: '1px solid var(--color-border)',
        borderRadius: 6,
        padding: '8px 12px',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
      }}>
        {context?.retrieval_method && (
          <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
            Retrieval method: <span style={{ color: 'var(--color-accent)' }}>{context.retrieval_method}</span>
          </p>
        )}
        {context?.suggestion && (
          <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--color-text-soft)', lineHeight: 1.5 }}>
            {context.suggestion}
          </p>
        )}
      </div>
    </div>
  )
}

function ErrorGeneric({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2">
      <span style={{ color: 'var(--color-red)', fontSize: '1rem', lineHeight: 1 }}>✗</span>
      <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.85rem', color: 'var(--color-red)', lineHeight: 1.5 }}>
        {message}
      </p>
    </div>
  )
}

function ErrorContent({ cell, onSuggest }: { cell: NotebookCellData; onSuggest: (q: string) => void }) {
  const msg = cell.error ?? 'Unknown error'
  const ctx = cell.errorContext
  switch (cell.errorCode) {
    case 'missing_column':
      return <ErrorMissingColumn message={msg} context={ctx} />
    case 'empty_workflow':
      return <ErrorEmptyWorkflow message={msg} context={ctx} onSuggest={onSuggest} />
    case 'execution_error':
      return <ErrorExecutionStep message={msg} context={ctx} />
    case 'rag_no_hits':
      return <ErrorRagNoHits message={msg} context={ctx} />
    default:
      return <ErrorGeneric message={msg} />
  }
}

// ---------------------------------------------------------------------------
// Clarification panel
// ---------------------------------------------------------------------------

function ClarificationPanel({
  cell,
  onSubmit,
}: {
  cell: NotebookCellData
  onSubmit: (answer: string) => void
}) {
  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const answered = !!cell.clarificationAnswer
  const affectedStep = cell.clarificationContext?.affected_step
  const clarificationLabel = cell.clarificationType === 'slot_validation'
    ? 'slot validation'
    : 'clarification needed'
  const clarificationAccent = cell.clarificationType === 'slot_validation'
    ? 'var(--color-yellow)'
    : 'var(--color-blue)'

  function handleSubmit() {
    const trimmed = draft.trim()
    if (!trimmed) return
    onSubmit(trimmed)
    setDraft('')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        <span style={{
          width: 'fit-content',
          border: `1px solid ${clarificationAccent}`,
          borderRadius: 999,
          padding: '2px 8px',
          fontFamily: 'var(--font-mono)',
          fontSize: '0.7rem',
          color: clarificationAccent,
          background: 'var(--color-surface-1)',
        }}>
          {clarificationLabel}
        </span>
        {affectedStep?.type && (
          <span style={{
            width: 'fit-content',
            border: '1px solid var(--color-border)',
            borderRadius: 999,
            padding: '2px 8px',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.7rem',
            color: 'var(--color-text-muted)',
            background: 'var(--color-surface-1)',
          }}>
            {String(affectedStep.type)}
            {typeof affectedStep.column === 'string' ? ` · ${affectedStep.column}` : ''}
          </span>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
        <span style={{ color: clarificationAccent, fontSize: '1rem', lineHeight: 1, flexShrink: 0 }}>?</span>
        <p style={{
          margin: 0,
          fontFamily: 'var(--font-mono)',
          fontSize: '0.85rem',
          color: 'var(--color-text)',
          lineHeight: 1.6,
        }}>
          {cell.clarificationQuestion}
        </p>
      </div>

      {answered ? (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '5px 10px',
          background: 'var(--color-surface-1)',
          border: '1px solid var(--color-border)',
          borderRadius: 6,
        }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>Answer:</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--color-accent)' }}>
            {cell.clarificationAnswer}
          </span>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 6 }}>
          <input
            ref={inputRef}
            autoFocus
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleSubmit() }}
            placeholder="Type your answer…"
            style={{
              flex: 1,
              background: 'var(--color-surface-1)',
              border: '1px solid var(--color-border)',
              borderRadius: 6,
              padding: '5px 10px',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.82rem',
              color: 'var(--color-text)',
              outline: 'none',
            }}
          />
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!draft.trim()}
            style={{
              padding: '5px 14px',
              background: draft.trim() ? 'var(--color-blue)' : 'var(--color-surface-2)',
              border: '1px solid var(--color-border)',
              borderRadius: 6,
              fontFamily: 'var(--font-mono)',
              fontSize: '0.78rem',
              color: draft.trim() ? '#fff' : 'var(--color-text-muted)',
              cursor: draft.trim() ? 'pointer' : 'not-allowed',
              whiteSpace: 'nowrap',
            }}
          >
            Send
          </button>
        </div>
      )}
    </div>
  )
}

export function NotebookCell({ cell, onConfirm, onClarify, onSuggest, onRerun }: NotebookCellProps) {
  const execResult = cell.confirmResult?.execution_result ?? cell.result?.execution_result ?? null
  const explanation = cell.confirmResult?.explanation ?? cell.result?.explanation ?? null
  const stepResults = cell.confirmResult?.execution_result?.step_results ?? cell.result?.step_results
  const ragContext = cell.result?.rag_context ?? null

  const lastPreviewStep = cell.result?.step_results?.filter(r => r.preview.length > 0).at(-1) ?? null
  const previewCols = lastPreviewStep ? Object.keys(lastPreviewStep.preview[0]) : []

  const hasResult = (cell.status === 'ok' || cell.status === 'preview' || cell.status === 'confirming') && !!cell.result
  const hasErrors = cell.result?.has_errors ?? false
  const hasWarnings = cell.result?.has_warnings ?? false

  return (
    <div style={{ marginBottom: 4 }}>
      {/* User message — right-aligned bubble */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '4px 16px 10px' }}>
        <div
          style={{
            maxWidth: '78%',
            background: 'var(--color-cell-in)',
            border: '1px solid rgba(97,175,239,0.35)',
            borderRadius: '14px 14px 4px 14px',
            padding: '8px 14px',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.88rem',
            color: 'var(--color-text)',
            lineHeight: 1.65,
            wordBreak: 'break-word',
            whiteSpace: 'pre-wrap',
          }}
        >
          {cell.query}
        </div>
      </div>

      {/* Bot response area */}
      <div style={{ padding: '0 16px 8px' }}>
        {/* Bot label */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
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
        </div>

        {/* Loading / thinking indicator */}
        {cell.status === 'loading' && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '10px 14px',
              background: 'var(--color-cell-in)',
              border: '1px solid var(--color-border)',
              borderRadius: 10,
              width: 'fit-content',
            }}
          >
            <Spinner />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--color-text-muted)' }}>
              Planning workflow…
            </span>
          </div>
        )}

        {/* Clarification state */}
        {cell.status === 'clarifying' && (
          <OutputBlock
            label={cell.clarificationType === 'slot_validation' ? 'slot validation' : 'clarification'}
            accent={cell.clarificationType === 'slot_validation' ? 'var(--color-yellow)' : 'var(--color-blue)'}
          >
            <ClarificationPanel cell={cell} onSubmit={answer => onClarify(cell, answer)} />
          </OutputBlock>
        )}

        {/* Error state */}
        {cell.status === 'error' && (
          <OutputBlock
            label={cell.errorCode ?? 'error'}
            accent={cell.errorCode === 'empty_workflow' || cell.errorCode === 'rag_no_hits' ? 'var(--color-yellow)' : 'var(--color-red)'}
          >
            <ErrorContent cell={cell} onSuggest={onSuggest} />
          </OutputBlock>
        )}

        {/* Main result content */}
        {hasResult && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {/* Warning / error summary banner */}
            {(hasErrors || hasWarnings) && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  borderRadius: 8,
                  padding: '7px 12px',
                  background: hasErrors ? 'rgba(244,135,113,0.08)' : 'rgba(220,220,170,0.07)',
                  border: `1px solid ${hasErrors ? 'var(--color-red)' : 'var(--color-yellow)'}`,
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.78rem',
                }}
              >
                <span style={{ color: hasErrors ? 'var(--color-red)' : 'var(--color-yellow)', fontSize: '0.9rem' }}>
                  {hasErrors ? '✗' : '⚠'}
                </span>
                <span style={{ color: hasErrors ? 'var(--color-red)' : 'var(--color-yellow)' }}>
                  {hasErrors ? 'Workflow has errors — execution blocked.' : 'Workflow has warnings — review before confirming.'}
                </span>
              </div>
            )}

            <WorkflowViewer
              steps={cell.result!.planned_steps}
              stepResults={stepResults}
              onRerun={steps => onRerun(steps, cell.result!.query, cell.result?.run_id ?? cell.confirmResult?.run_id)}
            />

            {ragContext && <RAGPanel ragContext={ragContext} />}

            {/* Preview result (before confirm) */}
            {(cell.status === 'preview' || cell.status === 'confirming') && lastPreviewStep && (
              <ResultTable
                columns={previewCols}
                rows={lastPreviewStep.preview}
                rowCount={lastPreviewStep.output_row_count}
                label={`step preview · ${lastPreviewStep.output_row_count.toLocaleString()} rows`}
              />
            )}

            {/* Final execution result */}
            {cell.status === 'ok' && execResult && (
              <ResultTable
                columns={execResult.columns}
                rows={execResult.preview}
                rowCount={execResult.row_count}
                columnCount={execResult.column_count}
                logs={execResult.logs}
              />
            )}

            {cell.status === 'ok' && explanation && (
              <ExplanationPanel
                text={explanation}
                executionResult={execResult ?? undefined}
              />
            )}

            {/* Blocked by error */}
            {cell.status === 'preview' && hasErrors && (
              <OutputBlock label="blocked" accent="var(--color-red)">
                <div className="flex items-start gap-2">
                  <span style={{ color: 'var(--color-red)', fontSize: '1rem' }}>✗</span>
                  <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--color-red)', lineHeight: 1.5 }}>
                    Execution blocked: the workflow has errors. Review the issues above and revise your query.
                  </p>
                </div>
              </OutputBlock>
            )}

            {/* Review / confirm */}
            {cell.status === 'preview' && !hasErrors && (
              <OutputBlock label="review" accent={hasWarnings ? 'var(--color-yellow)' : 'var(--color-accent)'}>
                <div className="flex items-center gap-3">
                  {hasWarnings && (
                    <span style={{ color: 'var(--color-yellow)', fontSize: '1rem' }}>⚠</span>
                  )}
                  <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--color-text-soft)', flex: 1 }}>
                    {hasWarnings
                      ? 'Workflow has warnings. Review the steps above, then confirm to execute.'
                      : 'Review the planned workflow above, then confirm to execute.'}
                  </p>
                  <button
                    onClick={() => onConfirm(cell)}
                    style={{
                      padding: '5px 16px',
                      background: 'var(--color-accent)',
                      border: 'none', borderRadius: 6,
                      color: 'var(--color-bg)',
                      fontFamily: 'var(--font-mono)', fontSize: '0.82rem',
                      fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap',
                    }}
                  >
                    Confirm
                  </button>
                </div>
              </OutputBlock>
            )}

            {/* Confirming spinner */}
            {cell.status === 'confirming' && (
              <OutputBlock label="executing…" accent="var(--color-accent)">
                <div className="flex items-center gap-2">
                  <Spinner />
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--color-text-muted)' }}>
                    Running confirmed workflow…
                  </span>
                </div>
              </OutputBlock>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
