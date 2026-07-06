import { useCallback, useEffect, useRef, useState } from 'react'
import { ENTITIES_SPLIT_MIN_PX } from './useEntitiesStackLayout'

const LIST_MIN_PX = 260
const LIST_MAX_PX = 560

function clamp(px: number, containerWidth: number): number {
  const maxByLayout = Math.max(LIST_MIN_PX, Math.floor(containerWidth * 0.6))
  return Math.min(Math.max(px, LIST_MIN_PX), Math.min(LIST_MAX_PX, maxByLayout))
}

export function useSplitResize(storageKey: string, defaultWidth = 320) {
  const containerRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)

  const [width, setWidth] = useState<number>(() => {
    const saved = Number(localStorage.getItem(storageKey))
    return Number.isFinite(saved) && saved > 0 ? saved : defaultWidth
  })

  const save = useCallback((px: number) => {
    localStorage.setItem(storageKey, String(px))
  }, [storageKey])

  const applyWidth = useCallback((px: number) => {
    const containerWidth = containerRef.current?.clientWidth ?? LIST_MAX_PX * 2
    const clamped = clamp(px, containerWidth)
    setWidth(clamped)
    return clamped
  }, [])

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (window.matchMedia(`(max-width: ${ENTITIES_SPLIT_MIN_PX - 1}px)`).matches) return
    e.preventDefault()
    dragging.current = true
    document.body.classList.add('is-col-resizing')
  }, [])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current || !containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      applyWidth(e.clientX - rect.left)
    }
    const onUp = () => {
      if (!dragging.current) return
      dragging.current = false
      document.body.classList.remove('is-col-resizing')
      const current = panelRef.current ? parseInt(panelRef.current.style.width, 10) : width
      if (Number.isFinite(current)) save(current)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    document.addEventListener('mouseleave', onUp)
    return () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.removeEventListener('mouseleave', onUp)
    }
  }, [applyWidth, save, width])

  useEffect(() => {
    const onResize = () => applyWidth(width)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [applyWidth, width])

  const onKeyDown = useCallback((e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 30 : 14
    if (e.key === 'ArrowLeft') { e.preventDefault(); const w = applyWidth(width - step); save(w) }
    else if (e.key === 'ArrowRight') { e.preventDefault(); const w = applyWidth(width + step); save(w) }
    else if (e.key === 'Home') { e.preventDefault(); const w = applyWidth(LIST_MIN_PX); save(w) }
    else if (e.key === 'End') { e.preventDefault(); const w = applyWidth(LIST_MAX_PX); save(w) }
  }, [applyWidth, save, width])

  return { containerRef, panelRef, width, resizerProps: { onMouseDown, onKeyDown } }
}
