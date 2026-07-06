import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'

export const AGENT_RAIL_WIDTH_PX = 40
const RESIZER_WIDTH_PX = 5
const PANEL_MIN_PX = 360
const PANEL_MAX_RATIO = 0.55
const PANEL_EXPANDED_RATIO = 0.72
const PANEL_DEFAULT_PX = 420

const STORAGE_WIDTH = 'ngsi_agent_panel_width'
const STORAGE_OPEN = 'ngsi_agent_panel_open'
const STORAGE_EXPANDED = 'ngsi_agent_panel_expanded'

function readBool(key: string, fallback: boolean): boolean {
  const raw = localStorage.getItem(key)
  if (raw === '1' || raw === 'true') return true
  if (raw === '0' || raw === 'false') return false
  return fallback
}

function clampPanelWidth(px: number, containerWidth: number): number {
  const maxPx = Math.max(PANEL_MIN_PX, Math.floor(containerWidth * PANEL_MAX_RATIO))
  return Math.min(Math.max(px, PANEL_MIN_PX), maxPx)
}

export function useAgentPanelResize(bodyRef: RefObject<HTMLDivElement | null>) {
  const dragging = useRef(false)
  const widthBeforeExpandRef = useRef<number | null>(null)

  const [isOpen, setIsOpen] = useState(() => readBool(STORAGE_OPEN, false))
  const [isExpanded, setIsExpanded] = useState(() => readBool(STORAGE_EXPANDED, false))
  const [panelWidth, setPanelWidth] = useState(() => {
    const saved = Number(localStorage.getItem(STORAGE_WIDTH))
    return Number.isFinite(saved) && saved >= PANEL_MIN_PX ? saved : PANEL_DEFAULT_PX
  })

  const persistOpen = useCallback((open: boolean) => {
    localStorage.setItem(STORAGE_OPEN, open ? '1' : '0')
  }, [])

  const persistWidth = useCallback((px: number) => {
    localStorage.setItem(STORAGE_WIDTH, String(px))
  }, [])

  const applyWidth = useCallback((px: number) => {
    const containerWidth = bodyRef.current?.clientWidth ?? window.innerWidth
    const clamped = clampPanelWidth(px, containerWidth)
    setPanelWidth(clamped)
    return clamped
  }, [bodyRef])

  const openPanel = useCallback(() => {
    setIsOpen(true)
    persistOpen(true)
  }, [persistOpen])

  const closePanel = useCallback(() => {
    setIsOpen(false)
    setIsExpanded(false)
    localStorage.setItem(STORAGE_EXPANDED, '0')
    persistOpen(false)
  }, [persistOpen])

  const persistExpanded = useCallback((expanded: boolean) => {
    localStorage.setItem(STORAGE_EXPANDED, expanded ? '1' : '0')
  }, [])

  const toggleExpanded = useCallback(() => {
    const containerWidth = bodyRef.current?.clientWidth ?? window.innerWidth
    setIsExpanded((prev) => {
      const next = !prev
      if (next) {
        widthBeforeExpandRef.current = panelWidth
        const expandedPx = Math.max(
          PANEL_MIN_PX,
          Math.floor(containerWidth * PANEL_EXPANDED_RATIO) - AGENT_RAIL_WIDTH_PX - RESIZER_WIDTH_PX,
        )
        applyWidth(expandedPx)
        persistWidth(expandedPx)
      } else if (widthBeforeExpandRef.current != null) {
        const restored = applyWidth(widthBeforeExpandRef.current)
        persistWidth(restored)
        widthBeforeExpandRef.current = null
      }
      persistExpanded(next)
      return next
    })
  }, [applyWidth, bodyRef, panelWidth, persistExpanded, persistWidth])

  const togglePanel = useCallback(() => {
    setIsOpen((prev) => {
      const next = !prev
      persistOpen(next)
      return next
    })
  }, [persistOpen])

  const onResizerMouseDown = useCallback((e: React.MouseEvent) => {
    if (!isOpen || isExpanded || window.matchMedia('(max-width: 768px)').matches) return
    e.preventDefault()
    dragging.current = true
    document.body.classList.add('is-col-resizing')
  }, [isExpanded, isOpen])

  const onResizerKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (!isOpen || isExpanded) return
    const step = e.shiftKey ? 40 : 16
    if (e.key === 'ArrowLeft') {
      e.preventDefault()
      const w = applyWidth(panelWidth + step)
      persistWidth(w)
    } else if (e.key === 'ArrowRight') {
      e.preventDefault()
      const w = applyWidth(panelWidth - step)
      persistWidth(w)
    } else if (e.key === 'Home') {
      e.preventDefault()
      const w = applyWidth(PANEL_MIN_PX)
      persistWidth(w)
    } else if (e.key === 'End') {
      e.preventDefault()
      const containerWidth = bodyRef.current?.clientWidth ?? window.innerWidth
      const w = applyWidth(Math.floor(containerWidth * PANEL_MAX_RATIO))
      persistWidth(w)
    }
  }, [applyWidth, bodyRef, isExpanded, isOpen, panelWidth, persistWidth])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current || !bodyRef.current) return
      const rect = bodyRef.current.getBoundingClientRect()
      const totalAside = rect.right - e.clientX
      const contentWidth = totalAside - AGENT_RAIL_WIDTH_PX - RESIZER_WIDTH_PX
      applyWidth(contentWidth)
    }
    const onUp = () => {
      if (!dragging.current) return
      dragging.current = false
      document.body.classList.remove('is-col-resizing')
      persistWidth(panelWidth)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    document.addEventListener('mouseleave', onUp)
    return () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.removeEventListener('mouseleave', onUp)
    }
  }, [applyWidth, bodyRef, panelWidth, persistWidth])

  useEffect(() => {
    if (!isOpen || !isExpanded) return
    const containerWidth = bodyRef.current?.clientWidth ?? window.innerWidth
    const expandedPx = Math.max(
      PANEL_MIN_PX,
      Math.floor(containerWidth * PANEL_EXPANDED_RATIO) - AGENT_RAIL_WIDTH_PX - RESIZER_WIDTH_PX,
    )
    applyWidth(expandedPx)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const onResize = () => {
      if (isExpanded) {
        const containerWidth = bodyRef.current?.clientWidth ?? window.innerWidth
        const expandedPx = Math.max(
          PANEL_MIN_PX,
          Math.floor(containerWidth * PANEL_EXPANDED_RATIO) - AGENT_RAIL_WIDTH_PX - RESIZER_WIDTH_PX,
        )
        applyWidth(expandedPx)
      } else {
        applyWidth(panelWidth)
      }
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [applyWidth, bodyRef, isExpanded, panelWidth])

  const asideWidth = isOpen
    ? panelWidth + AGENT_RAIL_WIDTH_PX + RESIZER_WIDTH_PX
    : AGENT_RAIL_WIDTH_PX

  return {
    isOpen,
    isExpanded,
    openPanel,
    closePanel,
    togglePanel,
    toggleExpanded,
    panelWidth,
    asideWidth,
    resizerProps: { onMouseDown: onResizerMouseDown, onKeyDown: onResizerKeyDown },
  }
}
