import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getSubscriptions } from '../api/orion'
import {
  fetchAllOrionEntities,
  fetchAllOrionEntitiesByTypes,
} from '../lib/orion-entities'
import { getTypeUri } from '../lib/model-parser'
import {
  applySubscriptionVisibilityFilter,
  subscribedEntityIdsFromSubscriptions,
  type SubscriptionFilterMode,
} from '../lib/subscriptions'
import type { NgsiLdEntity } from '../types/entity'

export function useEntityList(
  brokerUrl: string | null,
  typeFilter: string,
  modelJson: string | null,
  knownTypes: string[],
  brokerTenant?: string,
) {
  const { t } = useTranslation()
  const [allEntities, setAllEntities] = useState<NgsiLdEntity[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loadCount, setLoadCount] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [subscriptionFilter, setSubscriptionFilter] = useState<SubscriptionFilterMode>('all')
  const [subscribedIds, setSubscribedIds] = useState<Set<string>>(() => new Set())
  const [subscriptionError, setSubscriptionError] = useState<string | null>(null)

  const typeFilteredEntities = useMemo(() => {
    if (!typeFilter) return allEntities
    const typeUri = getTypeUri(typeFilter, modelJson)
    const short = typeFilter.toLowerCase()
    return allEntities.filter((e) => {
      const ty = e.type ?? ''
      const local = (ty.split('/').pop() ?? '').toLowerCase()
      return ty === typeUri || local === short || ty.endsWith(`/${typeFilter}`)
    })
  }, [allEntities, typeFilter, modelJson])

  const searchFilteredEntities = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return typeFilteredEntities
    return typeFilteredEntities.filter((e) => {
      const rawName = e.name
      const name = String(
        rawName && typeof rawName === 'object' && 'value' in (rawName as object)
          ? (rawName as { value?: unknown }).value
          : rawName ?? '',
      ).toLowerCase()
      const id = (e.id ?? '').toLowerCase()
      const type = ((e.type ?? '').split('/').pop() ?? '').toLowerCase()
      return name.includes(q) || id.includes(q) || type.includes(q)
    })
  }, [typeFilteredEntities, search])

  const filteredEntities = useMemo(() => {
    const ids = applySubscriptionVisibilityFilter(
      searchFilteredEntities.map((e) => e.id),
      subscribedIds,
      subscriptionFilter,
    )
    return searchFilteredEntities.filter((e) => ids.has(e.id))
  }, [searchFilteredEntities, subscribedIds, subscriptionFilter])

  const fetchEntities = useCallback(async () => {
    if (!brokerUrl) return
    setLoading(true)
    setError(null)
    setSearch('')
    setSubscriptionError(null)
    setLoadCount(0)

    const onProgress = (n: number) => setLoadCount(n)

    try {
      const [entitiesResult, subRes] = await Promise.all([
        (async () => {
          const global = await fetchAllOrionEntities(brokerUrl, { tenant: brokerTenant, onProgress })
          if (!global.error || global.entities.length > 0) {
            return global
          }
          const types = knownTypes.slice(0, 100)
          if (!types.length) {
            return global
          }
          const typeUris = types.map((ty) => getTypeUri(ty, modelJson))
          return fetchAllOrionEntitiesByTypes(brokerUrl, typeUris, {
            tenant: brokerTenant,
            onProgress,
          })
        })(),
        getSubscriptions(brokerUrl, { tenant: brokerTenant }),
      ])

      if (entitiesResult.error && !entitiesResult.entities.length) {
        setError(entitiesResult.error)
        setAllEntities([])
      } else {
        setAllEntities(entitiesResult.entities)
        if (entitiesResult.error) setError(entitiesResult.error)
      }

      if (subRes.error || subRes.status >= 400) {
        setSubscribedIds(new Set())
        setSubscriptionError(t('entities.edit.subsLoadError'))
        setSubscriptionFilter('all')
      } else {
        setSubscribedIds(subscribedEntityIdsFromSubscriptions(subRes.body ?? []))
        setSubscriptionError(null)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t('errors.network'))
    } finally {
      setLoading(false)
      setLoadCount(null)
    }
  }, [brokerUrl, modelJson, knownTypes, brokerTenant, t])
  return {
    allEntities,
    typeFilteredEntities,
    filteredEntities,
    loading,
    loadCount,
    error,
    search,
    setSearch,
    subscriptionFilter,
    setSubscriptionFilter,
    subscribedIds,
    subscriptionError,
    fetchEntities,
  }
}
