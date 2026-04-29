export function FilesIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
      <path d="M13.5 3H8.207L6.5 1.293A1 1 0 0 0 5.793 1H2.5a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1V4a1 1 0 0 0-1-1zM2.5 2h3.086l1.707 1.707A1 1 0 0 0 8 4h5.5v9h-11V2z" />
    </svg>
  )
}

export function SearchIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="currentColor">
      <path d="M10 6.5a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0zm-.691 3.516a4.5 4.5 0 1 1 .707-.707l3.337 3.338-.707.707-3.337-3.338z" />
    </svg>
  )
}

export function GearIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="currentColor">
      <path d="M7.5 5.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM4.5 7.5a3 3 0 1 1 6 0 3 3 0 0 1-6 0z" />
      <path d="M7.5 1a.5.5 0 0 1 .5.5V2.5a5.007 5.007 0 0 1 1.964.815l.707-.708a.5.5 0 0 1 .707.707l-.707.707A5.007 5.007 0 0 1 11.5 6h1a.5.5 0 0 1 0 1h-1a5.007 5.007 0 0 1-.829 1.979l.707.707a.5.5 0 0 1-.707.707l-.707-.707A5.007 5.007 0 0 1 8 10.5v1a.5.5 0 0 1-1 0v-1a5.007 5.007 0 0 1-1.964-.815l-.707.707a.5.5 0 0 1-.707-.707l.707-.707A5.007 5.007 0 0 1 3.5 7.5h-1a.5.5 0 0 1 0-1h1a5.007 5.007 0 0 1 .829-1.979l-.707-.707a.5.5 0 0 1 .707-.707l.707.707A5.007 5.007 0 0 1 7 2.5v-1a.5.5 0 0 1 .5-.5z" />
    </svg>
  )
}

export function ChevronIcon() {
  return (
    <svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor">
      <path d="M2 1l3 3-3 3" stroke="currentColor" strokeWidth="1.2" fill="none" />
    </svg>
  )
}

export function NotebookIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
      <path d="M3 1a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1H3zm0 1h10v12H3V2zm2 2v1h6V4H5zm0 3v1h6V7H5zm0 3v1h4v-1H5z" />
    </svg>
  )
}

export function Spinner() {
  return (
    <svg
      width="14" height="14" viewBox="0 0 14 14" fill="none"
      style={{ animation: 'spin 1s linear infinite' }}
    >
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <circle
        cx="7" cy="7" r="5.5"
        stroke="var(--color-text-muted)" strokeWidth="1.5"
        strokeDasharray="22" strokeDashoffset="8"
      />
    </svg>
  )
}
