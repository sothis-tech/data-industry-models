import { useEffect, useState, type RefObject } from 'react'

/** Por debajo de este ancho, filtros Orion y detalle pasan a drawers. */
export const VIZ_CANVAS_COMPACT_MAX_PX = 640

export function useVizCanvasCompact(canvasRef: RefObject<HTMLElement | null>) {
  const [isCompact, setIsCompact] = useState(false)

  useEffect(() => {
    const el = canvasRef.current
    if (!el) return

    const update = (width: number) => {
      setIsCompact(width < VIZ_CANVAS_COMPACT_MAX_PX)
    }

    const ro = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return
      const size = entry.contentBoxSize
      const width = size?.[0]?.inlineSize ?? entry.contentRect.width
      update(width)
    })

    ro.observe(el)
    update(el.getBoundingClientRect().width)

    return () => ro.disconnect()
  }, [canvasRef])

  return { isCompact }
}
