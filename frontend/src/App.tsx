import { useState } from 'react'
import type { UploadResponse } from './types'
import type { NotebookCellData } from './types/notebook'
import { ActivityBar } from './components/ActivityBar'
import { Sidebar } from './components/Sidebar'
import { Notebook } from './components/Notebook'


export default function App() {
  const [dataset, setDataset] = useState<UploadResponse | null>(null)
  const [cells, setCells] = useState<NotebookCellData[]>([])

  function appendCell(cell: NotebookCellData) {
    setCells(prev => {
      // When a result arrives (ok/error), replace the matching loading cell by id
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

  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ background: 'var(--color-bg)', fontFamily: 'var(--font-ui)' }}
    >
      <ActivityBar />
      <Sidebar dataset={dataset} onDatasetChange={setDataset} />
      <Notebook cells={cells} onAppendCell={appendCell} dataset={dataset} />
    </div>
  )
}
