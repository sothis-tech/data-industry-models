import { useCallback, useMemo, useState } from 'react'
import {
  fetchAllOrionEntities,
  fetchAllOrionEntitiesByTypes,
} from '../lib/orion-entities'
import { getTypeUri } from '../lib/model-parser'
import type { NgsiLdEntity } from '../types/entity'

export function useEntityList(
  brokerUrl: string | null,
  typeFilter: string,
  modelJson: string | null,
  knownTypes: string[],
  brokerTenant?: string,
) {
  const [allEntities, setAllEntities] = useState<NgsiLdEntity[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loadCount, setLoadCount] = useState<number | null>(null)
  const [search, setSearch] = useState('')

  const typeFilteredEntities = useMemo(() => {
    if (!typeFilter) return allEntities
    const typeUri = getTypeUri(typeFilter, modelJson)
    const short = typeFilter.toLowerCase()
    return allEntities.filter((e) => {
      const t = e.type ?? ''
      const local = (t.split('/').pop() ?? '').toLowerCase()
      return t === typeUri || local === short || t.endsWith(`/${typeFilter}`)
    })
  }, [allEntities, typeFilter, modelJson])

  const filteredEntities = useMemo(() => {
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

  const fetchEntities = useCallback(async () => {
    if (!brokerUrl) return
    setLoading(true)
    setError(null)
    setSearch('')
    setLoadCount(0)

    const onProgress = (n: number) => setLoadCount(n)

    try {
      const global = await fetchAllOrionEntities(brokerUrl, { tenant: brokerTenant, onProgress })
      if (!global.error || global.entities.length > 0) {
        setAllEntities(global.entities)
        if (global.error) setError(global.error)
      } else {
        const types = knownTypes.slice(0, 100)
        if (!types.length) {
          setError(global.error)
          return
        }
        const typeUris = types.map((t) => getTypeUri(t, modelJson))
        const byType = await fetchAllOrionEntitiesByTypes(brokerUrl, typeUris, {
          tenant: brokerTenant,
          onProgress,
        })
        if (byType.error && !byType.entities.length) {
          setError(byType.error)
          return
        }
        setAllEntities(byType.entities)
        if (byType.error) setError(byType.error)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error de red')
    } finally {
      setLoading(false)
      setLoadCount(null)
    }
  }, [brokerUrl, modelJson, knownTypes, brokerTenant])

  return {
    allEntities,
    typeFilteredEntities,
    filteredEntities,
    loading,
    loadCount,
    error,
    search,
    setSearch,
    fetchEntities,
  }
}
