import { useRef } from 'react'
import type * as d3 from 'd3'
import type { Relationship } from '../../lib/model-parser'

type Props = {
  open: boolean
  height: number
  types: string[]
  relationships: Relationship[]
  colorScale: d3.ScaleOrdinal<string, string, never>
  onHeightChange: (h: number) => void
}

export function SchemaInfoPanel({ open, height, types, relationships, colorScale, onHeightChange }: Props) {
  const resizingRef = useRef(false)
  const startYRef = useRef(0)
  const startHRef = useRef(0)

  function onResizeMouseDown(e: React.MouseEvent) {
    if (!open) return
    resizingRef.current = true
    startYRef.current = e.clientY
    startHRef.current = height

    function onMove(ev: MouseEvent) {
      if (!resizingRef.current) return
      const delta = startYRef.current - ev.clientY
      onHeightChange(Math.min(600, Math.max(80, startHRef.current + delta)))
    }

    function onUp() {
      resizingRef.current = false
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    e.preventDefault()
  }

  const hasImplicit = relationships.some((r) => r.implicit)

  return (
    <>
      <div
        className={`viz-resize-handle${open ? ' visible' : ''}`}
        title="Arrastra para cambiar la altura del panel"
        onMouseDown={onResizeMouseDown}
      />
      <div
        className={`viz-info-panel${open ? ' open' : ''}`}
        style={open ? { maxHeight: height } : undefined}
      >
        <div className="viz-info-inner">
          <div>
            <h3>Tipos detectados</h3>
            {types.length ? (
              <ul style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: '0.82rem' }}>
                {types.map((t) => (
                  <li key={t} style={{ padding: '0.25rem 0', display: 'flex', alignItems: 'center', gap: '0.55rem', borderBottom: '1px solid var(--border)' }}>
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: '50%',
                        background: colorScale(t),
                        flexShrink: 0,
                        display: 'inline-block',
                        boxShadow: `0 0 0 2px ${colorScale(t)}30`,
                      }}
                    />
                    <span style={{ fontSize: '0.82rem', color: 'var(--text)' }}>{t}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p style={{ color: 'var(--muted)', margin: 0 }}>Sin tipos cargados.</p>
            )}
          </div>
          <div>
            <h3>Relaciones</h3>
            {relationships.length ? (
              <>
                {hasImplicit && (
                  <p style={{ fontSize: '0.75rem', color: 'var(--muted)', margin: '0 0 0.4rem' }}>
                    <span style={{ borderBottom: '2px dashed var(--implicit-line)', paddingBottom: 1 }}>─ ─</span>{' '}
                    Derivada de ejemplos del paquete
                  </p>
                )}
                <table className="rel-table">
                  <thead>
                    <tr>
                      <th>Origen</th>
                      <th>Propiedad</th>
                      <th>Destino</th>
                    </tr>
                  </thead>
                  <tbody>
                    {relationships.map((r, i) => {
                      const cf = colorScale(r.from)
                      const ct = colorScale(r.to)
                      return (
                        <tr key={i} style={r.implicit ? { opacity: 0.62, fontStyle: 'italic' } : undefined}>
                          <td>
                            <span className="type-badge" style={{ background: cf, color: 'var(--badge-fg)', borderColor: cf + '20' }}>
                              {r.from}
                            </span>
                          </td>
                          <td>
                            <code style={{ fontSize: '0.75rem' }}>{r.property}</code>
                            {r.implicit && (
                              <span title="Derivada de ejemplos" style={{ color: 'var(--muted)', fontSize: '0.7rem' }}>
                                {' ~'}
                              </span>
                            )}
                          </td>
                          <td>
                            <span className="type-badge" style={{ background: ct, color: 'var(--badge-fg)', borderColor: ct + '20' }}>
                              {r.to}
                            </span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </>
            ) : (
              <p style={{ color: 'var(--muted)', fontSize: '0.82rem', margin: 0 }}>
                Sin relaciones detectadas. Para mostrarlas, incluye un{' '}
                <code>descriptor.json</code> con la sección{' '}
                <code>&ldquo;relationships&rdquo;</code> y/o ejemplos en la carpeta{' '}
                <code>examples/</code>.
              </p>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
