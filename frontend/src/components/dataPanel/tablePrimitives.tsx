import type { CSSProperties, ReactNode } from 'react'

export function th(): CSSProperties {
  return {
    padding: '6px 12px', textAlign: 'left', whiteSpace: 'nowrap',
    borderBottom: '1px solid var(--color-border)',
    borderRight: '1px solid var(--color-border-subtle)',
    color: 'var(--color-blue)', fontWeight: 500,
    background: 'var(--color-surface-2)',
  }
}

export function thIdx(): CSSProperties {
  return { ...th(), padding: '6px 10px', textAlign: 'right', color: 'var(--color-text-muted)', fontWeight: 400, minWidth: 40 }
}

export function td(isNull: boolean): CSSProperties {
  return {
    padding: '4px 12px', whiteSpace: 'nowrap',
    borderBottom: '1px solid var(--color-border-subtle)',
    borderRight: '1px solid var(--color-border-subtle)',
    color: isNull ? 'var(--color-text-muted)' : 'var(--color-text)',
  }
}

export function tdIdx(): CSSProperties {
  return {
    padding: '4px 10px', textAlign: 'right',
    borderBottom: '1px solid var(--color-border-subtle)',
    borderRight: '1px solid var(--color-border)',
    color: 'var(--color-text-muted)', fontSize: '0.72rem',
  }
}

export function browseBtnStyle(): CSSProperties {
  return {
    padding: '2px 10px', borderRadius: 3,
    background: 'var(--color-accent-subtle)', border: '1px solid var(--color-accent-dim)',
    color: 'var(--color-accent)', fontFamily: 'var(--font-mono)', fontSize: '0.72rem', cursor: 'pointer',
  }
}

export function backBtnStyle(): CSSProperties {
  return {
    padding: '2px 10px', borderRadius: 3,
    background: 'transparent', border: '1px solid var(--color-border)',
    color: 'var(--color-text-soft)', fontFamily: 'var(--font-mono)', fontSize: '0.72rem', cursor: 'pointer',
  }
}

export function PanelTableFooter({ label, page, totalPages, onPageChange, disabled }: {
  label: string
  page?: number
  totalPages?: number
  onPageChange?: (p: number) => void
  disabled?: boolean
}) {
  return (
    <div className="flex items-center justify-between px-3 py-2 shrink-0"
      style={{ borderTop: '1px solid var(--color-border)', background: 'var(--color-surface-2)' }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--color-text-muted)' }}>{label}</span>
      {onPageChange && totalPages !== undefined && page !== undefined && totalPages > 1 && (
        <div style={{ display: 'flex', gap: 3 }}>
          <PaginationIconBtn onClick={() => onPageChange(0)} disabled={disabled || page === 0}>«</PaginationIconBtn>
          <PaginationIconBtn onClick={() => onPageChange(page - 1)} disabled={disabled || page === 0}>‹</PaginationIconBtn>
          <span style={{ display: 'flex', alignItems: 'center', padding: '0 6px', fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--color-text-muted)' }}>
            {page + 1}/{totalPages}
          </span>
          <PaginationIconBtn onClick={() => onPageChange(page + 1)} disabled={disabled || page === totalPages - 1}>›</PaginationIconBtn>
          <PaginationIconBtn onClick={() => onPageChange(totalPages - 1)} disabled={disabled || page === totalPages - 1}>»</PaginationIconBtn>
        </div>
      )}
    </div>
  )
}

function PaginationIconBtn({ children, onClick, disabled }: { children: ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} style={{
      width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontFamily: 'var(--font-mono)', fontSize: '0.75rem', borderRadius: 3,
      border: '1px solid var(--color-border)', background: 'transparent',
      color: disabled ? 'var(--color-text-muted)' : 'var(--color-text-soft)',
      cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.4 : 1,
    }}>{children}</button>
  )
}
