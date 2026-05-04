export type ViewMode = 'original' | 'result'

export function DataPanelViewToggle({
  value,
  onChange,
}: {
  value: ViewMode
  onChange: (v: ViewMode) => void
}) {
  return (
    <div style={{
      display: 'flex', background: 'var(--color-surface-2)',
      borderRadius: 5, padding: 2, gap: 1,
      border: '1px solid var(--color-border-subtle)',
    }}>
      {(['original', 'result'] as ViewMode[]).map(m => (
        <button key={m} type="button" onClick={() => onChange(m)} style={{
          padding: '2px 10px', borderRadius: 4, border: 'none',
          background: value === m ? 'var(--color-surface)' : 'transparent',
          color: value === m ? 'var(--color-text)' : 'var(--color-text-muted)',
          fontFamily: 'var(--font-mono)', fontSize: '0.73rem',
          cursor: 'pointer', fontWeight: value === m ? 600 : 400,
          boxShadow: value === m ? '0 1px 3px rgba(0,0,0,0.3)' : 'none',
          transition: 'all 0.1s',
        }}>{m}</button>
      ))}
    </div>
  )
}
