import { NotebookIcon } from '../ui/Icons'

export function DataPanelEmpty() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 h-full"
      style={{ color: 'var(--color-text-muted)', padding: 32 }}>
      <NotebookIcon size={36} />
      <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '0.82rem', textAlign: 'center', lineHeight: 1.8 }}>
        Upload a CSV file<br />to preview the data here.
      </p>
    </div>
  )
}
