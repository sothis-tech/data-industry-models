import type * as d3 from 'd3'
import type { OrionGraphNode } from '../../types/graph'
import { resolveTypeColor, typeKeyFromFullType } from '../../lib/graph-utils'
import { TypeFilterPanel } from './TypeFilterPanel'

type Props = {
  id?: string
  compact?: boolean
  onClose?: () => void
  search: string
  onSearchChange: (value: string) => void
  onClearSearch: () => void
  searchHits: OrionGraphNode[]
  focusedEntityId?: string | null
  onSelectEntity: (node: OrionGraphNode) => void
  typeKeys: string[]
  activeTypeKeys: string[]
  colorScale: d3.ScaleOrdinal<string, string, never>
  onTypeFilterChange: (keys: string[]) => void
  typeFilterDisabled?: boolean
}

export function OrionSidePanel({
  id = 'orion-side-panel',
  compact = false,
  onClose,
  search,
  onSearchChange,
  onClearSearch,
  searchHits,
  focusedEntityId = null,
  onSelectEntity,
  typeKeys,
  activeTypeKeys,
  colorScale,
  onTypeFilterChange,
  typeFilterDisabled = false,
}: Props) {
  const q = search.trim()
  const showClear = search.length > 0

  const searchBlock = (
    <div className="orion-search">
      <label className="orion-search-label" htmlFor="orion-entity-search">
        Buscar instancia
      </label>
      <div className="orion-search-field">
        <input
          id="orion-entity-search"
          type="text"
          className="orion-search-input"
          placeholder="ID, nombre o tipo…"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape' && search.length > 0) {
              e.preventDefault()
              onClearSearch()
            }
          }}
          autoComplete="off"
          spellCheck={false}
          role="searchbox"
          aria-controls="orion-search-hits"
        />
        {showClear && (
          <button
            type="button"
            className="orion-search-clear"
            onMouseDown={(e) => {
              e.preventDefault()
              onClearSearch()
            }}
            aria-label="Limpiar búsqueda y mostrar todo el grafo"
            title="Limpiar búsqueda"
          >
            ×
          </button>
        )}
      </div>
      {q && (
        <p className="orion-search-meta">
          {searchHits.length === 0
            ? 'Sin coincidencias en el grafo cargado'
            : `${searchHits.length} coincidencia${searchHits.length === 1 ? '' : 's'}`}
        </p>
      )}
      <ul id="orion-search-hits" className="orion-search-hits" aria-live="polite">
        {q &&
          searchHits.map((node) => {
            const typeKey = typeKeyFromFullType(node.type || '')
            const c = resolveTypeColor(node.type || '', colorScale)
            return (
              <li key={node.id}>
                <button
                  type="button"
                  className={`orion-search-hit${focusedEntityId === node.id ? ' is-selected' : ''}`}
                  onClick={() => onSelectEntity(node)}
                  title={node.id}
                >
                  <span className="orion-search-hit-dot" style={{ background: c }} />
                  <span className="orion-search-hit-text">
                    <span className="orion-search-hit-label">
                      {node.label || node.id.split(':').pop()}
                    </span>
                    <span className="orion-search-hit-sub">
                      {typeKey} · {node.id.split(':').pop()}
                    </span>
                  </span>
                </button>
              </li>
            )
          })}
      </ul>
    </div>
  )

  return (
    <aside
      id={id}
      className={`orion-side-panel${compact ? ' orion-side-panel--drawer' : ''}`}
      aria-label="Filtros y búsqueda de instancias"
    >
      {compact && (
        <div className="orion-side-panel-drawer-head">
          <span className="orion-side-panel-drawer-title">Filtros y búsqueda</span>
          <button
            type="button"
            className="orion-side-panel-drawer-close"
            onClick={onClose}
            aria-label="Cerrar filtros"
          >
            ✕
          </button>
        </div>
      )}
      {typeKeys.length > 0 && (
        <TypeFilterPanel
          typeKeys={typeKeys}
          activeKeys={activeTypeKeys}
          colorScale={colorScale}
          onChange={onTypeFilterChange}
          disabled={typeFilterDisabled}
        />
      )}

      {compact ? (
        <div className="orion-side-panel-drawer-body">
          {typeFilterDisabled && (
            <p className="orion-filter-hint">
              Mientras escribes, el grafo muestra coincidencias. Elige una instancia o limpia la búsqueda para volver al filtro por tipos.
            </p>
          )}
          {searchBlock}
        </div>
      ) : (
        <>
          {typeFilterDisabled && (
            <p className="orion-filter-hint">
              Mientras escribes, el grafo muestra coincidencias. Elige una instancia o limpia la búsqueda para volver al filtro por tipos.
            </p>
          )}
          {searchBlock}
        </>
      )}
    </aside>
  )
}
