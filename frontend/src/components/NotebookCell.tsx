import type { NotebookCellData } from '../types/notebook'
import { OutputBlock } from './ui/OutputBlock'
import { Spinner } from './ui/Icons'
import { WorkflowViewer } from './WorkflowViewer'
import { ResultTable } from './ResultTable'
import { ExplanationPanel } from './ExplanationPanel'
import { RAGPanel } from './RAGPanel'

interface NotebookCellProps {
  cell: NotebookCellData
  onConfirm: (cell: NotebookCellData) => void
}

export function NotebookCell({ cell, onConfirm }: NotebookCellProps) {
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

        {/* Error state */}
        {cell.status === 'error' && (
          <OutputBlock label="error" accent="var(--color-red)">
            <div className="flex items-start gap-2">
              <span style={{ color: 'var(--color-red)', fontSize: '1rem', lineHeight: 1 }}>✗</span>
              <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.85rem', color: 'var(--color-red)', lineHeight: 1.5 }}>
                {cell.error}
              </p>
            </div>
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
