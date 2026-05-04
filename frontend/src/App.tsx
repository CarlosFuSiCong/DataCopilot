import { useCallback, useRef, useState } from 'react'
import type { UploadResponse } from './types'
import type { NotebookCellData } from './types/notebook'
import { ActivityBar } from './components/ActivityBar'
import { Sidebar } from './components/Sidebar'
import { DataPreview } from './components/DataPreview'
import { Notebook } from './components/Notebook'
import { NotebookIcon } from './components/ui/Icons'

const DATA_PANEL_MIN = 300
const CHAT_PANEL_MIN = 280
const DATA_PANEL_DEFAULT = 620

export default function App() {
  const [dataset, setDataset] = useState<UploadResponse | null>(null)
  const [cells, setCells] = useState<NotebookCellData[]>([])
  const [dataPanelWidth, setDataPanelWidth] = useState(DATA_PANEL_DEFAULT)
  const isDragging = useRef(false)
  const containerRef = useRef<HTMLDivElement>(null)

  function appendCell(cell: NotebookCellData) {
    setCells(prev => {
      if (cell.status !== 'loading') {
        const idx = [...prev].reverse().findIndex(c => c.id === cell.id)
        if (idx !== -1) {
          const realIdx = prev.length - 1 - idx
          const next = [...prev]
          next[realIdx] = cell
          return next
        }
      }
      return [...prev, cell]
    })
  }

  const onDividerMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    isDragging.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    function onMouseMove(ev: MouseEvent) {
      if (!isDragging.current || !containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const totalWidth = rect.width
      const newWidth = ev.clientX - rect.left
      const clamped = Math.min(
        Math.max(newWidth, DATA_PANEL_MIN),
        totalWidth - CHAT_PANEL_MIN,
      )
      setDataPanelWidth(clamped)
    }

    function onMouseUp() {
      isDragging.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }, [])

  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ background: 'var(--color-bg)', fontFamily: 'var(--font-ui)' }}
    >
      <ActivityBar />
      <Sidebar dataset={dataset} onDatasetChange={setDataset} />

      {/* Main area — data panel + divider + chat panel */}
      <div ref={containerRef} className="flex flex-1 overflow-hidden">

        {/* Data panel (persistent) */}
        <div
          className="flex flex-col overflow-hidden shrink-0"
          style={{
            width: dataPanelWidth,
            borderRight: '1px solid var(--color-border)',
            background: 'var(--color-bg)',
          }}
        >
          {/* Data panel tab bar */}
          <div
            className="flex items-center shrink-0"
            style={{
              height: 36,
              background: 'var(--color-surface)',
              borderBottom: '1px solid var(--color-border)',
              paddingLeft: 8,
            }}
          >
            <div
              className="flex items-center gap-1.5 px-3 h-full"
              style={{
                borderRight: '1px solid var(--color-border)',
                borderBottom: '2px solid var(--color-blue)',
                background: 'var(--color-surface-1)',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.82rem',
                color: 'var(--color-blue)',
              }}
            >
              <span style={{ fontSize: '0.78rem' }}>⊞</span>
              <span>data.csv</span>
            </div>
          </div>

          {/* Data panel content */}
          <div className="flex-1 overflow-hidden">
            {dataset ? (
              <DataPreview dataset={dataset} />
            ) : (
              <DataPanelEmpty />
            )}
          </div>
        </div>

        {/* Drag divider */}
        <div
          onMouseDown={onDividerMouseDown}
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

        {/* Chat panel */}
        <div className="flex flex-col flex-1 overflow-hidden" style={{ minWidth: CHAT_PANEL_MIN }}>
          <Notebook cells={cells} onAppendCell={appendCell} dataset={dataset} />
        </div>

      </div>
    </div>
  )
}

function DataPanelEmpty() {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 h-full"
      style={{ color: 'var(--color-text-muted)', padding: 32 }}
    >
      <NotebookIcon size={36} />
      <p style={{
        margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.82rem',
        textAlign: 'center', lineHeight: 1.8, color: 'var(--color-text-muted)',
      }}>
        Upload a CSV file<br />to preview the data here.
      </p>
    </div>
  )
}
