interface ResizeDividerProps {
  onMouseDown: (e: React.MouseEvent) => void
}

export function ResizeDivider({ onMouseDown }: ResizeDividerProps) {
  return (
    <div
      onMouseDown={onMouseDown}
      style={{
        width: 4,
        flexShrink: 0,
        background: 'var(--color-border)',
        cursor: 'col-resize',
        transition: 'background 0.15s',
      }}
      onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-accent-dim)')}
      onMouseLeave={e => (e.currentTarget.style.background = 'var(--color-border)')}
    />
  )
}
