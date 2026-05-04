import { useState } from 'react'
import type { UploadResponse } from './types'
import { useNotebook } from './hooks/useNotebook'
import { useThreePanelSplit } from './hooks/useThreePanelSplit'
import { ActivityBar } from './components/ActivityBar'
import { Sidebar } from './components/Sidebar'
import { DataPanel } from './components/DataPanel'
import { ResizeDivider } from './components/ResizeDivider'
import { ChatPanel } from './components/ChatPanel'

export default function App() {
  const [dataset, setDataset] = useState<UploadResponse | null>(null)
  const { cells, isLoading, handleSubmit, handleConfirm } = useNotebook(dataset)
  const {
    containerRef,
    sidebarWidth,
    chatWidth,
    onLeftDividerMouseDown,
    onRightDividerMouseDown,
  } = useThreePanelSplit({
    defaultSidebar: 220,
    defaultChat: 380,
    minSidebar: 120,
    maxSidebar: 400,
    minData: 260,
    minChat: 240,
    maxChat: 640,
  })

  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ background: 'var(--color-bg)', fontFamily: 'var(--font-ui)' }}
    >
      <ActivityBar />

      {/* Three-panel area: sidebar | DataPanel (flex-1) | ChatPanel */}
      <div ref={containerRef} className="flex flex-1 overflow-hidden">
        <Sidebar dataset={dataset} onDatasetChange={setDataset} width={sidebarWidth} />
        <ResizeDivider onMouseDown={onLeftDividerMouseDown} />
        <DataPanel dataset={dataset} />
        <ResizeDivider onMouseDown={onRightDividerMouseDown} />
        <ChatPanel
          dataset={dataset}
          cells={cells}
          isLoading={isLoading}
          onSubmit={handleSubmit}
          onConfirm={handleConfirm}
          width={chatWidth}
        />
      </div>
    </div>
  )
}
