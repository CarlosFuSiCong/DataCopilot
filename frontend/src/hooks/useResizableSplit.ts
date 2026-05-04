import { useCallback, useRef, useState } from 'react'

interface ResizableSplitOptions {
  defaultWidth: number
  minLeft: number
  minRight: number
}

export function useResizableSplit({ defaultWidth, minLeft, minRight }: ResizableSplitOptions) {
  const [leftWidth, setLeftWidth] = useState(defaultWidth)
  const containerRef = useRef<HTMLDivElement>(null)
  const isDragging = useRef(false)

  const onDividerMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    isDragging.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    function onMouseMove(ev: MouseEvent) {
      if (!isDragging.current || !containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const newWidth = ev.clientX - rect.left
      setLeftWidth(Math.min(Math.max(newWidth, minLeft), rect.width - minRight))
    }

    function onMouseUp() {
      isDragging.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }, [minLeft, minRight])

  return { leftWidth, containerRef, onDividerMouseDown }
}
