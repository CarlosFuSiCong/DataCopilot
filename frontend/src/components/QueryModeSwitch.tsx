import type { QueryModeHint } from '../types'

const MODES: Array<{ id: QueryModeHint; label: string; description: string }> = [
  { id: 'auto', label: 'Auto', description: 'Classifier chooses the route' },
  { id: 'ask', label: 'Ask', description: 'Read-only answers' },
  { id: 'analysis', label: 'Analysis', description: 'Read-only analytical tools' },
  { id: 'workflow', label: 'Workflow', description: 'Preview and confirm changes' },
]

interface QueryModeSwitchProps {
  value: QueryModeHint
  onChange: (mode: QueryModeHint) => void
  disabled?: boolean
}

export function QueryModeSwitch({ value, onChange, disabled = false }: QueryModeSwitchProps) {
  return (
    <div
      data-testid="query-mode-switch"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
        gap: 4,
        marginBottom: 8,
      }}
    >
      {MODES.map(mode => {
        const active = value === mode.id
        return (
          <button
            key={mode.id}
            type="button"
            disabled={disabled}
            title={mode.description}
            onClick={() => onChange(mode.id)}
            style={{
              padding: '5px 6px',
              borderRadius: 8,
              border: `1px solid ${active ? 'var(--color-accent)' : 'var(--color-border)'}`,
              background: active ? 'var(--color-accent-subtle)' : 'var(--color-surface-1)',
              color: active ? 'var(--color-accent)' : 'var(--color-text-muted)',
              cursor: disabled ? 'not-allowed' : 'pointer',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.68rem',
              letterSpacing: '0.03em',
              whiteSpace: 'nowrap',
            }}
          >
            {mode.label}
          </button>
        )
      })}
    </div>
  )
}
