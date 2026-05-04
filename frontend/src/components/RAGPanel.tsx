import { useState } from 'react'
import type { RAGContext } from '../types'
import { OutputBlock } from './ui/OutputBlock'

interface RAGPanelProps {
  ragContext: RAGContext
}

const DOC_TYPE_COLORS: Record<string, string> = {
  transformation: 'var(--color-blue)',
  failure_case:   'var(--color-red)',
  correction_case:'var(--color-yellow)',
  workflow_example:'var(--color-purple)',
}

const METHOD_COLORS: Record<string, string> = {
  pgvector: 'var(--color-accent)',
  keyword:  'var(--color-orange)',
}

export function RAGPanel({ ragContext }: RAGPanelProps) {
  const [expanded, setExpanded] = useState(false)
  const { retrieved_docs, debug } = ragContext
  const method = debug?.method ?? 'unknown'
  const methodColor = METHOD_COLORS[method] ?? 'var(--color-text-muted)'

  return (
    <OutputBlock
      label={`rag · ${retrieved_docs.length} doc${retrieved_docs.length !== 1 ? 's' : ''}`}
      accent="var(--color-purple)"
    >
      <div className="flex flex-col gap-2">

        {/* Header row: retrieval method badge + toggle */}
        <div className="flex items-center gap-3">
          <span
            className="px-2 py-0.5 rounded"
            style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
              background: 'var(--color-surface-2)',
              border: `1px solid ${methodColor}`,
              color: methodColor,
            }}
          >
            {method}
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--color-text-muted)', flex: 1 }}>
            {debug?.query_tokens?.slice(0, 6).join(' · ') ?? ''}
          </span>
          <button
            onClick={() => setExpanded(v => !v)}
            style={{
              padding: '2px 8px', background: 'transparent',
              border: '1px solid var(--color-border)', borderRadius: 3,
              color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)',
              fontSize: '0.72rem', cursor: 'pointer',
            }}
          >
            {expanded ? '▲ hide docs' : `▼ show docs (${retrieved_docs.length})`}
          </button>
        </div>

        {/* Doc list */}
        {expanded && (
          <div className="flex flex-col gap-1.5">
            {retrieved_docs.map((doc, i) => {
              const typeColor = DOC_TYPE_COLORS[doc.type] ?? 'var(--color-text-muted)'
              const scoreLabel = typeof doc.score === 'number'
                ? `score ${doc.score.toFixed(3)}`
                : null
              return (
                <div
                  key={i}
                  className="flex items-start gap-2 rounded px-2 py-1.5"
                  style={{
                    background: 'var(--color-surface-2)',
                    border: '1px solid var(--color-border-subtle)',
                  }}
                >
                  {/* Type chip */}
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
                      color: typeColor, whiteSpace: 'nowrap', paddingTop: 1,
                      border: `1px solid ${typeColor}`, borderRadius: 2,
                      padding: '1px 4px',
                    }}
                  >
                    {doc.type.replace('_', ' ')}
                  </span>

                  {/* Description */}
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)', fontSize: '0.75rem',
                      color: 'var(--color-text-soft)', flex: 1, lineHeight: 1.5,
                    }}
                  >
                    {doc.description?.slice(0, 120) ?? ''}
                    {doc.description?.length > 120 ? '…' : ''}
                  </span>

                  {/* Score */}
                  {scoreLabel && (
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)', fontSize: '0.68rem',
                        color: 'var(--color-text-muted)', whiteSpace: 'nowrap', paddingTop: 1,
                      }}
                    >
                      {scoreLabel}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        )}

      </div>
    </OutputBlock>
  )
}
