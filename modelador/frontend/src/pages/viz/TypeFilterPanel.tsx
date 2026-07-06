import { useEffect, useId, useRef } from 'react'
import type * as d3 from 'd3'
import { resolveTypeColor } from '../../lib/graph-utils'

type Props = {
  typeKeys: string[]
  activeKeys: string[]
  colorScale: d3.ScaleOrdinal<string, string, never>
  onChange: (newKeys: string[]) => void
  disabled?: boolean
}

export function TypeFilterPanel({ typeKeys, activeKeys, colorScale, onChange, disabled = false }: Props) {
  const masterId = useId()
  const masterRef = useRef<HTMLInputElement>(null)
  const activeSet = new Set(activeKeys)

  useEffect(() => {
    const cb = masterRef.current
    if (!cb) return
    const checked = activeKeys.length
    if (checked === 0) {
      cb.indeterminate = false
      cb.checked = false
    } else if (checked === typeKeys.length) {
      cb.indeterminate = false
      cb.checked = true
    } else {
      cb.indeterminate = true
      cb.checked = false
    }
  }, [activeKeys, typeKeys.length])

  function handleMasterChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (disabled) return
    onChange(e.target.checked ? [...typeKeys] : [])
  }

  function handleRowChange(key: string, checked: boolean) {
    if (disabled) return
    if (checked) {
      onChange([...activeKeys, key])
    } else {
      onChange(activeKeys.filter((k) => k !== key))
    }
  }

  const allOn  = activeKeys.length === typeKeys.length
  const allOff = activeKeys.length === 0

  return (
    <div className={`orion-type-filter${disabled ? ' is-disabled' : ''}`} aria-disabled={disabled || undefined}>
      <div className="orion-type-filter-head">
        <label className="orion-type-filter-master" title="Seleccionar o deseleccionar todos">
          <input
            ref={masterRef}
            type="checkbox"
            id={masterId}
            aria-label="Seleccionar o deseleccionar todos los tipos"
            disabled={disabled}
            onChange={handleMasterChange}
          />
        </label>
        <div className="orion-type-filter-title">
          Tipos
          <span className="orion-type-filter-count">
            {allOn ? 'todos' : allOff ? 'ninguno' : `${activeKeys.length}/${typeKeys.length}`}
          </span>
        </div>
      </div>
      <div className="orion-type-filter-list">
        {typeKeys.map((k) => {
          const c = resolveTypeColor(k, colorScale)
          const isActive = activeSet.has(k)
          return (
            <label
              key={k}
              className={`orion-type-filter-row${isActive ? '' : ' dimmed'}`}
              title={disabled ? 'Desactivado mientras buscas' : k}
            >
              <input
                type="checkbox"
                checked={isActive}
                disabled={disabled}
                onChange={(e) => handleRowChange(k, e.target.checked)}
              />
              <span
                className="orion-type-filter-dot"
                style={{ background: c, border: `1px solid ${c}`, opacity: isActive ? 1 : 0.35 }}
              />
              <span className="orion-type-filter-label">{k}</span>
            </label>
          )
        })}
      </div>
    </div>
  )
}
