import type { NotebookCellData } from '../types/notebook'
import { Gutter, OutputBlock } from './ui/OutputBlock'
import { Spinner } from './ui/Icons'
import { WorkflowViewer } from './WorkflowViewer'
import { ResultTable } from './ResultTable'
import { ExplanationPanel } from './ExplanationPanel'

interface NotebookCellProps {
  index: number
  cell: NotebookCellData
  onConfirm: (cell: NotebookCellData) => void
}

export function NotebookCell({ index, cell, onConfirm }: NotebookCellProps) {
  const outColor =
    cell.status === 'error' ? 'var(--color-red)' :
    cell.status === 'preview' || cell.status === 'confirming' ? 'var(--color-yellow)' :
    'var(--color-accent)'

  const execResult = cell.confirmResult?.execution_result ?? cell.result?.execution_result ?? null
  const explanation = cell.confirmResult?.explanation ?? cell.result?.explanation ?? null
  const stepResults = cell.confirmResult?.execution_result?.step_results ?? cell.result?.step_results

  const lastPreviewStep = cell.result?.step_results?.filter(r => r.preview.length > 0).at(-1) ?? null
  const previewCols = lastPreviewStep ? Object.keys(lastPreviewStep.preview[0]) : []

  const hasResult = (cell.status === 'ok' || cell.status === 'preview' || cell.status === 'confirming') && !!cell.result

  return (
    <div style={{ marginBottom: 8 }}>
      {/* In row */}
      <div className="flex" style={{ padding: '2px 0' }}>
        <Gutter label={`In [${index}]:`} color="var(--color-blue)" />
        <div
          className="flex-1 mr-4 rounded px-3 py-2"
          style={{ background: 'var(--color-cell-in)', border: '1px solid var(--color-border)', fontFamily: 'var(--font-mono)', fontSize: '0.9rem', color: 'var(--color-text)' }}
        >
          {cell.query}
        </div>
      </div>

      {/* Out row */}
      <div className="flex" style={{ padding: '2px 0' }}>
        <Gutter label={`Out[${index}]:`} color={outColor} />
        <div className="flex-1 mr-4 flex flex-col gap-2">

          {cell.status === 'error' && (
            <OutputBlock label="error" accent="var(--color-red)">
              <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.85rem', color: 'var(--color-red)' }}>
                {cell.error}
              </p>
            </OutputBlock>
          )}

          {hasResult && (
            <>
              <WorkflowViewer
                steps={cell.result!.planned_steps}
                stepResults={stepResults}
              />

              {(cell.status === 'preview' || cell.status === 'confirming') && lastPreviewStep && (
                <ResultTable
                  columns={previewCols}
                  rows={lastPreviewStep.preview}
                  rowCount={lastPreviewStep.output_row_count}
                  label={`step preview · ${lastPreviewStep.output_row_count.toLocaleString()} rows`}
                />
              )}

              {cell.status === 'ok' && execResult && (
                <ResultTable
                  columns={execResult.columns}
                  rows={execResult.preview}
                  rowCount={execResult.row_count}
                  logs={execResult.logs}
                />
              )}

              {cell.status === 'ok' && explanation && (
                <ExplanationPanel text={explanation} />
              )}

              {cell.status === 'preview' && cell.result!.has_errors && (
                <OutputBlock label="blocked" accent="var(--color-red)">
                  <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--color-red)' }}>
                    Execution blocked: the workflow has errors. Review the issues above and revise your query.
                  </p>
                </OutputBlock>
              )}

              {cell.status === 'preview' && !cell.result!.has_errors && (
                <OutputBlock label="review" accent="var(--color-yellow)">
                  <div className="flex items-center gap-3">
                    <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--color-text-soft)', flex: 1 }}>
                      {cell.result!.has_warnings
                        ? 'Workflow has warnings. Review the steps above, then confirm to execute.'
                        : 'Review the planned workflow above, then confirm to execute.'}
                    </p>
                    <button
                      onClick={() => onConfirm(cell)}
                      style={{
                        padding: '5px 16px',
                        background: 'var(--color-accent)',
                        border: 'none',
                        borderRadius: 4,
                        color: 'var(--color-bg)',
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.82rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Confirm
                    </button>
                  </div>
                </OutputBlock>
              )}

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
            </>
          )}

        </div>
      </div>
    </div>
  )
}
