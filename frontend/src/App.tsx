import { useState } from 'react'
import type { UploadResponse } from './types'
import { useNotebook } from './hooks/useNotebook'
import { useResizableSplit } from './hooks/useResizableSplit'
import { ActivityBar } from './components/ActivityBar'
import { Sidebar } from './components/Sidebar'
import { DataPanel } from './components/DataPanel'
import { ResizeDivider } from './components/ResizeDivider'
import { ChatPanel } from './components/ChatPanel'

export default function App() {
  const [dataset, setDataset] = useState<UploadResponse | null>(null)
  const { cells, isLoading, handleSubmit, handleConfirm } = useNotebook(dataset)

  // Sidebar ↔ main area split
  const sidebarSplit = useResizableSplit({ defaultWidth: 220, minLeft: 140, minRight: 580 })

  // DataPanel ↔ ChatPanel split (within main area)
  const dataSplit = useResizableSplit({ defaultWidth: 620, minLeft: 300, minRight: 280 })

  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ background: 'var(--color-bg)', fontFamily: 'var(--font-ui)' }}
    >
      <ActivityBar />

      {/* Sidebar + main, sharing the sidebar resize container */}
      <div ref={sidebarSplit.containerRef} className="flex flex-1 overflow-hidden">
        <Sidebar
          dataset={dataset}
          onDatasetChange={setDataset}
          width={sidebarSplit.leftWidth}
        />
        <ResizeDivider onMouseDown={sidebarSplit.onDividerMouseDown} />

        {/* DataPanel + ChatPanel, sharing the data resize container */}
        <div ref={dataSplit.containerRef} className="flex flex-1 overflow-hidden">
          <DataPanel dataset={dataset} width={dataSplit.leftWidth} />
          <ResizeDivider onMouseDown={dataSplit.onDividerMouseDown} />
          <ChatPanel
            dataset={dataset}
            cells={cells}
            isLoading={isLoading}
            onSubmit={handleSubmit}
            onConfirm={handleConfirm}
          />
        </div>
      </div>
    </div>
  )
}
