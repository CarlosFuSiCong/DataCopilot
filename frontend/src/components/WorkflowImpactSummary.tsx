import type { StepResult } from '../types'

interface WorkflowImpactSummaryProps {
  stepResults: StepResult[]
  hasWarnings?: boolean
  hasErrors?: boolean
}

function lastStep(stepResults: StepResult[]) {
  return stepResults.length > 0 ? stepResults[stepResults.length - 1] : null
}

export function WorkflowImpactSummary({ stepResults, hasWarnings = false, hasErrors = false }: WorkflowImpactSummaryProps) {
  const finalStep = lastStep(stepResults)
  if (!finalStep) return null

  const warningCount = stepResults.reduce((count, step) => count + step.issues.filter(issue => issue.severity === 'warning').length, 0)
  const errorCount = stepResults.reduce((count, step) => count + step.issues.filter(issue => issue.severity === 'error').length, 0)

  return (
    <div
      data-testid="workflow-impact-summary"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
        gap: 6,
        padding: 8,
        borderRadius: 10,
        background: hasErrors
          ? 'rgba(244,135,113,0.08)'
          : hasWarnings
            ? 'rgba(220,220,170,0.07)'
            : 'var(--color-surface-1)',
        border: `1px solid ${hasErrors ? 'var(--color-red)' : hasWarnings ? 'var(--color-yellow)' : 'var(--color-border)'}`,
        fontFamily: 'var(--font-mono)',
      }}
    >
      <ImpactMetric label="Rows" value={`${finalStep.input_row_count.toLocaleString()} -> ${finalStep.output_row_count.toLocaleString()}`} />
      <ImpactMetric label="Columns" value={`${finalStep.input_column_count.toLocaleString()} -> ${finalStep.output_column_count.toLocaleString()}`} />
      <ImpactMetric label="Warnings" value={String(warningCount)} tone={warningCount > 0 ? 'warn' : 'normal'} />
      <ImpactMetric label="Errors" value={String(errorCount)} tone={errorCount > 0 ? 'error' : 'normal'} />
    </div>
  )
}

function ImpactMetric({ label, value, tone = 'normal' }: { label: string; value: string; tone?: 'normal' | 'warn' | 'error' }) {
  const color = tone === 'error' ? 'var(--color-red)' : tone === 'warn' ? 'var(--color-yellow)' : 'var(--color-text-heading)'
  return (
    <div>
      <p style={{ margin: 0, color: 'var(--color-text-muted)', fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {label}
      </p>
      <p style={{ margin: '2px 0 0', color, fontSize: '0.82rem', fontWeight: 600 }}>
        {value}
      </p>
    </div>
  )
}
