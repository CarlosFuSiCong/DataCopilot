import type { ReactNode } from 'react'

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
