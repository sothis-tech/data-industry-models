import { useEffect, useRef } from 'react'
import { useTranslation, Trans } from 'react-i18next'
import Select from 'react-select'
import {
  SUBSCRIPTION_FILTER_OPTIONS,
  type SubscriptionFilterMode,
} from '../../lib/subscriptions'
import type { NgsiLdEntity } from '../../types/entity'

type SelectOption = { value: string; label: string }

/** Estilos para react-select adaptados al tema oscuro */
function useSelectStyles() {
  return {
    control: (base: object, state: { isFocused: boolean }) => ({
      ...base,
      background: 'var(--bg)',
      borderColor: state.isFocused ? 'var(--accent)' : 'var(--border)',
      borderRadius: 'var(--radius-md)',
      boxShadow: state.isFocused ? '0 0 0 3px var(--accent-10)' : 'none',
      minHeight: '32px',
      fontSize: '0.82rem',
      cursor: 'pointer',
      '&:hover': { borderColor: 'var(--accent)' },
    }),
    valueContainer: (base: object) => ({ ...base, padding: '0 8px' }),
    singleValue: (base: object) => ({ ...base, color: 'var(--text)' }),
    placeholder: (base: object) => ({ ...base, color: 'var(--muted)', opacity: 0.7 }),
    menu: (base: object) => ({
      ...base,
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)',
      boxShadow: 'var(--shadow-md)',
      zIndex: 50,
    }),
    option: (base: object, state: { isSelected: boolean; isFocused: boolean }) => ({
      ...base,
      background: state.isSelected
        ? 'var(--accent-dim)'
        : state.isFocused
          ? 'var(--surface-2)'
          : 'transparent',
      color: state.isSelected ? 'var(--accent)' : 'var(--text)',
      fontSize: '0.82rem',
      cursor: 'pointer',
      padding: '6px 10px',
    }),
    indicatorSeparator: () => ({ display: 'none' }),
    dropdownIndicator: (base: object) => ({ ...base, color: 'var(--muted)', padding: '0 6px' }),
    clearIndicator: (base: object) => ({ ...base, color: 'var(--muted)', padding: '0 4px', cursor: 'pointer' }),
    input: (base: object) => ({ ...base, color: 'var(--text)', margin: 0, padding: 0 }),
  }
}

type Props = {
  entities: NgsiLdEntity[]
  allCount: number
  types: string[]
  typeFilter: string
  search: string
  subscriptionFilter: SubscriptionFilterMode
  subscribedIds?: Set<string>
  subscriptionError?: string | null
  loading: boolean
  loadCount?: number | null
  error?: string | null
  selectedId: string | null
  onTypeFilterChange: (type: string) => void
  onSearchChange: (q: string) => void
  onSubscriptionFilterChange: (mode: SubscriptionFilterMode) => void
  onSelect: (entity: NgsiLdEntity) => void
  onNewEntity: () => void
}

function entityLabel(e: NgsiLdEntity): string {
  const n = e.name
  if (n && typeof n === 'object' && 'value' in (n as object)) return String((n as { value?: unknown }).value ?? e.id)
  if (typeof n === 'string' && n) return n
  return e.id
}

export function EntityList({
  entities,
  allCount,
  types,
  typeFilter,
  search,
  subscriptionFilter,
  subscribedIds,
  subscriptionError = null,
  loading,
  loadCount = null,
  error = null,
  selectedId,
  onTypeFilterChange,
  onSearchChange,
  onSubscriptionFilterChange,
  onSelect,
  onNewEntity,
}: Props) {
  const { t } = useTranslation()
  const searchRef = useRef<HTMLInputElement>(null)
  const selectStyles = useSelectStyles()

  useEffect(() => {
    const el = searchRef.current
    if (!el) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onSearchChange(''); el.value = '' }
    }
    el.addEventListener('keydown', handler)
    return () => el.removeEventListener('keydown', handler)
  }, [onSearchChange])

  const typeOptions: SelectOption[] = types.map(t => ({ value: t, label: t }))
  const selectedOption = typeFilter ? typeOptions.find(o => o.value === typeFilter) ?? null : null
  const subOptions = SUBSCRIPTION_FILTER_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))
  const selectedSubOption =
    subOptions.find((o) => o.value === subscriptionFilter) ?? subOptions[0]

  const showEmpty = !loading && entities.length === 0
  const showFooter = !loading && allCount > 0
  const subFilterDisabled = !!subscriptionError

  return (
    <div className="entity-list-panel">
      <div className="entity-list-toolbar">
        <Select<SelectOption>
          options={typeOptions}
          value={selectedOption}
          onChange={opt => onTypeFilterChange(opt?.value ?? '')}
          placeholder={t('entities.list.allTypes')}
          isClearable
          isSearchable
          styles={selectStyles as never}
          noOptionsMessage={() => t('entities.list.noTypes')}
        />
        <Select<{ value: SubscriptionFilterMode; label: string }>
          options={subOptions}
          value={selectedSubOption}
          onChange={(opt) => onSubscriptionFilterChange(opt?.value ?? 'all')}
          isDisabled={subFilterDisabled}
          isSearchable={false}
          styles={selectStyles as never}
          aria-label={t('entities.list.subscriptionFilterAria')}
        />
        {subscriptionError && (
          <p className="entity-list-sub-hint" role="status">{subscriptionError}</p>
        )}
        <input
          ref={searchRef}
          type="search"
          placeholder={t('entities.list.searchPlaceholder')}
          aria-label={t('entities.list.searchAria')}
          autoComplete="off"
          value={search}
          onChange={e => onSearchChange(e.target.value)}
        />
      </div>

      <button type="button" className="btn-new-entity" onClick={onNewEntity}>
        {t('entities.list.newEntity')}
      </button>

      <div className="entity-list-scroll">
        {error && !loading && (
          <div className="entity-list-error" role="alert">
            ⚠ {error}
          </div>
        )}
        {loading && (
          <div className="entity-list-empty">
            {loadCount != null && loadCount > 0 ? t('entities.list.loadingCount', { count: loadCount }) : t('common.loading')}
          </div>
        )}
        {showEmpty && (
          <div className="entity-list-empty">
            {search
              ? t('entities.list.noSearchResults', { search })
              : allCount > 0
                ? t('entities.list.noFilterResults')
                : t('entities.list.noEntities')}
          </div>
        )}
        {!loading && entities.map(entity => {
          const name = entityLabel(entity)
          const short = entity.id.split(':').pop() ?? entity.id
          const type = (entity.type ?? '').split('/').pop() ?? entity.type
          const hasQlSub = subscribedIds?.has(entity.id) ?? false
          return (
            <div
              key={entity.id}
              className={`entity-item${selectedId === entity.id ? ' active' : ''}`}
              onClick={() => onSelect(entity)}
            >
              <div className="entity-item-name">{name}</div>
              <div className="entity-item-id">{short}</div>
              <div className="entity-item-badges">
                <span className="type-badge">{type}</span>
                {hasQlSub && (
                  <span className="sub-badge" title={t('entities.list.qlBadgeTitle')}>QL</span>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {showFooter && (
        <div className="entity-list-footer">
          <span className="entity-list-count">
            {search
              ? <Trans i18nKey="entities.list.countFiltered" values={{ shown: entities.length, total: allCount }} components={{ strong: <strong /> }} />
              : <Trans i18nKey="entities.list.countTotal" values={{ count: allCount }} count={allCount} components={{ strong: <strong /> }} />
            }
          </span>
        </div>
      )}
    </div>
  )
}
