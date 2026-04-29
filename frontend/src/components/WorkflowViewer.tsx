import { useState } from 'react'
import type { WorkflowStep } from '../types'
import { OutputBlock } from './ui/OutputBlock'

interface WorkflowViewerProps {
  steps: WorkflowStep[]
}

export function WorkflowViewer({ steps }: WorkflowViewerProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <OutputBlock
      label={`workflow · ${steps.length} step${steps.length !== 1 ? 's' : ''}`}
      accent="var(--color-yellow)"
    >
      <div className="flex flex-col gap-1.5">
        {steps.map((step, i) => (
          <div
            key={i}
            className="flex items-start gap-2 rounded px-2 py-1.5"
            style={{ background: 'var(--color-surface-2)', border: '1px solid var(--color-border-subtle)' }}
          >
            <span
              style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
                color: 'var(--color-text-muted)', minWidth: 20, paddingTop: 1,
              }}
            >
              {i + 1}.
            </span>
            <div className="flex flex-col gap-0.5 flex-1 min-w-0">
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--color-yellow)', fontWeight: 500 }}>
                {step.type}
              </span>
              {Object.entries(step)
                .filter(([k]) => k !== 'type')
                .map(([k, v]) => (
                  <span key={k} style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-soft)' }}>
                    <span style={{ color: 'var(--color-blue)' }}>{k}</span>
                    {': '}
                    <span style={{ color: 'var(--color-orange)' }}>{JSON.stringify(v)}</span>
                  </span>
                ))}
            </div>
          </div>
        ))}

        <button
          onClick={() => setExpanded(v => !v)}
          style={{
            marginTop: 2, padding: '2px 8px', background: 'transparent',
            border: '1px solid var(--color-border)', borderRadius: 3,
            color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)',
            fontSize: '0.75rem', cursor: 'pointer', alignSelf: 'flex-start',
          }}
        >
          {expanded ? '▲ hide JSON' : '▼ show JSON'}
        </button>

        {expanded && (
          <pre style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-soft)', overflowX: 'auto' }}>
            {JSON.stringify(steps, null, 2)}
          </pre>
        )}
      </div>
    </OutputBlock>
  )
}
