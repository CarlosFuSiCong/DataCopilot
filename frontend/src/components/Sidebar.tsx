import { useRef, useState } from 'react'
import type { UploadResponse } from '../types'
import { uploadDataset } from '../api/client'
import { ChevronIcon } from './ui/Icons'

interface SidebarProps {
  dataset: UploadResponse | null
  onDatasetChange: (d: UploadResponse | null) => void
  width: number
}

export function Sidebar({ dataset, onDatasetChange, width }: SidebarProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadError(null)
    try {
      const result = await uploadDataset(file)
      onDatasetChange(result)
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div
      className="flex flex-col shrink-0 overflow-y-auto"
      style={{ width, background: 'var(--color-surface)', borderRight: '1px solid var(--color-border)' }}
    >
      <div
        className="flex items-center gap-2 px-3 py-2 uppercase tracking-widest"
        style={{
          fontSize: '0.68rem', fontWeight: 600,
          color: 'var(--color-text-muted)',
          borderBottom: '1px solid var(--color-border-subtle)',
          fontFamily: 'var(--font-mono)',
        }}
      >
        Explorer
      </div>

      <SidebarSection label="DATASET">
        <input
          ref={fileRef}
          type="file"
          accept=".csv"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />

        {dataset ? (
          <div className="px-3 py-2 flex flex-col gap-1">
            <div
              className="flex items-center gap-1.5 rounded px-2 py-1.5"
              style={{ background: 'var(--color-surface-2)' }}
            >
              <span style={{ color: 'var(--color-green)', fontSize: '0.68rem' }}>●</span>
              <span
                className="truncate"
                style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--color-text)' }}
              >
                {dataset.filename}
              </span>
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-muted)', paddingLeft: 8 }}>
              {dataset.row_count.toLocaleString()} rows · {dataset.column_count} cols
            </div>
            <button
              onClick={() => fileRef.current?.click()}
              style={{
                marginTop: 4, padding: '4px 8px', borderRadius: 3,
                background: 'transparent', border: '1px solid var(--color-border)',
                color: 'var(--color-text-soft)', fontFamily: 'var(--font-mono)',
                fontSize: '0.75rem', cursor: 'pointer', textAlign: 'left',
              }}
            >
              ↺ Replace file
            </button>
          </div>
        ) : (
          <div className="px-3 py-2 flex flex-col gap-2">
            <p style={{ fontSize: '0.82rem', color: 'var(--color-text-muted)', margin: 0 }}>
              No file loaded.
            </p>
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              style={{
                padding: '5px 8px', borderRadius: 3,
                background: 'var(--color-accent-subtle)',
                border: '1px solid var(--color-accent-dim)',
                color: 'var(--color-accent)',
                fontFamily: 'var(--font-mono)', fontSize: '0.75rem',
                cursor: uploading ? 'not-allowed' : 'pointer',
                opacity: uploading ? 0.6 : 1,
              }}
            >
              {uploading ? '⟳ Uploading…' : '+ Upload CSV'}
            </button>
            {uploadError && (
              <p style={{ fontSize: '0.75rem', color: 'var(--color-red)', margin: 0 }}>
                ✕ {uploadError}
              </p>
            )}
          </div>
        )}
      </SidebarSection>

      {dataset && (
        <SidebarSection label="SCHEMA">
          <div className="px-3 py-1.5 flex flex-col gap-0.5">
            {dataset.columns.slice(0, 10).map(col => (
              <div key={col.name} className="flex items-center justify-between gap-2">
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {col.name}
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--color-purple)', flexShrink: 0 }}>
                  {col.dtype}
                </span>
              </div>
            ))}
            {dataset.columns.length > 10 && (
              <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                +{dataset.columns.length - 10} more
              </span>
            )}
          </div>
        </SidebarSection>
      )}

      <SidebarSection label="KERNEL">
        <div className="px-3 py-1.5 flex items-center gap-2">
          <span style={{ color: 'var(--color-green)', fontSize: '0.68rem' }}>●</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--color-text-soft)' }}>
            Python · FastAPI
          </span>
        </div>
      </SidebarSection>
    </div>
  )
}

export function SidebarSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
      <div
        className="px-3 py-1.5 flex items-center gap-1"
        style={{
          fontSize: '0.68rem', fontWeight: 600,
          color: 'var(--color-text-muted)',
          letterSpacing: '0.1em',
          fontFamily: 'var(--font-mono)',
        }}
      >
        <ChevronIcon />
        {label}
      </div>
      {children}
    </div>
  )
}
