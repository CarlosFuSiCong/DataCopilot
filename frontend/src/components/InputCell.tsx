import { useState, useRef, useEffect } from 'react'

interface InputCellProps {
  disabled: boolean
  onSubmit: (query: string) => void
  // When set by a parent (e.g. "Use this" button), pre-fills and focuses the input.
  suggestedQuery?: string
  onSuggestedQueryConsumed?: () => void
}

export function InputCell({ disabled, onSubmit, suggestedQuery, onSuggestedQueryConsumed }: InputCellProps) {
  const [query, setQuery] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // When a "Use this" suggestion arrives, fill the textarea and focus it.
  useEffect(() => {
    if (suggestedQuery) {
      queueMicrotask(() => {
        setQuery(suggestedQuery)
        onSuggestedQueryConsumed?.()
        textareaRef.current?.focus()
        autoResize()
      })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suggestedQuery])

  function autoResize() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
  }

  function handleChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setQuery(e.target.value)
    autoResize()
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  function submit() {
    const trimmed = query.trim()
    if (!trimmed || disabled) return
    onSubmit(trimmed)
    setQuery('')
    // Reset height after clearing
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
      }
    }, 0)
  }

  const canSend = !disabled && query.trim().length > 0

  return (
    <div
      style={{
        padding: '10px 12px 12px',
        borderTop: '1px solid var(--color-border)',
        background: 'var(--color-bg)',
        flexShrink: 0,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          gap: 8,
          background: 'var(--color-cell-in)',
          border: `1px solid ${disabled ? 'var(--color-border-subtle)' : canSend ? 'rgba(97,175,239,0.5)' : 'var(--color-border)'}`,
          borderRadius: 12,
          padding: '8px 8px 8px 12px',
          opacity: disabled ? 0.5 : 1,
          transition: 'border-color 0.15s',
        }}
      >
        <textarea
          ref={textareaRef}
          disabled={disabled}
          value={query}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder={disabled ? 'Upload a dataset to start…' : 'Ask a question about your data…'}
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            outline: 'none',
            resize: 'none',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.9rem',
            color: 'var(--color-text)',
            lineHeight: 1.6,
            maxHeight: 120,
            overflow: 'auto',
            padding: 0,
          }}
        />
        <button
          onClick={submit}
          disabled={!canSend}
          title="Send (Enter)"
          style={{
            flexShrink: 0,
            width: 32,
            height: 32,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: canSend ? 'var(--color-accent)' : 'var(--color-border)',
            border: 'none',
            borderRadius: 8,
            cursor: canSend ? 'pointer' : 'not-allowed',
            color: canSend ? 'var(--color-bg)' : 'var(--color-text-muted)',
            fontSize: '1rem',
            lineHeight: 1,
            transition: 'background 0.15s',
          }}
        >
          ↑
        </button>
      </div>
      <p
        style={{
          margin: '5px 0 0',
          textAlign: 'center',
          fontFamily: 'var(--font-mono)',
          fontSize: '0.67rem',
          color: 'var(--color-text-muted)',
          opacity: 0.7,
        }}
      >
        Enter to send · Shift+Enter for new line
      </p>
    </div>
  )
}
