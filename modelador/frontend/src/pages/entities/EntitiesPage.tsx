import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { deleteEntity, getEntityById } from '../../api/orion'
import {
  AGENT_APPLY_ENTITY,
  AGENT_OPEN_ENTITY,
  dispatchAgentOpenVizEntity,
  type AgentApplyEntityDetail,
  type AgentOpenEntityDetail,
} from '../../lib/agentEvents'
import { ConfirmModal } from '../../components/ConfirmModal'
import { useEntitiesStackLayout } from '../../hooks/useEntitiesStackLayout'
import { useEntityList } from '../../hooks/useEntityList'
import { useSplitResize } from '../../hooks/useSplitResize'
import {
  buildCreateBasePayload,
  normalizeImportedEntityPayload,
  parseModel,
  resolveSchemaTypeName,
} from '../../lib/model-parser'
import { getCurrentBroker } from '../../lib/storage'
import { setVizFocusEntityId } from '../../lib/vizNavigation'
import type { NgsiLdEntity } from '../../types/entity'
import { EntityCreate } from './EntityCreate'
import { EntityEdit } from './EntityEdit'
import { EntityList } from './EntityList'
import { SelectTypeModal } from './SelectTypeModal'

type Panel = 'empty' | 'create' | 'edit'

function readModelJson(): string | null {
  return localStorage.getItem('ngsi_model')
}

function entityIdFromJsonDraft(draft?: string): string | null {
  if (!draft?.trim()) return null
  try {
    const parsed = JSON.parse(draft) as { id?: unknown }
    const id = parsed.id
    return typeof id === 'string' && id.startsWith('urn:ngsi-ld:') ? id : null
  } catch {
    return null
  }
}

export function EntitiesPage() {
  const navigate = useNavigate()
  const modelJson = readModelJson()
  const { types } = parseModel(modelJson)
  const broker = getCurrentBroker()

  const [typeFilter, setTypeFilter] = useState<string>(() => {
    const vf = sessionStorage.getItem('viz_filter_type')
    if (vf) sessionStorage.removeItem('viz_filter_type')
    return vf ?? ''
  })
  const pendingSelectId = useRef<string | null>(null)
  if (pendingSelectId.current === null) {
    const vi = sessionStorage.getItem('viz_select_id')
    if (vi) { sessionStorage.removeItem('viz_select_id'); pendingSelectId.current = vi }
  }

  const [panel, setPanel] = useState<Panel>('empty')
  const [selectedEntity, setSelectedEntity] = useState<NgsiLdEntity | null>(null)
  const [createPayload, setCreatePayload] = useState<Record<string, unknown> | null>(null)
  const [dirty, setDirty] = useState(false)

  const [showTypeModal, setShowTypeModal] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [editorJsonDraft, setEditorJsonDraft] = useState<string | undefined>()

  const { containerRef, panelRef, width, resizerProps } = useSplitResize('ngsi_entities_list_panel_width', 320)
  const { isStacked, stackPane, focusDetailPane, focusListPane } = useEntitiesStackLayout(containerRef)

  const entityList = useEntityList(broker?.url ?? null, typeFilter, modelJson, types, broker?.tenant)

  const guardDirty = useCallback((action: () => void) => {
    if (dirty && !confirm('Tienes cambios sin guardar. ¿Deseas descartarlos?')) return
    setDirty(false)
    action()
  }, [dirty])

  useEffect(() => {
    localStorage.setItem('ngsi_onboarding_step3_done', '1')
  }, [])

  useEffect(() => {
    function onApplyEntity(event: Event) {
      const { payload } = (event as CustomEvent<AgentApplyEntityDetail>).detail
      if (!payload || typeof payload !== 'object') return
      const normalized = normalizeImportedEntityPayload(payload as Record<string, unknown>, modelJson)
      const type = resolveSchemaTypeName(normalized.type)
      guardDirty(() => {
        if (type) setTypeFilter(type)
        setCreatePayload(normalized)
        setSelectedEntity(null)
        setPanel('create')
        focusDetailPane()
      })
    }

    async function onOpenEntity(event: Event) {
      const { entityId } = (event as CustomEvent<AgentOpenEntityDetail>).detail
      if (!entityId || !broker?.url) return
      guardDirty(() => {
        void (async () => {
          let target = entityList.filteredEntities.find((e) => e.id === entityId)
          if (!target) {
            const { body } = await getEntityById(broker.url, entityId, broker.tenant)
            if (body?.id) target = body as NgsiLdEntity
          }
          if (target) {
            const t = String(target.type ?? '').split('/').pop() ?? ''
            if (t) setTypeFilter(t)
            handleSelectEntity(target)
          }
        })()
      })
    }

    window.addEventListener(AGENT_APPLY_ENTITY, onApplyEntity)
    window.addEventListener(AGENT_OPEN_ENTITY, onOpenEntity)
    return () => {
      window.removeEventListener(AGENT_APPLY_ENTITY, onApplyEntity)
      window.removeEventListener(AGENT_OPEN_ENTITY, onOpenEntity)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [broker?.url, entityList.filteredEntities])

  useEffect(() => {
    if (!broker?.url) return
    entityList.fetchEntities().then(async () => {
      const pid = pendingSelectId.current
      if (!pid) return
      pendingSelectId.current = null
      let target = entityList.filteredEntities.find(e => e.id === pid)
      if (!target) {
        const { body } = await getEntityById(broker.url, pid, broker.tenant)
        if (body?.id) target = body as NgsiLdEntity
      }
      if (target) handleSelectEntity(target)
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [broker?.url])

  function handleTypeFilterChange(newType: string) {
    if (panel === 'create') {
      guardDirty(() => {
        setTypeFilter(newType)
        if (newType) {
          const { payload } = buildCreateBasePayload(newType, modelJson)
          setCreatePayload(payload)
        } else {
          setPanel('empty')
          setCreatePayload(null)
        }
      })
    } else {
      setTypeFilter(newType)
    }
  }

  function handleSelectEntity(entity: NgsiLdEntity) {
    guardDirty(() => {
      setSelectedEntity(entity)
      setPanel('edit')
      focusDetailPane()
    })
  }

  function handleNewEntity() {
    guardDirty(() => {
      const type = typeFilter
      if (!type) {
        if (!types.length) { alert('No hay tipos disponibles. Carga un modelo en Configuración.'); return }
        setShowTypeModal(true)
        return
      }
      const { payload } = buildCreateBasePayload(type, modelJson)
      setCreatePayload(payload)
      setSelectedEntity(null)
      setPanel('create')
      focusDetailPane()
    })
  }

  function handleTypeModalConfirm(type: string) {
    setShowTypeModal(false)
    if (typeFilter !== type) setTypeFilter(type)
    const { payload } = buildCreateBasePayload(type, modelJson)
    setCreatePayload(payload)
    setSelectedEntity(null)
    setPanel('create')
    focusDetailPane()
  }

  async function handleEntityCreated(entity: NgsiLdEntity) {
    setDirty(false)
    await entityList.fetchEntities()
    const found = entityList.allEntities.find(e => e.id === entity.id) ?? entity
    setSelectedEntity(found)
    setPanel('edit')
    focusDetailPane()
  }

  async function handleEntitySaved() {
    setDirty(false)
    await entityList.fetchEntities()
  }

  async function handleDeleteConfirm() {
    if (!selectedEntity || !broker?.url) return
    setDeleting(true)
    const { status, error } = await deleteEntity(broker.url, selectedEntity.id, broker.tenant)
    setDeleting(false)
    setShowDeleteModal(false)
    if (!error && status >= 200 && status < 300) {
      setDirty(false)
      setSelectedEntity(null)
      setPanel('empty')
      focusListPane()
      await entityList.fetchEntities()
    } else {
      alert(`Error al eliminar (${status}): ${error ?? 'Error desconocido'}`)
    }
  }

  async function handleDuplicate() {
    if (!selectedEntity) return
    const type = (String(selectedEntity.type ?? '').split('/').pop()) ?? ''
    if (!type) return
    if (typeFilter !== type) setTypeFilter(type)
    const cloned = JSON.parse(JSON.stringify(selectedEntity)) as Record<string, unknown>
    const compacted = normalizeImportedEntityPayload(cloned, modelJson)
    compacted.type = type
    const origId = (compacted.id ?? cloned.id) as string
    compacted.id = origId.endsWith('-copy') ? `${origId}-001` : `${origId}-copy`
    setCreatePayload(compacted)
    setSelectedEntity(null)
    setPanel('create')
    focusDetailPane()
  }

  const titleEntity = selectedEntity
    ? (() => {
        const n = selectedEntity.name
        const label = n && typeof n === 'object' && 'value' in (n as object)
          ? String((n as { value?: unknown }).value ?? '')
          : typeof n === 'string' ? n : ''
        return label || selectedEntity.id.split(':').pop() || selectedEntity.id
      })()
    : ''
  const titleType = selectedEntity
    ? (String(selectedEntity.type ?? '').split('/').pop() ?? '')
    : typeFilter || ''

  const vizEntityId =
    panel === 'edit' && selectedEntity?.id
      ? selectedEntity.id
      : panel === 'create'
        ? (typeof createPayload?.id === 'string' ? createPayload.id : null)
          ?? entityIdFromJsonDraft(editorJsonDraft)
        : null

  function handleOpenInVisualization() {
    if (!vizEntityId?.startsWith('urn:ngsi-ld:')) return
    setVizFocusEntityId(vizEntityId)
    dispatchAgentOpenVizEntity({ entityId: vizEntityId })
    navigate('/visualizacion')
  }

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key !== 's') return
      e.preventDefault()
      if (panel === 'edit') document.getElementById('btn-patch-save')?.click()
      else if (panel === 'create') document.getElementById('btn-create-save')?.click()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [panel])

  useEffect(() => {
    if (!dirty) return
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])

  useEffect(() => {
    if (panel === 'empty') focusListPane()
  }, [panel, focusListPane])

  const pageClass = [
    'entities-page',
    isStacked ? 'entities-page--stacked' : '',
    isStacked ? `entities-page--pane-${stackPane}` : '',
  ]
    .filter(Boolean)
    .join(' ')

  const showBackToList = isStacked && panel !== 'empty'

  return (
    <div className={pageClass} ref={containerRef}>
      <div
        className="entities-list-panel"
        ref={panelRef}
        style={isStacked ? undefined : { width }}
      >
        <EntityList
          entities={entityList.filteredEntities}
          allCount={entityList.typeFilteredEntities.length}
          types={types}
          typeFilter={typeFilter}
          search={entityList.search}
          loading={entityList.loading}
          loadCount={entityList.loadCount}
          error={entityList.error}
          selectedId={selectedEntity?.id ?? null}
          onTypeFilterChange={handleTypeFilterChange}
          onSearchChange={entityList.setSearch}
          onSelect={e => guardDirty(() => handleSelectEntity(e))}
          onNewEntity={handleNewEntity}
        />
      </div>

      <div
        className="entities-resizer"
        role="separator"
        aria-orientation="vertical"
        aria-label="Redimensionar panel de lista"
        tabIndex={0}
        {...resizerProps}
      />

      <div className="entities-detail-panel">
        <div className="detail-header">
          <div className="detail-header-meta">
            {showBackToList && (
              <button
                type="button"
                className="secondary entities-back-btn"
                onClick={() => focusListPane()}
                aria-label="Volver a la lista de entidades"
              >
                ← Lista
              </button>
            )}
            <h2>{panel === 'empty' ? 'Entidades' : panel === 'create' ? 'Nueva entidad' : titleEntity}</h2>
            {titleType && panel !== 'empty' && (
              <span className="type-badge">{titleType}</span>
            )}
          </div>
          <div className="detail-header-actions">
            {vizEntityId?.startsWith('urn:ngsi-ld:') && (
              <button
                type="button"
                className="secondary"
                style={{ fontSize: '0.78rem' }}
                onClick={handleOpenInVisualization}
              >
                Ver en visualización
              </button>
            )}
            {panel === 'edit' && (
              <button
                type="button"
                className="secondary"
                style={{ fontSize: '0.78rem' }}
                onClick={handleDuplicate}
              >
                Duplicar
              </button>
            )}
          </div>
        </div>

        {panel === 'empty' && (
          <div className="entities-empty">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="3" y="3" width="18" height="18" rx="3" />
              <path d="M3 9h18M9 21V9" />
            </svg>
            <p>Selecciona una entidad para editarla<br />o crea una nueva.</p>
          </div>
        )}

        {panel === 'create' && broker?.url && (
          <EntityCreate
            type={typeFilter}
            modelJson={modelJson}
            brokerUrl={broker.url}
            brokerTenant={broker.tenant}
            initialPayload={createPayload}
            onDirty={() => setDirty(true)}
            onCreated={handleEntityCreated}
            onJsonDraftChange={setEditorJsonDraft}
          />
        )}

        {panel === 'edit' && selectedEntity && broker?.url && (
          <EntityEdit
            entity={selectedEntity}
            brokerUrl={broker.url}
            brokerTenant={broker.tenant}
            onDirty={() => setDirty(true)}
            onSaved={handleEntitySaved}
            onDelete={() => setShowDeleteModal(true)}
            onJsonDraftChange={setEditorJsonDraft}
          />
        )}
      </div>

      {showTypeModal && (
        <SelectTypeModal
          types={types}
          onConfirm={handleTypeModalConfirm}
          onClose={() => setShowTypeModal(false)}
        />
      )}

      {showDeleteModal && selectedEntity && (
        <ConfirmModal
          title="¿Eliminar entidad?"
          message="Se eliminará permanentemente la entidad"
          entityId={selectedEntity.id}
          confirmLabel="Eliminar"
          danger
          loading={deleting}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setShowDeleteModal(false)}
        />
      )}
    </div>
  )
}
