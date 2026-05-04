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
  const { leftWidth, containerRef, onDividerMouseDown } = useResizableSplit({
    defaultWidth: 620,
    minLeft: 300,
    minRight: 280,
  })

  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ background: 'var(--color-bg)', fontFamily: 'var(--font-ui)' }}
    >
      <ActivityBar />
      <Sidebar dataset={dataset} onDatasetChange={setDataset} />

      <div ref={containerRef} className="flex flex-1 overflow-hidden">
        <DataPanel dataset={dataset} width={leftWidth} />
        <ResizeDivider onMouseDown={onDividerMouseDown} />
        <ChatPanel
          dataset={dataset}
          cells={cells}
          isLoading={isLoading}
          onSubmit={handleSubmit}
          onConfirm={handleConfirm}
        />
      </div>
    </div>
  )
}
