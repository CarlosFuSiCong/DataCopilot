import { useState } from 'react'
import { Gutter } from './ui/OutputBlock'

interface InputCellProps {
  disabled: boolean
  onSubmit: (query: string) => void
}

export function InputCell({ disabled, onSubmit }: InputCellProps) {
  const [query, setQuery] = useState('')

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (query.trim()) {
        onSubmit(query.trim())
        setQuery('')
      }
    }
  }

  return (
    <div className="flex" style={{ padding: '4px 0', marginTop: 8 }}>
      <Gutter label="In [ ]:" color={disabled ? 'var(--color-text-muted)' : 'var(--color-blue)'} />
      <div
        className="flex-1 mr-4 rounded"
        style={{
          background: 'var(--color-cell-in)',
          border: `1px solid ${disabled ? 'var(--color-border-subtle)' : 'var(--color-blue)'}`,
          opacity: disabled ? 0.45 : 1,
        }}
      >
        <textarea
          disabled={disabled}
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
          placeholder={disabled ? 'Upload a dataset to start…' : 'Enter a query… (Enter to run, Shift+Enter for new line)'}
          style={{
            width: '100%', background: 'transparent', border: 'none', outline: 'none',
            resize: 'none', padding: '10px 12px',
            fontFamily: 'var(--font-mono)', fontSize: '0.9rem',
            color: 'var(--color-text)', lineHeight: 1.6,
          }}
        />
      </div>
    </div>
  )
}
