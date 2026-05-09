import type { CSSProperties } from 'react'

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
