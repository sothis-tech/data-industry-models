import { useCallback, useEffect, useState, type RefObject } from 'react'

/** Ancho mínimo del contenedor para lista (~240px) + detalle útil (~320px). */
export const ENTITIES_SPLIT_MIN_PX = 560

export type EntitiesStackPane = 'list' | 'detail'

export function useEntitiesStackLayout(containerRef: RefObject<HTMLElement | null>) {
  const [isStacked, setIsStacked] = useState(false)
  const [stackPane, setStackPane] = useState<EntitiesStackPane>('list')

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const update = (width: number) => {
      setIsStacked(width < ENTITIES_SPLIT_MIN_PX)
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
  }, [containerRef])

  const focusDetailPane = useCallback(() => setStackPane('detail'), [])
  const focusListPane = useCallback(() => setStackPane('list'), [])

  return {
    isStacked,
    stackPane,
    setStackPane,
    focusDetailPane,
    focusListPane,
  }
}
