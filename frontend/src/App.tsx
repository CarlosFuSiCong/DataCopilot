import { useState } from 'react'
import type { ExecutionResult, UploadResponse, WorkflowStep } from './types'
import { useNotebook } from './hooks/useNotebook'
import { useThreePanelSplit } from './hooks/useThreePanelSplit'
import { ActivityBar } from './components/ActivityBar'
import { Sidebar } from './components/Sidebar'
import { DataPanel } from './components/DataPanel'
import { ResizeDivider } from './components/ResizeDivider'
import { ChatPanel } from './components/ChatPanel'

export default function App() {
  const [dataset, setDataset] = useState<UploadResponse | null>(null)
  const [suggestedQuery, setSuggestedQuery] = useState<string | undefined>(undefined)
  const { cells, isLoading, handleSubmit, handleConfirm, handleClarify, handleRerun } = useNotebook(dataset)
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

  // Counts confirmed cells — used as a refresh trigger for run history.
  const confirmedCount = cells.filter(c => c.status === 'ok').length

  // Last mutating confirmed cell drives the result tab. Read-only answers should not replace the data table.
  const lastConfirmedCell = [...cells].reverse().find(c =>
    c.status === 'ok' && (c.confirmResult || !c.result?.is_read_only)
  )
  const lastConfirmedSteps: WorkflowStep[] | null =
    lastConfirmedCell?.result?.planned_steps ?? null
  // execution_result lives in confirmResult (manual confirm) or result (auto-confirm)
  const lastExecutionResult: ExecutionResult | null =
    lastConfirmedCell?.confirmResult?.execution_result
    ?? lastConfirmedCell?.result?.execution_result
    ?? null
  // run_id for the persisted result CSV; used by DataPanel's download button.
  const lastRunId: string | null =
    lastConfirmedCell?.confirmResult?.run_id
    ?? lastConfirmedCell?.result?.run_id
    ?? null

  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ background: 'var(--color-bg)', fontFamily: 'var(--font-ui)' }}
    >
      <ActivityBar />

      {/* Three-panel area: sidebar | DataPanel (flex-1) | ChatPanel */}
      <div ref={containerRef} className="flex flex-1 overflow-hidden">
        <Sidebar dataset={dataset} onDatasetChange={setDataset} onRerun={handleRerun} historyRefreshKey={confirmedCount} width={sidebarWidth} />
        <ResizeDivider onMouseDown={onLeftDividerMouseDown} />
        <DataPanel
          dataset={dataset}
          lastExecutionResult={lastExecutionResult}
          lastConfirmedSteps={lastConfirmedSteps}
          lastRunId={lastRunId}
        />
        <ResizeDivider onMouseDown={onRightDividerMouseDown} />
        <ChatPanel
          dataset={dataset}
          cells={cells}
          isLoading={isLoading}
          onSubmit={handleSubmit}
          onConfirm={handleConfirm}
          onClarify={handleClarify}
          onRerun={handleRerun}
          onSuggest={setSuggestedQuery}
          suggestedQuery={suggestedQuery}
          onSuggestedQueryConsumed={() => setSuggestedQuery(undefined)}
          width={chatWidth}
        />
      </div>
    </div>
  )
}
