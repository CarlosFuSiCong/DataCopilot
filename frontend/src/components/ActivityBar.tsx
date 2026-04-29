import { FilesIcon, SearchIcon, GearIcon } from './ui/Icons'

export function ActivityBar() {
  return (
    <div
      className="flex flex-col items-center gap-1 py-3 shrink-0"
      style={{
        width: 44,
        background: 'var(--color-gutter)',
        borderRight: '1px solid var(--color-border-subtle)',
      }}
    >
      <div
        className="flex items-center justify-center rounded mb-2"
        style={{
          width: 28,
          height: 28,
          background: 'var(--color-accent)',
          fontFamily: 'var(--font-mono)',
          fontSize: '0.68rem',
          fontWeight: 600,
          color: '#0d1117',
          letterSpacing: '-0.02em',
        }}
      >
        DC
      </div>

      <ActivityIcon label="Explorer" active><FilesIcon /></ActivityIcon>
      <ActivityIcon label="Search"><SearchIcon /></ActivityIcon>
      <div className="flex-1" />
      <ActivityIcon label="Settings"><GearIcon /></ActivityIcon>
    </div>
  )
}

function ActivityIcon({
  children,
  label,
  active,
}: {
  children: React.ReactNode
  label: string
  active?: boolean
}) {
  return (
    <button
      title={label}
      style={{
        width: 32, height: 32,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'transparent', border: 'none', cursor: 'pointer',
        borderRadius: 4,
        color: active ? 'var(--color-text-heading)' : 'var(--color-text-muted)',
        borderLeft: active ? '2px solid var(--color-accent)' : '2px solid transparent',
      }}
    >
      {children}
    </button>
  )
}
