import { useTranslation } from 'react-i18next'
import type * as d3 from 'd3'
import type { SubscriptionFilterMode } from '../../lib/subscriptions'
import type { OrionGraphNode } from '../../types/graph'
import { resolveTypeColor, typeKeyFromFullType } from '../../lib/graph-utils'
import { SubscriptionFilterPanel } from './SubscriptionFilterPanel'
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
  subscriptionFilter: SubscriptionFilterMode
  onSubscriptionFilterChange: (mode: SubscriptionFilterMode) => void
  subscribedCount: number
  subscriptionFilterDisabled?: boolean
  subscriptionError?: string | null
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
  subscriptionFilter,
  onSubscriptionFilterChange,
  subscribedCount,
  subscriptionFilterDisabled = false,
  subscriptionError = null,
}: Props) {
  const { t } = useTranslation()
  const q = search.trim()
  const showClear = search.length > 0

  const searchBlock = (
    <div className="orion-search">
      <label className="orion-search-label" htmlFor="orion-entity-search">
        {t('viz.orionPanel.searchLabel')}
      </label>
      <div className="orion-search-field">
        <input
          id="orion-entity-search"
          type="text"
          className="orion-search-input"
          placeholder={t('viz.orionPanel.searchPlaceholder')}
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
            aria-label={t('viz.orionPanel.clearAria')}
            title={t('viz.orionPanel.clearTitle')}
          >
            ×
          </button>
        )}
      </div>
      {q && (
        <p className="orion-search-meta">
          {searchHits.length === 0
            ? t('viz.orionPanel.noMatches')
            : t('viz.orionPanel.matches', { count: searchHits.length })}
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
      aria-label={t('viz.orionPanel.ariaLabel')}
    >
      {compact && (
        <div className="orion-side-panel-drawer-head">
          <span className="orion-side-panel-drawer-title">{t('viz.orionPanel.drawerTitle')}</span>
          <button
            type="button"
            className="orion-side-panel-drawer-close"
            onClick={onClose}
            aria-label={t('viz.orionPanel.closeFiltersAria')}
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

      <SubscriptionFilterPanel
        mode={subscriptionFilter}
        onChange={onSubscriptionFilterChange}
        subscribedCount={subscribedCount}
        disabled={subscriptionFilterDisabled || typeFilterDisabled}
        error={subscriptionError}
      />

      {compact ? (
        <div className="orion-side-panel-drawer-body">
          {typeFilterDisabled && (
            <p className="orion-filter-hint">
              {t('viz.orionPanel.searchHint')}
            </p>
          )}
          {searchBlock}
        </div>
      ) : (
        <>
          {typeFilterDisabled && (
            <p className="orion-filter-hint">
              {t('viz.orionPanel.searchHint')}
            </p>
          )}
          {searchBlock}
        </>
      )}
    </aside>
  )
}
