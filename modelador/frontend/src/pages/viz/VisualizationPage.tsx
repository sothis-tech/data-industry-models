import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation, Trans } from 'react-i18next'
import { useVizCanvasCompact } from '../../hooks/useVizCanvasCompact'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { buildOrionGraph, buildSchemaGraph, buildSchemaTypeView, getEntityView } from '../../api/graph'
import { deleteEntity, getEntityById } from '../../api/orion'
import {
  AGENT_OPEN_VIZ_ENTITY,
  type AgentOpenVizEntityDetail,
} from '../../lib/agentEvents'
import {
  createTypeColorScale,
  computeOrionVisibleNodeIds,
  loadGraphLabelPlacement,
  loadSavedTypeFilter,
  mergeOrionActiveKeysForFocus,
  orionEntitySearchLabel,
  orionNodeMatchesSearch,
  resolveTypeColor,
  saveGraphLabelPlacement,
  saveTypeFilter,
  typeKeyFromFullType,
  type GraphLabelPlacement,
} from '../../lib/graph-utils'
import { fetchAllOrionEntities, uniqueEntitiesById } from '../../lib/orion-entities'
import { parseModel } from '../../lib/model-parser'
import { getCurrentBroker } from '../../lib/storage'
import { consumeVizFocusEntityId } from '../../lib/vizNavigation'
import type { NgsiLdEntity } from '../../types/entity'
import type { EntityView, OrionGraphLink, OrionGraphNode, SchemaGraphData, SchemaTypeView } from '../../types/graph'
import { ConfirmModal } from '../../components/ConfirmModal'
import type { GraphHandle } from './SchemaGraph'
import { SchemaGraph } from './SchemaGraph'
import { OrionGraph } from './OrionGraph'
import { NodeDetailPanel } from './NodeDetailPanel'
import { SchemaInfoPanel } from './SchemaInfoPanel'
import { OrionSidePanel } from './OrionSidePanel'

type ActiveTab = 'schema' | 'orion'

type SchemaDetail =
  | { state: 'loading'; typeId: string }
  | { state: 'ready'; typeId: string; view: SchemaTypeView }
  | { state: 'error'; typeId: string; error: string }
  | null

type OrionDetail =
  | { state: 'loading'; node: OrionGraphNode }
  | { state: 'ready'; node: OrionGraphNode; view: EntityView }
  | { state: 'error'; node: OrionGraphNode; error: string }
  | null

type OutletCtx = { refreshKey: number }

export function VisualizationPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { refreshKey } = useOutletContext<OutletCtx>()

  // Mark onboarding step 3 done
  useEffect(() => {
    localStorage.setItem('ngsi_onboarding_step3_done', '1')
  }, [])

  // Model data — re-leído cuando el layout notifica un cambio de modelo (refreshKey)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const { types, relationships } = useMemo(() => parseModel(localStorage.getItem('ngsi_model')), [refreshKey])

  // Color scale shared between both graphs
  const colorScale = useMemo(() => createTypeColorScale(types), [types])

  // ── Tabs ──────────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<ActiveTab>('schema')

  // ── Schema graph state ────────────────────────────────────────────────────
  const [schemaGraphData, setSchemaGraphData] = useState<SchemaGraphData | null>(null)
  const [schemaGraphError, setSchemaGraphError] = useState<string | null>(null)
  const [schemaDetail, setSchemaDetail] = useState<SchemaDetail>(null)
  const [infoPanelOpen, setInfoPanelOpen] = useState(false)
  const [infoPanelHeight, setInfoPanelHeight] = useState(220)
  const schemaGraphRef = useRef<GraphHandle>(null)
  const [graphLabelPlacement, setGraphLabelPlacement] = useState<GraphLabelPlacement>(() => loadGraphLabelPlacement())

  const toggleGraphLabelPlacement = useCallback(() => {
    setGraphLabelPlacement((current) => {
      const next = current === 'below' ? 'inside' : 'below'
      saveGraphLabelPlacement(next)
      return next
    })
  }, [])

  // ── Orion graph state ─────────────────────────────────────────────────────
  const [orionLoaded, setOrionLoaded] = useState(false)
  const [orionLoading, setOrionLoading] = useState(false)
  const [orionError, setOrionError] = useState<string | null>(null)
  const [orionNodes, setOrionNodes] = useState<OrionGraphNode[]>([])
  const [orionLinks, setOrionLinks] = useState<OrionGraphLink[]>([])
  const [orionAllTypeKeys, setOrionAllTypeKeys] = useState<string[]>([])
  const [orionActiveTypeKeys, setOrionActiveTypeKeys] = useState<string[]>([])
  const [orionEntityCount, setOrionEntityCount] = useState(0)
  const [orionLinkCount, setOrionLinkCount] = useState(0)
  const [orionLoadCount, setOrionLoadCount] = useState<number | null>(null)
  const orionRawEntitiesRef = useRef<NgsiLdEntity[]>([])
  /** Texto del buscador: filtra el grafo; al seleccionar entidad se rellena para poder limpiar con ×. */
  const [orionSearchDraft, setOrionSearchDraft] = useState('')
  const [orionFocusedNodeId, setOrionFocusedNodeId] = useState<string | null>(null)
  const [orionDetail, setOrionDetail] = useState<OrionDetail>(null)
  const [deleteModal, setDeleteModal] = useState<{ open: boolean; entityId: string; loading: boolean }>({
    open: false,
    entityId: '',
    loading: false,
  })
  const orionGraphRef = useRef<GraphHandle>(null)
  const schemaCanvasRef = useRef<HTMLDivElement>(null)
  const orionCanvasRef = useRef<HTMLDivElement>(null)
  const { isCompact: schemaCanvasCompact } = useVizCanvasCompact(schemaCanvasRef)
  const { isCompact: orionCanvasCompact } = useVizCanvasCompact(orionCanvasRef)
  const [orionFiltersOpen, setOrionFiltersOpen] = useState(false)
  /** URN pendiente hasta que el grafo Orion esté listo (misma ruta que elegir en el buscador). */
  const pendingOrionSelectRef = useRef<string | null>(null)

  useEffect(() => {
    if (!orionCanvasCompact) setOrionFiltersOpen(false)
  }, [orionCanvasCompact])

  const orionSearchQuery = orionSearchDraft.trim()
  /** Texto en el buscador sin entidad seleccionada: filtra el grafo por coincidencias. */
  const orionSearchFiltering = orionSearchQuery.length > 0 && orionFocusedNodeId === null

  const clearOrionSearch = useCallback(() => {
    setOrionSearchDraft('')
  }, [])

  const orionVisibleIds = useMemo(
    () =>
      computeOrionVisibleNodeIds(
        orionNodes,
        orionLinks,
        orionActiveTypeKeys,
        orionAllTypeKeys,
        orionSearchFiltering ? orionSearchDraft : '',
      ),
    [
      orionNodes,
      orionLinks,
      orionActiveTypeKeys,
      orionAllTypeKeys,
      orionSearchFiltering,
      orionSearchDraft,
    ],
  )

  const orionSearchHits = useMemo(() => {
    if (!orionSearchQuery || !orionNodes.length) return []
    return orionNodes.filter((n) => orionNodeMatchesSearch(n, orionSearchQuery)).slice(0, 12)
  }, [orionNodes, orionSearchQuery])

  function handleOrionSearchChange(value: string) {
    const clearing = orionSearchDraft.trim().length > 0 && value.trim().length === 0
    const focusedNode = orionFocusedNodeId
      ? orionNodes.find((n) => n.id === orionFocusedNodeId)
      : null
    const leavingFocus =
      !clearing &&
      focusedNode != null &&
      value.trim() !== orionEntitySearchLabel(focusedNode)

    if (clearing) {
      setOrionSearchDraft('')
      return
    }

    setOrionSearchDraft(value)
    if (leavingFocus) {
      setOrionFocusedNodeId(null)
      setOrionDetail(null)
      orionGraphRef.current?.clearHighlight()
    }
  }

  // ── Build schema graph on mount ───────────────────────────────────────────
  useEffect(() => {
    if (!types.length) return
    buildSchemaGraph(types, relationships).then((data) => {
      if (data.error) {
        setSchemaGraphError(data.error)
      } else {
        setSchemaGraphData(data)
      }
    })
  }, [types, relationships])

  const applyOrionGraphFromEntities = useCallback(
    async (
      entities: NgsiLdEntity[],
      options?: { preserveFocus?: boolean },
    ): Promise<{ ok: boolean; nodes: OrionGraphNode[]; focusedId: string | null }> => {
      if (!entities.length) {
        setOrionNodes([])
        setOrionLinks([])
        setOrionEntityCount(0)
        setOrionLinkCount(0)
        setOrionAllTypeKeys([])
        setOrionActiveTypeKeys([])
        if (!options?.preserveFocus) {
          setOrionFocusedNodeId(null)
          setOrionSearchDraft('')
        }
        return { ok: true, nodes: [], focusedId: null }
      }

      const graphData = await buildOrionGraph(entities, relationships)
      if (graphData.error) {
        setOrionError(graphData.error)
        return { ok: false, nodes: [], focusedId: null }
      }

      const newNodes = (graphData.nodes as OrionGraphNode[]) ?? []
      const newLinks = (graphData.links as OrionGraphLink[]) ?? []
      const typeKeys = [...new Set(newNodes.map((n) => typeKeyFromFullType(n.type || '')).filter(Boolean))]
      let activeKeys = loadSavedTypeFilter(typeKeys)

      const preserveFocus = options?.preserveFocus === true
      const pendingId = pendingOrionSelectRef.current
      let focusId: string | null = preserveFocus ? orionFocusedNodeId : null
      let searchDraftOnLoad = preserveFocus ? orionSearchDraft : ''

      if (pendingId) {
        const pendingNode = newNodes.find((n) => n.id === pendingId)
        if (pendingNode) {
          focusId = pendingNode.id
          searchDraftOnLoad = orionEntitySearchLabel(pendingNode)
          activeKeys = mergeOrionActiveKeysForFocus(pendingId, newNodes, newLinks, activeKeys, typeKeys)
          saveTypeFilter(activeKeys)
          pendingOrionSelectRef.current = null
        }
      } else if (preserveFocus && focusId) {
        const focusedNode = newNodes.find((n) => n.id === focusId)
        if (focusedNode) {
          activeKeys = mergeOrionActiveKeysForFocus(focusId, newNodes, newLinks, activeKeys, typeKeys)
          saveTypeFilter(activeKeys)
        } else {
          focusId = null
          searchDraftOnLoad = ''
        }
      }

      setOrionNodes(newNodes)
      setOrionLinks(newLinks)
      setOrionAllTypeKeys(typeKeys)
      setOrionActiveTypeKeys(activeKeys)
      setOrionEntityCount(entities.length)
      setOrionLinkCount(newLinks.length)
      setOrionFocusedNodeId(focusId)
      if (!preserveFocus || pendingId || searchDraftOnLoad) {
        setOrionSearchDraft(searchDraftOnLoad)
      }
      return { ok: true, nodes: newNodes, focusedId: focusId }
    },
    [relationships, orionFocusedNodeId, orionSearchDraft],
  )

  const ensurePendingEntityInBatch = useCallback(
    async (entities: NgsiLdEntity[], brokerUrl: string, tenant?: string) => {
      const pendingId = pendingOrionSelectRef.current
      if (!pendingId || entities.some((e) => e.id === pendingId)) return entities
      const { body, error } = await getEntityById(brokerUrl, pendingId, tenant)
      if (!error && body?.id) {
        return uniqueEntitiesById([body as NgsiLdEntity, ...entities])
      }
      return entities
    },
    [],
  )

  // ── Load Orion graph (todas las instancias del broker) ────────────────────
  const loadOrionGraph = useCallback(async () => {
    const broker = getCurrentBroker()
    if (!broker) {
      setOrionError('no-broker')
      return
    }
    setOrionLoading(true)
    setOrionError(null)
    setOrionFocusedNodeId(null)
    setOrionLoadCount(0)
    orionRawEntitiesRef.current = []

    const { entities: fetched, error: fetchError } = await fetchAllOrionEntities(broker.url, {
      tenant: broker.tenant,
      onProgress: setOrionLoadCount,
    })

    let entities = await ensurePendingEntityInBatch(fetched, broker.url, broker.tenant)
    orionRawEntitiesRef.current = entities

    if (fetchError && !entities.length) {
      setOrionLoading(false)
      setOrionLoadCount(null)
      setOrionError(fetchError)
      return
    }

    if (!entities.length) {
      setOrionLoading(false)
      setOrionLoadCount(null)
      setOrionLoaded(true)
      await applyOrionGraphFromEntities([])
      return
    }

    const { ok } = await applyOrionGraphFromEntities(entities)
    setOrionLoading(false)
    setOrionLoadCount(null)
    if (fetchError) setOrionError(fetchError)
    if (ok) setOrionLoaded(true)
  }, [applyOrionGraphFromEntities, ensurePendingEntityInBatch])

  // Load Orion when switching to its tab for the first time
  function handleTabChange(tab: ActiveTab) {
    setActiveTab(tab)
    if (tab === 'orion' && !orionLoaded && !orionLoading) {
      void loadOrionGraph()
    }
  }

  function handleOrionTypeFilterChange(newKeys: string[]) {
    setOrionActiveTypeKeys(newKeys)
    saveTypeFilter(newKeys)
  }

  // ── Schema node click ─────────────────────────────────────────────────────
  const handleSchemaNodeClick = useCallback(
    async (typeId: string | null) => {
      if (!typeId) {
        setSchemaDetail(null)
        return
      }
      setSchemaDetail({ state: 'loading', typeId })
      const result = await buildSchemaTypeView(typeId, relationships)
      if (result.error || !result.view) {
        setSchemaDetail({ state: 'error', typeId, error: result.error ?? t('viz.page.errLoadDetail') })
      } else {
        setSchemaDetail({ state: 'ready', typeId, view: result.view })
      }
    },
    [relationships, t],
  )

  const loadOrionEntityDetail = useCallback(async (node: OrionGraphNode) => {
    setOrionDetail({ state: 'loading', node })
    const broker = getCurrentBroker()
    if (!broker) {
      setOrionDetail({ state: 'error', node, error: t('viz.page.errNoBrokerConfigured') })
      return
    }
    const result = await getEntityView(broker.url, node.id, broker.tenant)
    if (result.error || !result.view) {
      setOrionDetail({ state: 'error', node, error: result.error ?? t('viz.page.errLoadEntity') })
    } else {
      setOrionDetail({ state: 'ready', node, view: result.view })
    }
  }, [t])

  /** Selección de instancia: buscador, clic en nodo o llegada desde Entidades / Marvin. */
  const selectOrionEntity = useCallback(
    (node: OrionGraphNode) => {
      setActiveTab('orion')
      pendingOrionSelectRef.current = null

      setOrionActiveTypeKeys((keys) => {
        const merged = mergeOrionActiveKeysForFocus(
          node.id,
          orionNodes,
          orionLinks,
          keys,
          orionAllTypeKeys,
        )
        if (merged.length === keys.length && merged.every((k) => keys.includes(k))) return keys
        saveTypeFilter(merged)
        return merged
      })

      setOrionSearchDraft(orionEntitySearchLabel(node))
      setOrionFocusedNodeId(node.id)

      queueMicrotask(() => {
        orionGraphRef.current?.highlightNode(node.id)
      })
    },
    [orionNodes, orionLinks, orionAllTypeKeys],
  )

  const fulfillPendingOrionSelection = useCallback(async () => {
    const entityId = pendingOrionSelectRef.current
    if (!entityId || !orionLoaded || orionLoading) return

    const existing = orionNodes.find((n) => n.id === entityId)
    if (existing) {
      selectOrionEntity(existing)
      return
    }

    const broker = getCurrentBroker()
    if (!broker) return
    const merged = await ensurePendingEntityInBatch(
      orionRawEntitiesRef.current,
      broker.url,
      broker.tenant,
    )
    if (!merged.some((e) => e.id === entityId)) return

    orionRawEntitiesRef.current = merged
    const { ok, nodes } = await applyOrionGraphFromEntities(merged)
    if (!ok) return

    const graphNode = nodes.find((n) => n.id === entityId)
    if (graphNode) selectOrionEntity(graphNode)
  }, [
    orionLoaded,
    orionLoading,
    orionNodes,
    selectOrionEntity,
    ensurePendingEntityInBatch,
    applyOrionGraphFromEntities,
  ])

  const queueOrionEntityById = useCallback(
    (entityId: string) => {
      const id = entityId.trim()
      if (!id) return
      pendingOrionSelectRef.current = id
      setActiveTab('orion')

      const knownNode = orionNodes.find((n) => n.id === id)
      if (knownNode) {
        setOrionSearchDraft(orionEntitySearchLabel(knownNode))
      }

      if (!orionLoaded && !orionLoading) {
        void loadOrionGraph()
        return
      }
      if (orionLoading) return
      void fulfillPendingOrionSelection()
    },
    [orionLoaded, orionLoading, orionNodes, loadOrionGraph, fulfillPendingOrionSelection],
  )

  // ── Orion node click ──────────────────────────────────────────────────────
  const handleOrionNodeClick = useCallback(
    (node: OrionGraphNode | null) => {
      if (!node) {
        setOrionDetail(null)
        setOrionFocusedNodeId(null)
        setOrionSearchDraft('')
        orionGraphRef.current?.clearHighlight()
        return
      }
      selectOrionEntity(node)
      setOrionFiltersOpen(false)
    },
    [selectOrionEntity],
  )

  const handleOrionSearchSelect = useCallback(
    (node: OrionGraphNode) => {
      if (!orionLoaded || orionLoading) return
      selectOrionEntity(node)
      setOrionFiltersOpen(false)
    },
    [orionLoaded, orionLoading, selectOrionEntity],
  )

  const closeOrionFilters = useCallback(() => setOrionFiltersOpen(false), [])

  useEffect(() => {
    if (!orionFocusedNodeId || !orionLoaded || orionLoading) return
    const node = orionNodes.find((n) => n.id === orionFocusedNodeId)
    if (!node) return
    if (orionDetail?.state === 'loading' && orionDetail.node.id === node.id) return
    if (orionDetail?.state === 'ready' && orionDetail.node.id === node.id) return
    void loadOrionEntityDetail(node)
  }, [orionFocusedNodeId, orionLoaded, orionLoading, orionNodes, orionDetail, loadOrionEntityDetail])

  useEffect(() => {
    if (!orionLoaded || orionLoading) return
    void fulfillPendingOrionSelection()
  }, [orionLoaded, orionLoading, orionNodes, fulfillPendingOrionSelection])

  useEffect(() => {
    const fromStorage = consumeVizFocusEntityId()
    if (fromStorage) queueOrionEntityById(fromStorage)
  }, [queueOrionEntityById])

  useEffect(() => {
    function onAgentOpenViz(event: Event) {
      const { entityId } = (event as CustomEvent<AgentOpenVizEntityDetail>).detail
      if (entityId) queueOrionEntityById(entityId)
    }
    window.addEventListener(AGENT_OPEN_VIZ_ENTITY, onAgentOpenViz)
    return () => window.removeEventListener(AGENT_OPEN_VIZ_ENTITY, onAgentOpenViz)
  }, [queueOrionEntityById])

  // ── Delete flow ───────────────────────────────────────────────────────────
  function openDeleteModal(entityId: string) {
    setDeleteModal({ open: true, entityId, loading: false })
  }

  async function handleDeleteConfirm() {
    const broker = getCurrentBroker()
    if (!broker) return
    setDeleteModal((s) => ({ ...s, loading: true }))
    const { error, status } = await deleteEntity(broker.url, deleteModal.entityId, broker.tenant)
    setDeleteModal({ open: false, entityId: '', loading: false })
    if (!error && status >= 200 && status < 300) {
      setOrionDetail(null)
      setOrionLoaded(false)
      void loadOrionGraph()
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  function schemaDetailTitle() {
    if (!schemaDetail) return null
    const c = colorScale(schemaDetail.typeId)
    return (
      <span style={{ background: c, color: 'var(--badge-fg)', padding: '0.15rem 0.55rem', borderRadius: 5 }}>
        {schemaDetail.typeId}
      </span>
    )
  }

  function schemaDetailBody() {
    if (!schemaDetail) return null
    if (schemaDetail.state === 'loading')
      return (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '1rem 0', color: 'var(--muted)' }}>
          <div className="viz-spinner" />
        </div>
      )
    if (schemaDetail.state === 'error')
      return <p style={{ color: 'var(--error)', fontSize: '0.82rem' }}>{schemaDetail.error}</p>

    const { from_rels, to_rels } = schemaDetail.view
    if (!from_rels.length && !to_rels.length)
      return <p style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>{t('viz.page.noRelationsForType')}</p>

    return (
      <>
        {from_rels.length > 0 && (
          <div className="viz-detail-section">
            <div className="viz-detail-section-title">{t('viz.page.pointsTo')}</div>
            {from_rels.map((r, i) => {
              const ct = colorScale(r.to ?? '')
              const ps = r.property_short || r.property
              const pns = r.property_ns
              return (
                <div key={i} className="viz-attr-row" style={r.implicit ? { opacity: 0.7 } : undefined}>
                  <span className="viz-attr-key" title={r.property}>
                    {ps}
                    {r.implicit && <span title={t('viz.page.derivedFromExamples')} style={{ color: 'var(--muted)', fontSize: '0.68rem', marginLeft: '0.2rem' }}>{t('viz.page.exampleTag')}</span>}
                  </span>
                  <span style={{ flex: 1, display: 'flex', alignItems: 'baseline', gap: '0.3rem', flexWrap: 'wrap' }}>
                    {pns && (
                      <span className="viz-ns-badge" style={{ color: pns.color, borderColor: pns.color }} title={r.property}>
                        {pns.label}
                      </span>
                    )}
                    <span className="viz-attr-val">
                      <span style={{ background: ct, color: 'var(--badge-fg)', borderRadius: 3, padding: '0.05rem 0.35rem', fontSize: '0.7rem' }}>
                        {r.to}
                      </span>
                    </span>
                  </span>
                </div>
              )
            })}
          </div>
        )}
        {to_rels.length > 0 && (
          <div className="viz-detail-section">
            <div className="viz-detail-section-title">{t('viz.page.referencedBy')}</div>
            {to_rels.map((r, i) => {
              const cf = colorScale(r.from ?? '')
              const ps = r.property_short || r.property
              const pns = r.property_ns
              return (
                <div key={i} className="viz-attr-row" style={r.implicit ? { opacity: 0.7 } : undefined}>
                  <span className="viz-attr-key" title={r.property}>
                    {ps}
                    {r.implicit && <span title={t('viz.page.derivedFromExamples')} style={{ color: 'var(--muted)', fontSize: '0.68rem', marginLeft: '0.2rem' }}>{t('viz.page.exampleTag')}</span>}
                  </span>
                  <span style={{ flex: 1, display: 'flex', alignItems: 'baseline', gap: '0.3rem', flexWrap: 'wrap' }}>
                    {pns && (
                      <span className="viz-ns-badge" style={{ color: pns.color, borderColor: pns.color }} title={r.property}>
                        {pns.label}
                      </span>
                    )}
                    <span className="viz-attr-val">
                      <span style={{ background: cf, color: 'var(--badge-fg)', borderRadius: 3, padding: '0.05rem 0.35rem', fontSize: '0.7rem' }}>
                        {r.from}
                      </span>
                    </span>
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </>
    )
  }

  function orionDetailTitle() {
    if (!orionDetail) return null
    const c = resolveTypeColor(orionDetail.node.type || '', colorScale)
    return (
      <span style={{ background: c, color: 'var(--badge-fg)', padding: '0.15rem 0.55rem', borderRadius: 5 }}>
        {orionDetail.node.label || (orionDetail.node.type || '').split('/').pop() || '–'}
      </span>
    )
  }

  function orionDetailBody() {
    if (!orionDetail) return null
    if (orionDetail.state === 'loading')
      return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem', gap: '0.5rem', color: 'var(--muted)' }}>
          <div className="viz-spinner" />
          {t('viz.page.loadingAttrs')}
        </div>
      )
    if (orionDetail.state === 'error')
      return (
        <>
          <div className="viz-detail-id">{orionDetail.node.id}</div>
          <p style={{ color: 'var(--error)', fontSize: '0.82rem' }}>{orionDetail.error}</p>
        </>
      )

    const { view } = orionDetail
    return (
      <>
        <div className="viz-detail-id">{view.id}</div>
        {view.attrs.length > 0 ? (
          <div className="viz-detail-section">
            <div className="viz-detail-section-title">{t('viz.page.attributes')}</div>
            {view.attrs.map((attr, i) => (
              <div key={i} className="viz-attr-row">
                <span className="viz-attr-key" title={attr.key}>{attr.short || attr.key}</span>
                <span style={{ flex: 1, display: 'flex', alignItems: 'baseline', gap: '0.3rem', minWidth: 0, flexWrap: 'wrap' }}>
                  {attr.ns && (
                    <span className="viz-ns-badge" style={{ color: attr.ns.color, borderColor: attr.ns.color }} title={attr.key}>
                      {attr.ns.label}
                    </span>
                  )}
                  {attr.typeTag && <span className="viz-attr-type">{attr.typeTag}</span>}
                  <span className="viz-attr-val" title={attr.value || '–'}>{attr.display || '–'}</span>
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>{t('viz.page.noExtraAttrs')}</p>
        )}
      </>
    )
  }

  // ── Orion "empty" message ─────────────────────────────────────────────────
  function renderOrionEmpty() {
    if (orionError === 'no-broker')
      return (
        <div className="viz-empty-state">
          <Trans i18nKey="viz.page.emptyNoBroker" components={{ cfg: <button className="link-btn" onClick={() => navigate('/')} /> }} />
        </div>
      )
    if (orionError)
      return (
        <div className="viz-empty-state">
          <Trans i18nKey="viz.page.emptyBrokerError" values={{ error: orionError }} components={{ em: <em />, cfg: <button className="link-btn" onClick={() => navigate('/')} /> }} />
        </div>
      )
    if (orionLoaded && orionNodes.length === 0)
      return <div className="viz-empty-state">{t('viz.page.emptyNoEntities')}</div>
    if (orionLoaded && orionVisibleIds.size === 0)
      return (
        <div className="viz-empty-state">
          {orionSearchFiltering
            ? t('viz.page.emptyNoSearchMatch')
            : orionFocusedNodeId
              ? t('viz.page.emptySelectedNoNeighbors')
              : t('viz.page.emptyNoTypeNodes')}
        </div>
      )
    return null
  }

  const schemaOpen = schemaDetail !== null
  const orionOpen = orionDetail !== null
  const orionDetailEntityId = orionDetail?.state === 'ready' ? orionDetail.view.id : orionDetail?.node.id ?? ''
  const orionTypeShort = orionDetail ? typeKeyFromFullType(orionDetail.node.type || '') : ''

  const labelToggleTitle = graphLabelPlacement === 'below' ? t('viz.page.labelsInside') : t('viz.page.labelsBelow')

  return (
    <div className="viz-page">
      {/* Tab bar */}
      <div className="viz-tabs" role="tablist">
        <button
          className={`viz-tab${activeTab === 'schema' ? ' active' : ''}`}
          role="tab"
          aria-selected={activeTab === 'schema'}
          onClick={() => handleTabChange('schema')}
        >
          {t('viz.page.tabSchema')}
          {types.length > 0 && (
            <span className="tab-count">{types.length}</span>
          )}
        </button>
        <button
          className={`viz-tab${activeTab === 'orion' ? ' active' : ''}`}
          role="tab"
          aria-selected={activeTab === 'orion'}
          onClick={() => handleTabChange('orion')}
        >
          {t('viz.page.tabOrion')}
          {orionEntityCount > 0 && (
            <span className="tab-count">{orionEntityCount}</span>
          )}
        </button>
      </div>

      {/* ── Tab: Modelo abstracto ── */}
      <div className="viz-panel" role="tabpanel" style={{ display: activeTab === 'schema' ? 'flex' : 'none' }}>
        <div
          ref={schemaCanvasRef}
          className={`viz-canvas-full${schemaCanvasCompact ? ' viz-canvas-full--compact' : ''}`}
        >
          {!types.length && (
            <div className="viz-empty-state">
              <Trans i18nKey="viz.page.emptyLoadModel" components={{ cfg: <button className="link-btn" onClick={() => navigate('/')} /> }} />
              <span style={{ fontSize: '0.78rem', color: 'var(--muted)', marginTop: '0.4rem', display: 'block' }}>
                <Trans i18nKey="viz.page.emptyLoadModelHint" components={{ strong: <strong />, code: <code /> }} />
              </span>
            </div>
          )}
          {schemaGraphError && (
            <div className="viz-empty-state" style={{ color: 'var(--error)' }}>
              <Trans i18nKey="viz.page.schemaGraphError" values={{ error: schemaGraphError }} components={{ em: <em /> }} />
            </div>
          )}
          {schemaGraphData && !schemaGraphError && (
            <SchemaGraph
              ref={schemaGraphRef}
              nodes={schemaGraphData.nodes}
              links={schemaGraphData.links}
              colorScale={colorScale}
              labelPlacement={graphLabelPlacement}
              onNodeClick={handleSchemaNodeClick}
            />
          )}

          {/* Zoom controls */}
          {schemaGraphData && (
            <div className="viz-controls">
              <button className="viz-ctrl-btn" onClick={() => schemaGraphRef.current?.zoomIn()} title={t('viz.page.zoomIn')} aria-label={t('viz.page.zoomInAria')}>+</button>
              <button className="viz-ctrl-btn" onClick={() => schemaGraphRef.current?.zoomOut()} title={t('viz.page.zoomOut')} aria-label={t('viz.page.zoomOutAria')}>−</button>
              <button className="viz-ctrl-btn" onClick={() => schemaGraphRef.current?.fit()} title={t('viz.page.fit')} aria-label={t('viz.page.fitAria')} style={{ fontSize: '0.8rem' }}>⤢</button>
              <div className="viz-ctrl-sep" />
              <button
                className={`viz-ctrl-btn${graphLabelPlacement === 'inside' ? ' active' : ''}`}
                onClick={toggleGraphLabelPlacement}
                title={labelToggleTitle}
                aria-label={labelToggleTitle}
                aria-pressed={graphLabelPlacement === 'inside'}
                style={{ fontSize: '0.72rem' }}
              >
                Aa
              </button>
              <div className="viz-ctrl-sep" />
              <button
                className={`viz-ctrl-btn${infoPanelOpen ? ' active' : ''}`}
                onClick={() => setInfoPanelOpen((v) => !v)}
                title={t('viz.page.typesAndRelations')}
                aria-label={t('viz.page.typesAndRelations')}
                aria-expanded={infoPanelOpen}
                aria-controls="schema-info-panel"
              >
                ☰
              </button>
            </div>
          )}

          <div className="viz-hint">{t('viz.page.hint')}</div>

          {/* Schema detail panel */}
          <NodeDetailPanel
            open={schemaOpen}
            title={schemaDetailTitle()}
            onClose={() => setSchemaDetail(null)}
            footer={
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault()
                  if (schemaDetail) {
                    sessionStorage.setItem('viz_filter_type', schemaDetail.typeId)
                    navigate('/entidades')
                  }
                }}
              >
                {t('viz.page.viewEntitiesOfType')}
              </a>
            }
          >
            {schemaDetailBody()}
          </NodeDetailPanel>
        </div>

        {/* Collapsible info panel */}
        <SchemaInfoPanel
          open={infoPanelOpen}
          height={infoPanelHeight}
          types={types}
          relationships={relationships}
          colorScale={colorScale}
          onHeightChange={setInfoPanelHeight}
        />
      </div>

      {/* ── Tab: Instancias Orion-LD ── */}
      <div className="viz-panel" role="tabpanel" style={{ display: activeTab === 'orion' ? 'flex' : 'none' }}>
        <div
          ref={orionCanvasRef}
          className={[
            'viz-canvas-full',
            orionCanvasCompact ? 'viz-canvas-full--compact' : '',
            orionFiltersOpen ? 'viz-canvas-full--filters-open' : '',
          ]
            .filter(Boolean)
            .join(' ')}
        >
          {orionCanvasCompact && orionFiltersOpen && (
            <button
              type="button"
              className="viz-drawer-backdrop"
              aria-label={t('viz.orionPanel.closeFiltersAria')}
              onClick={closeOrionFilters}
            />
          )}
          {/* Loading overlay */}
          <div className={`viz-loading${orionLoading ? ' active' : ''}`}>
            <div className="viz-spinner" />
            <span>
              {orionLoadCount != null && orionLoadCount > 0
                ? t('viz.page.loadingEntitiesCount', { count: orionLoadCount })
                : t('viz.page.loadingEntities')}
            </span>
          </div>

          {renderOrionEmpty()}

          {orionLoaded && orionNodes.length > 0 && !orionLoading && (
            <OrionGraph
              ref={orionGraphRef}
              nodes={orionNodes}
              links={orionLinks}
              visibleNodeIds={orionVisibleIds}
              colorScale={colorScale}
              labelPlacement={graphLabelPlacement}
              focusedNodeId={orionFocusedNodeId}
              searchActive={orionSearchFiltering}
              onNodeClick={handleOrionNodeClick}
            />
          )}

          {/* Zoom + refresh controls */}
          <div className="viz-controls">
            <button
              className="viz-ctrl-btn"
              onClick={() => { setOrionLoaded(false); void loadOrionGraph() }}
              title={t('viz.page.reload')}
              aria-label={t('viz.page.reloadAria')}
            >
              ↺
            </button>
            <div className="viz-ctrl-sep" />
            <button className="viz-ctrl-btn" onClick={() => orionGraphRef.current?.zoomIn()} title={t('viz.page.zoomIn')} aria-label={t('viz.page.zoomInAria')}>+</button>
            <button className="viz-ctrl-btn" onClick={() => orionGraphRef.current?.zoomOut()} title={t('viz.page.zoomOut')} aria-label={t('viz.page.zoomOutAria')}>−</button>
            <button className="viz-ctrl-btn" onClick={() => orionGraphRef.current?.fit()} title={t('viz.page.fit')} aria-label={t('viz.page.fitAria')} style={{ fontSize: '0.8rem' }}>⤢</button>
            <div className="viz-ctrl-sep" />
            <button
              className={`viz-ctrl-btn${graphLabelPlacement === 'inside' ? ' active' : ''}`}
              onClick={toggleGraphLabelPlacement}
              title={labelToggleTitle}
              aria-label={labelToggleTitle}
              aria-pressed={graphLabelPlacement === 'inside'}
              style={{ fontSize: '0.72rem' }}
            >
              Aa
            </button>
          </div>

          {orionLoaded && orionNodes.length > 0 && orionCanvasCompact && (
            <button
              type="button"
              className={`viz-filters-toggle${orionFiltersOpen ? ' active' : ''}`}
              aria-expanded={orionFiltersOpen}
              aria-controls="orion-side-panel"
              onClick={() => setOrionFiltersOpen((o) => !o)}
            >
              {t('viz.page.filters')}
            </button>
          )}

          {orionLoaded && orionNodes.length > 0 && (
            <OrionSidePanel
              id="orion-side-panel"
              compact={orionCanvasCompact}
              onClose={closeOrionFilters}
              search={orionSearchDraft}
              onSearchChange={handleOrionSearchChange}
              onClearSearch={clearOrionSearch}
              searchHits={orionSearchHits}
              focusedEntityId={orionFocusedNodeId}
              onSelectEntity={handleOrionSearchSelect}
              typeKeys={orionAllTypeKeys}
              activeTypeKeys={orionActiveTypeKeys}
              colorScale={colorScale}
              onTypeFilterChange={handleOrionTypeFilterChange}
              typeFilterDisabled={orionSearchFiltering}
            />
          )}

          {/* Status bar */}
          {orionLoaded && orionEntityCount > 0 && (
            <div className="viz-status-bar">
              <span className="viz-status-text">
                {t('viz.page.statusEntities', { count: orionEntityCount })}
                {' · '}
                {t('viz.page.statusRelations', { count: orionLinkCount })}
              </span>
            </div>
          )}

          <div className="viz-hint">{t('viz.page.hint')}</div>

          {/* Orion detail panel */}
          <NodeDetailPanel
            open={orionOpen}
            title={orionDetailTitle()}
            onClose={() => {
              setOrionDetail(null)
              setOrionFocusedNodeId(null)
              clearOrionSearch()
            }}
            footer={
              <>
                
                <a
                  href="#"
                  onClick={(e) => {
                    e.preventDefault()
                    if (orionDetail) {
                      sessionStorage.setItem('viz_filter_type', orionTypeShort)
                      sessionStorage.setItem('viz_select_id', orionDetailEntityId)
                      navigate('/entidades')
                    }
                  }}
                >
                  {t('viz.page.editInEntities')}
                </a>
                <button
                  style={{
                    background: 'var(--danger, #e63946)',
                    color: 'var(--badge-fg)',
                    border: 'none',
                    borderRadius: 6,
                    padding: '0.35rem 0.85rem',
                    fontSize: '0.82rem',
                    cursor: 'pointer',
                    fontWeight: 500,
                  }}
                  onClick={() => openDeleteModal(orionDetailEntityId)}
                >
                  {t('common.delete')}
                </button>
              </>
            }
          >
            {orionDetailBody()}
          </NodeDetailPanel>
        </div>
      </div>

      {/* Delete confirmation modal */}
      {deleteModal.open && (
        <ConfirmModal
          title={t('viz.page.deleteTitle')}
          message={
            <Trans i18nKey="viz.page.deleteMessage" values={{ id: deleteModal.entityId }} components={{ code: <code /> }} />
          }
          danger
          loading={deleteModal.loading}
          confirmLabel={t('common.delete')}
          onConfirm={() => void handleDeleteConfirm()}
          onCancel={() => setDeleteModal({ open: false, entityId: '', loading: false })}
        />
      )}
    </div>
  )
}
