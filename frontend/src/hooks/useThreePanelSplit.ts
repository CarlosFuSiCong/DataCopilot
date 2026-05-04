import { useCallback, useRef, useState } from 'react'

const DIVIDER_W = 4  // px, each divider

interface ThreePanelOptions {
  defaultSidebar?: number
  defaultChat?: number
  minSidebar?: number
  maxSidebar?: number
  minData?: number
  minChat?: number
  maxChat?: number
}

export function useThreePanelSplit({
  defaultSidebar = 220,
  defaultChat = 380,
  minSidebar = 120,
  maxSidebar = 480,
  minData = 260,
  minChat = 240,
  maxChat = 640,
}: ThreePanelOptions = {}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [sidebarWidth, setSidebarWidth] = useState(defaultSidebar)
  const [chatWidth, setChatWidth] = useState(defaultChat)

  // ── Left divider: only sidebar ↔ DataPanel ────────────────────────────────
  const onLeftDividerMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'

      function onMouseMove(ev: MouseEvent) {
        const rect = containerRef.current?.getBoundingClientRect()
        if (!rect) return
        const available = rect.width - chatWidth - DIVIDER_W * 2
        const raw = ev.clientX - rect.left
        const clamped = Math.min(
          Math.max(raw, minSidebar),
          Math.min(maxSidebar, available - minData),
        )
        setSidebarWidth(clamped)
      }

      function onMouseUp() {
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
        document.removeEventListener('mousemove', onMouseMove)
        document.removeEventListener('mouseup', onMouseUp)
      }

      document.addEventListener('mousemove', onMouseMove)
      document.addEventListener('mouseup', onMouseUp)
    },
    [chatWidth, minSidebar, maxSidebar, minData],
  )

  // ── Right divider: only DataPanel ↔ ChatPanel ────────────────────────────
  const onRightDividerMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'

      function onMouseMove(ev: MouseEvent) {
        const rect = containerRef.current?.getBoundingClientRect()
        if (!rect) return
        const available = rect.width - sidebarWidth - DIVIDER_W * 2
        const raw = rect.right - ev.clientX
        const clamped = Math.min(
          Math.max(raw, minChat),
          Math.min(maxChat, available - minData),
        )
        setChatWidth(clamped)
      }

      function onMouseUp() {
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
        document.removeEventListener('mousemove', onMouseMove)
        document.removeEventListener('mouseup', onMouseUp)
      }

      document.addEventListener('mousemove', onMouseMove)
      document.addEventListener('mouseup', onMouseUp)
    },
    [sidebarWidth, minChat, maxChat, minData],
  )

  return {
    containerRef,
    sidebarWidth,
    chatWidth,
    onLeftDividerMouseDown,
    onRightDividerMouseDown,
  }
}
