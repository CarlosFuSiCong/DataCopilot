import { useRef, useState } from 'react'
import type { NotebookCellData } from '../types/notebook'

interface ClarificationPanelProps {
  cell: NotebookCellData
  onSubmit: (answer: string) => void
  onSuggest: (query: string) => void
}

const AVAILABLE_COLUMNS_PATTERN = /Available columns:\s*([^.?;]+)/gi

function cleanColumnToken(value: string): string {
  return value
    .trim()
    .replace(/^[\s'"[]+/, '')
    .replace(/[\s'"\]]+$/, '')
}

function availableColumnsFromQuestion(question: string | undefined): string[] {
  if (!question) return []
  const matches = Array.from(question.matchAll(AVAILABLE_COLUMNS_PATTERN))
  const lastMatch = matches[matches.length - 1]
  if (!lastMatch?.[1]) return []
  return lastMatch[1]
    .split(',')
    .map(cleanColumnToken)
    .filter(Boolean)
}

export function ClarificationPanel({ cell, onSubmit, onSuggest }: ClarificationPanelProps) {
  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const answered = !!cell.clarificationAnswer
  const choices = cell.clarificationContext?.choices ?? cell.clarificationChoices ?? []
  const availableColumns = availableColumnsFromQuestion(cell.clarificationQuestion)
  const affectedStep = cell.clarificationContext?.affected_step
  const clarificationLabel = cell.clarificationType === 'slot_validation'
    ? 'slot validation'
    : 'clarification needed'
  const clarificationAccent = cell.clarificationType === 'slot_validation'
    ? 'var(--color-yellow)'
    : 'var(--color-blue)'

  function handleSubmit() {
    const trimmed = draft.trim()
    if (!trimmed) return
    onSubmit(trimmed)
    setDraft('')
  }

  return (
    <div data-testid="clarification-panel" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        <span style={{
          width: 'fit-content',
          border: `1px solid ${clarificationAccent}`,
          borderRadius: 999,
          padding: '2px 8px',
          fontFamily: 'var(--font-mono)',
          fontSize: '0.7rem',
          color: clarificationAccent,
          background: 'var(--color-surface-1)',
        }}>
          {clarificationLabel}
        </span>
        {affectedStep?.type && (
          <span style={{
            width: 'fit-content',
            border: '1px solid var(--color-border)',
            borderRadius: 999,
            padding: '2px 8px',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.7rem',
            color: 'var(--color-text-muted)',
            background: 'var(--color-surface-1)',
          }}>
            {String(affectedStep.type)}
            {typeof affectedStep.column === 'string' ? ` · ${affectedStep.column}` : ''}
          </span>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
        <span style={{ color: clarificationAccent, fontSize: '1rem', lineHeight: 1, flexShrink: 0 }}>?</span>
        <p style={{
          margin: 0,
          fontFamily: 'var(--font-mono)',
          fontSize: '0.85rem',
          color: 'var(--color-text)',
          lineHeight: 1.6,
        }}>
          {cell.clarificationQuestion}
        </p>
      </div>

      {!answered && choices.length > 0 && (
        <div style={{ display: 'grid', gap: 6 }}>
          {choices.map(choice => (
            <button
              key={choice.id}
              type="button"
              onClick={() => {
                onSuggest(choice.query)
                onSubmit(choice.query)
              }}
              style={{
                textAlign: 'left',
                background: 'var(--color-surface-1)',
                border: '1px solid var(--color-border)',
                borderRadius: 8,
                padding: '9px 10px',
                cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
              }}
            >
              <div style={{ color: 'var(--color-accent)', fontSize: '0.8rem', fontWeight: 600 }}>
                {choice.label}
              </div>
              <div style={{ color: 'var(--color-text-muted)', fontSize: '0.74rem', lineHeight: 1.5, marginTop: 2 }}>
                {choice.description}
              </div>
              {choice.tool && (
                <div style={{ color: 'var(--color-blue)', fontSize: '0.68rem', marginTop: 4 }}>
                  tool · {choice.tool}
                </div>
              )}
            </button>
          ))}
        </div>
      )}

      {!answered && choices.length === 0 && availableColumns.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--color-text-muted)' }}>
            Choose an available column:
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {availableColumns.map(column => (
              <button
                key={column}
                type="button"
                onClick={() => onSubmit(column)}
                style={{
                  border: '1px solid var(--color-blue)',
                  borderRadius: 999,
                  background: 'rgba(86,156,214,0.08)',
                  color: 'var(--color-blue)',
                  padding: '3px 9px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.72rem',
                  cursor: 'pointer',
                }}
              >
                {column}
              </button>
            ))}
          </div>
        </div>
      )}

      {answered ? (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '5px 10px',
          background: 'var(--color-surface-1)',
          border: '1px solid var(--color-border)',
          borderRadius: 6,
        }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>Answer:</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--color-accent)' }}>
            {cell.clarificationAnswer}
          </span>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 6 }}>
          <input
            ref={inputRef}
            autoFocus
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleSubmit() }}
            placeholder="Type your answer…"
            style={{
              flex: 1,
              background: 'var(--color-surface-1)',
              border: '1px solid var(--color-border)',
              borderRadius: 6,
              padding: '5px 10px',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.82rem',
              color: 'var(--color-text)',
              outline: 'none',
            }}
          />
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!draft.trim()}
            style={{
              padding: '5px 14px',
              background: draft.trim() ? 'var(--color-blue)' : 'var(--color-surface-2)',
              border: '1px solid var(--color-border)',
              borderRadius: 6,
              fontFamily: 'var(--font-mono)',
              fontSize: '0.78rem',
              color: draft.trim() ? '#fff' : 'var(--color-text-muted)',
              cursor: draft.trim() ? 'pointer' : 'not-allowed',
              whiteSpace: 'nowrap',
            }}
          >
            Send
          </button>
        </div>
      )}
    </div>
  )
}
