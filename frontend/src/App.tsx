import { useState } from 'react'
import type { UploadResponse, ChatResponse } from './types'

export default function App() {
  const [dataset, setDataset] = useState<UploadResponse | null>(null)
  const [chatResult, setChatResult] = useState<ChatResponse | null>(null)

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--color-surface)', color: 'var(--color-text)' }}>
      <Header />
      <main className="flex-1 flex overflow-hidden">
        <Sidebar dataset={dataset} onDatasetChange={setDataset} onResult={setChatResult} />
        <ResultArea result={chatResult} />
      </main>
    </div>
  )
}

function Header() {
  return (
    <header
      className="flex items-center gap-3 px-6 py-4 border-b shrink-0"
      style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-1)' }}
    >
      <span className="font-mono text-sm font-semibold tracking-widest uppercase" style={{ color: 'var(--color-accent)' }}>
        DataCopilot
      </span>
      <span className="text-xs px-2 py-0.5 rounded" style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}>
        MVP
      </span>
    </header>
  )
}

interface SidebarProps {
  dataset: UploadResponse | null
  onDatasetChange: (d: UploadResponse | null) => void
  onResult: (r: ChatResponse | null) => void
}

function Sidebar({ dataset, onDatasetChange, onResult }: SidebarProps) {
  return (
    <aside
      className="w-80 shrink-0 flex flex-col border-r overflow-y-auto"
      style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface-1)' }}
    >
      {/* Upload placeholder */}
      <Section title="Dataset">
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          {dataset ? `✓ ${dataset.filename}  ${dataset.row_count} rows` : 'No CSV uploaded yet'}
        </p>
      </Section>

      {/* Chat placeholder */}
      <Section title="Query">
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          {dataset ? 'Enter a query...' : 'Upload a dataset first'}
        </p>
      </Section>

      {/* Suppress unused-var lint */}
      <span className="hidden">{String(onDatasetChange)}{String(onResult)}</span>
    </aside>
  )
}

interface ResultAreaProps {
  result: ChatResponse | null
}

function ResultArea({ result }: ResultAreaProps) {
  return (
    <div className="flex-1 flex flex-col overflow-hidden p-6 gap-4">
      {result ? (
        <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
          Result panels (Workflow / Table / Explanation) — coming soon
        </p>
      ) : (
        <EmptyState />
      )}
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4 opacity-40">
      <div className="w-12 h-12 rounded-lg border-2 flex items-center justify-center font-mono text-2xl"
        style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}>
        ∅
      </div>
      <p className="text-sm font-mono" style={{ color: 'var(--color-text-muted)' }}>
        Upload a CSV, enter a query, view results
      </p>
    </div>
  )
}

interface SectionProps {
  title: string
  children: React.ReactNode
}

function Section({ title, children }: SectionProps) {
  return (
    <div className="p-4 border-b" style={{ borderColor: 'var(--color-border-subtle)' }}>
      <h2 className="text-xs font-mono font-semibold uppercase tracking-widest mb-3"
        style={{ color: 'var(--color-text-muted)' }}>
        {title}
      </h2>
      {children}
    </div>
  )
}
