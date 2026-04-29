interface OutputBlockProps {
  label: string
  accent: string
  children: React.ReactNode
}

export function OutputBlock({ label, accent, children }: OutputBlockProps) {
  return (
    <div
      className="rounded overflow-hidden"
      style={{ background: 'var(--color-cell-out)', border: '1px solid var(--color-border-subtle)' }}
    >
      <div
        className="px-3 py-1 flex items-center gap-1.5"
        style={{
          background: 'var(--color-surface-2)',
          borderBottom: '1px solid var(--color-border-subtle)',
          fontFamily: 'var(--font-mono)',
          fontSize: '0.75rem',
          color: accent,
          letterSpacing: '0.04em',
        }}
      >
        <span style={{ opacity: 0.6 }}>▸</span>
        {label}
      </div>
      <div className="px-3 py-2">{children}</div>
    </div>
  )
}

export function Gutter({ label, color }: { label: string; color: string }) {
  return (
    <div
      className="shrink-0 flex items-start justify-end pt-2 pr-2 select-none"
      style={{ width: 72, fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color }}
    >
      {label}
    </div>
  )
}
