const DEMO_PROMPTS = [
  { label: 'Ask schema', shortLabel: 'Schema', query: 'What columns are in this dataset?' },
  { label: 'Broad analysis clarification', shortLabel: 'Clarify', query: 'Analyze this dataset for issues' },
  { label: 'Check missing values', shortLabel: 'Missing', query: 'Check for missing values' },
  { label: 'Compare amount by region', shortLabel: 'Compare', query: 'Compare average amount by region' },
  { label: 'Sort by revenue descending', shortLabel: 'Revenue sort', query: 'Sort by revenue descending' },
  { label: 'Sort by amount descending', shortLabel: 'Amount sort', query: 'Sort by amount descending' },
  { label: 'Filter amount > 1000', shortLabel: 'Filter >1000', query: 'Filter rows where amount > 1000' },
]

interface DemoGuidePanelProps {
  onSuggest: (query: string) => void
}

export function DemoGuidePanel({ onSuggest }: DemoGuidePanelProps) {
  return (
    <div
      data-testid="demo-guide-panel"
      style={{
        margin: '6px 12px 0',
        padding: '5px 7px',
        border: '1px solid var(--color-border)',
        borderRadius: 9,
        background: 'rgba(86,156,214,0.05)',
        fontFamily: 'var(--font-mono)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 4 }}>
        <p style={{ margin: 0, color: 'var(--color-accent)', fontSize: '0.68rem', fontWeight: 700 }}>
          Demo
        </p>
        <span style={{ color: 'var(--color-text-muted)', fontSize: '0.62rem' }}>
          fill
        </span>
      </div>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {DEMO_PROMPTS.map(item => (
          <button
            key={item.label}
            type="button"
            aria-label={item.label}
            onClick={() => onSuggest(item.query)}
            title={item.query}
            style={{
              border: '1px solid var(--color-border)',
              borderRadius: 999,
              background: 'var(--color-surface-1)',
              color: 'var(--color-text-soft)',
              padding: '2px 6px',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.62rem',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              lineHeight: 1.3,
            }}
          >
            {item.shortLabel}
          </button>
        ))}
      </div>
    </div>
  )
}
