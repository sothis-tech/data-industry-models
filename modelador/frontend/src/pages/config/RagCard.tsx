import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react'
import {
  getRagConfig,
  createRagTenant,
  listRagDocuments,
  deleteRagDocument,
  vectorizeRagTenant,
  clearRagIndex,
  uploadRagDocument,
} from '../../api/rag'
import { normalizeRagTenantId } from '../../lib/ragTenant'
import type { RagConfig, RagDocuments, RagUploadResult, UploadStatus, DocInfo } from '../../types/rag'

type Props = {
  activeBrokerUrl?: string
  activeTenant?: string
  isOrionAuthenticated?: boolean
  ragPanelOpen?: boolean
}
type OpStatus = { msg: string; ok: boolean } | null

const OP_FLASH_MS = 4200
const UPLOAD_MSG_MS = 5000

export function RagCard({
  activeBrokerUrl,
  activeTenant,
  isOrionAuthenticated = false,
  ragPanelOpen = true,
}: Props) {
  const [config, setConfig]                     = useState<RagConfig | null>(null)
  const [docs, setDocs]                         = useState<RagDocuments | null>(null)
  const [docsLoading, setDocsLoading]           = useState(false)
  const [collection, setCollection]             = useState('documents')
  const [dragging, setDragging]                 = useState(false)
  const [uploadStatus, setUploadStatus]         = useState<UploadStatus>('idle')
  const [uploadProgress, setUploadProgress]     = useState(0)
  const [lastUpload, setLastUpload]             = useState<RagUploadResult | null>(null)
  const [opStatus, setOpStatus]                 = useState<OpStatus>(null)
  const [vectorizing, setVectorizing]           = useState(false)
  const [clearing, setClearing]                 = useState(false)
  const [confirmClear, setConfirmClear]         = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const opFlashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const uploadMsgTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearTransientFeedback = useCallback(() => {
    if (opFlashTimerRef.current) {
      clearTimeout(opFlashTimerRef.current)
      opFlashTimerRef.current = null
    }
    if (uploadMsgTimerRef.current) {
      clearTimeout(uploadMsgTimerRef.current)
      uploadMsgTimerRef.current = null
    }
    setOpStatus(null)
    setLastUpload(null)
    setUploadStatus('idle')
    setConfirmClear(false)
  }, [])

  useEffect(() => {
    if (!ragPanelOpen) clearTransientFeedback()
  }, [ragPanelOpen, clearTransientFeedback])

  useEffect(
    () => () => {
      if (opFlashTimerRef.current) clearTimeout(opFlashTimerRef.current)
      if (uploadMsgTimerRef.current) clearTimeout(uploadMsgTimerRef.current)
    },
    [],
  )

  const flash = (msg: string, ok: boolean) => {
    if (opFlashTimerRef.current) {
      clearTimeout(opFlashTimerRef.current)
      opFlashTimerRef.current = null
    }
    setOpStatus({ msg, ok })
    opFlashTimerRef.current = setTimeout(() => {
      setOpStatus(null)
      opFlashTimerRef.current = null
    }, OP_FLASH_MS)
  }

  const scheduleUploadMessageDismiss = useCallback(() => {
    if (uploadMsgTimerRef.current) {
      clearTimeout(uploadMsgTimerRef.current)
      uploadMsgTimerRef.current = null
    }
    uploadMsgTimerRef.current = setTimeout(() => {
      setLastUpload(null)
      setUploadStatus('idle')
      uploadMsgTimerRef.current = null
    }, UPLOAD_MSG_MS)
  }, [])

  const fiwareTenant = activeTenant?.trim() ?? ''
  const brokerBaseUrl = activeBrokerUrl?.trim() ?? ''
  const ragSpaceId = fiwareTenant ? normalizeRagTenantId(fiwareTenant) : ''

  // ── Cargar config ─────────────────────────────────────────────────────────
  useEffect(() => {
    getRagConfig()
      .then(setConfig)
      .catch(() =>
        setConfig({ enabled: false, max_mb: 20, allowed_extensions: ['.pdf', '.txt', '.md', '.docx'], chroma_db: 'default' }),
      )
  }, [])

  // ── Asegurar espacio en rag-manager (Chroma + .tenants.json) ───────────────
  useEffect(() => {
    if (!config?.enabled || !fiwareTenant) return
    void createRagTenant(fiwareTenant).catch(() => {
      /* idempotente / errores de red: no bloquear la UI */
    })
  }, [config?.enabled, fiwareTenant])

  useEffect(() => {
    if (!isOrionAuthenticated) setDocs(null)
  }, [isOrionAuthenticated])

  // ── Cargar documentos ─────────────────────────────────────────────────────
  const loadDocs = useCallback(() => {
    if (!ragSpaceId || !brokerBaseUrl || !isOrionAuthenticated) return
    setDocsLoading(true)
    listRagDocuments(ragSpaceId, brokerBaseUrl, fiwareTenant)
      .then(setDocs)
      .catch(() => setDocs(null))
      .finally(() => setDocsLoading(false))
  }, [brokerBaseUrl, fiwareTenant, isOrionAuthenticated, ragSpaceId])

  useEffect(() => { loadDocs() }, [loadDocs])

  // ── Handlers ──────────────────────────────────────────────────────────────
  const handleDeleteDoc = async (filename: string, fromDisk: boolean) => {
    const msg = fromDisk
      ? `¿Eliminar "${filename}" del índice y del disco?`
      : `¿Quitar "${filename}" del índice? El archivo se conserva en disco.`
    if (!window.confirm(msg)) return
    try {
      await deleteRagDocument(ragSpaceId, brokerBaseUrl, filename, fromDisk, fiwareTenant)
      flash(`"${filename}" ${fromDisk ? 'eliminado' : 'quitado del índice'}`, true)
      loadDocs()
    } catch (e) {
      flash(String(e), false)
    }
  }

  const handleVectorize = async () => {
    setVectorizing(true)
    try {
      const res = await vectorizeRagTenant(ragSpaceId, brokerBaseUrl, fiwareTenant)
      flash(`Vectorizados ${res.processed} documentos`, true)
      loadDocs()
    } catch (e) {
      flash(String(e), false)
    } finally {
      setVectorizing(false)
    }
  }

  const handleClear = async () => {
    if (!confirmClear) { setConfirmClear(true); return }
    setClearing(true)
    setConfirmClear(false)
    try {
      await clearRagIndex(ragSpaceId, brokerBaseUrl, fiwareTenant)
      flash('Índice vaciado', true)
      loadDocs()
    } catch (e) {
      flash(String(e), false)
    } finally {
      setClearing(false)
    }
  }

  const handleFile = useCallback(
    async (file: File) => {
      if (!config?.enabled || !ragSpaceId || !fiwareTenant || !brokerBaseUrl || !isOrionAuthenticated) return
      if (uploadMsgTimerRef.current) {
        clearTimeout(uploadMsgTimerRef.current)
        uploadMsgTimerRef.current = null
      }
      setUploadStatus('uploading')
      setUploadProgress(0)
      setLastUpload(null)
      try {
        const result = await uploadRagDocument(
          file,
          ragSpaceId,
          brokerBaseUrl,
          collection,
          setUploadProgress,
          fiwareTenant,
        )
        setLastUpload(result)
        setUploadStatus(result.ok ? 'success' : 'error')
        scheduleUploadMessageDismiss()
        if (result.ok) loadDocs()
      } catch (err) {
        setLastUpload({ ok: false, status: 0, filename: file.name, error: String(err) })
        setUploadStatus('error')
        scheduleUploadMessageDismiss()
      }
    },
    [brokerBaseUrl, config, isOrionAuthenticated, ragSpaceId, fiwareTenant, collection, loadDocs, scheduleUploadMessageDismiss],
  )

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) void handleFile(file)
  }

  // ── Render ────────────────────────────────────────────────────────────────
  if (!config) return <p className="rag-loading">Cargando configuración…</p>

  if (!config.enabled) {
    return (
      <div className="rag-panel-disabled">
        <p>El servicio RAG no está configurado.</p>
        <code>RAG_URL</code>
        <p className="rag-hint">Establece la variable de entorno en el servidor para habilitarlo.</p>
      </div>
    )
  }

  if (!fiwareTenant) {
    return (
      <div className="rag-panel-needs-tenant">
        <p className="rag-needs-tenant-title">Tenant obligatorio</p>
        <p>
          Para gestionar documentación RAG, la conexión Orion activa debe tener el campo{' '}
          <strong>Tenant / NGSILD-Tenant</strong> definido: es el mismo identificador que Orion y el espacio en Chroma.
        </p>
        <p className="rag-hint">
          Cierra este panel, edita la tarjeta <strong>Conexión Orion (tenant)</strong>, rellena el tenant, y pulsa{' '}
          <strong>Guardar</strong>, o pulsa <strong>Usar</strong> en una conexión guardada que ya lo incluya.
        </p>
        <p className="rag-hint rag-hint--dev">
          <code>RAG_CHROMA_DB</code> en el servidor sigue siendo útil como valor por defecto en el proxy cuando una petición
          llega sin tenant; este panel no lo usa: siempre depende de la conexión Orion activa.
        </p>
      </div>
    )
  }

  if (!isOrionAuthenticated) {
    return (
      <div className="rag-panel-needs-tenant">
        <p className="rag-needs-tenant-title">Sesión Orion requerida</p>
        <p>
          Para consultar o gestionar documentación RAG debes iniciar sesión primero en la conexión Orion activa.
        </p>
        <p className="rag-hint">
          Pulsa <strong>Usar</strong> en una conexión guardada si necesitas cargar sus parámetros, introduce usuario y
          contraseña, y después pulsa <strong>Conectar</strong>.
        </p>
      </div>
    )
  }

  const pendingDocs = docs?.not_indexed ?? []
  const indexedDocs = Object.entries(docs?.indexed ?? {}) as [string, DocInfo][]

  return (
    <div className="rag-panel-content">

      <div className="rag-section">
        <p className="rag-section-label">Espacio RAG (tenant Chroma)</p>
        <p className="rag-space-id"><code>{ragSpaceId}</code></p>
        <p className="rag-hint">Derivado del tenant de la conexión Orion activa (normalizado igual que en el servicio RAG).</p>
      </div>

      {/* ── Documentos indexados ── */}
      <div className="rag-section">
        <p className="rag-section-label">
          Indexados
          {docs !== null && <span className="rag-section-count">{indexedDocs.length}</span>}
        </p>
        {docsLoading ? (
          <p className="rag-hint">Cargando…</p>
        ) : indexedDocs.length === 0 ? (
          <p className="rag-hint">Sin documentos indexados.</p>
        ) : (
          <ul className="rag-doc-list">
            {indexedDocs.map(([name, info]) => (
              <li key={name} className="rag-doc-item">
                <div className="rag-doc-info">
                  <span className="rag-doc-name" title={name}>{name}</span>
                  <span className="rag-doc-meta">{info.chunks} chunks · {info.pages} pág.</span>
                </div>
                <div className="rag-doc-actions rag-doc-actions--row">
                  <button
                    type="button"
                    className="rag-btn rag-btn--ghost rag-btn--compact"
                    onClick={() => void handleDeleteDoc(name, false)}
                    title="Quitar del índice (el archivo sigue en disco)"
                  >
                    Quitar índice
                  </button>
                  <button
                    type="button"
                    className="rag-btn rag-btn--danger rag-btn--compact"
                    onClick={() => void handleDeleteDoc(name, true)}
                    title="Eliminar del índice y borrar el archivo en disco"
                  >
                    Borrar archivo
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* ── Documentos pendientes ── */}
      {pendingDocs.length > 0 && (
        <div className="rag-section">
          <p className="rag-section-label">
            Pendientes de vectorizar
            <span className="rag-section-count rag-section-count--warn">{pendingDocs.length}</span>
          </p>
          <ul className="rag-doc-list">
            {pendingDocs.map((name) => (
              <li key={name} className="rag-doc-item rag-doc-item--pending">
                <div className="rag-doc-info">
                  <span className="rag-doc-name" title={name}>{name}</span>
                  <span className="rag-doc-meta">Pendiente de vectorizar</span>
                </div>
                <div className="rag-doc-actions rag-doc-actions--row">
                  <button
                    type="button"
                    className="rag-btn rag-btn--danger rag-btn--compact"
                    onClick={() => void handleDeleteDoc(name, true)}
                    title="Eliminar archivo del disco"
                  >
                    Quitar
                  </button>
                </div>
              </li>
            ))}
          </ul>
          <button
            className="rag-btn rag-btn--primary rag-btn--full"
            onClick={() => void handleVectorize()}
            disabled={vectorizing}
            style={{ marginTop: 8 }}
          >
            {vectorizing
              ? 'Vectorizando…'
              : `Vectorizar ${pendingDocs.length} pendiente${pendingDocs.length > 1 ? 's' : ''}`}
          </button>
        </div>
      )}

      {/* ── Subida de documentos ── */}
      <div className="rag-section">
        <p className="rag-section-label">Subir documento</p>
        <div className="rag-field">
          <label htmlFor="rag-collection">Colección</label>
          <input
            id="rag-collection"
            value={collection}
            onChange={(e) => setCollection(e.target.value)}
            placeholder="documents"
          />
        </div>
        <div
          className={`rag-dropzone${dragging ? ' rag-dropzone--drag' : ''}${uploadStatus === 'uploading' ? ' rag-dropzone--uploading' : ''}`}
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          role="button"
          tabIndex={0}
          aria-label="Zona de arrastrar o seleccionar documento"
          onKeyDown={(e) => { if (e.key === 'Enter') fileInputRef.current?.click() }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={(config.allowed_extensions ?? ['.pdf', '.txt', '.md', '.docx']).join(',')}
            style={{ display: 'none' }}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) void handleFile(f)
              e.target.value = ''
            }}
          />
          {uploadStatus === 'uploading' ? (
            <div className="rag-progress">
              <div
                className="rag-progress-bar"
                style={{ ['--w']: `${uploadProgress}%` } as Record<string, string>}
              />
              <span>{uploadProgress}%</span>
            </div>
          ) : (
            <>
              <span className="rag-drop-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                  strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="12" y1="12" x2="12" y2="18" />
                  <line x1="9" y1="15" x2="15" y2="15" />
                </svg>
              </span>
              <span className="rag-drop-label">Arrastra o haz clic</span>
              <span className="rag-drop-hint">
                {(config.allowed_extensions ?? []).join(' · ')} · máx {config.max_mb} MB
              </span>
            </>
          )}
        </div>
        {lastUpload && (
          <div className={`rag-result rag-result--${lastUpload.ok ? 'ok' : 'err'}`}>
            {lastUpload.ok
              ? `✓ "${lastUpload.filename}" subido`
              : `✗ ${lastUpload.error ?? 'Error desconocido'}`}
          </div>
        )}
      </div>

      {/* ── Acciones peligrosas ── */}
      {(indexedDocs.length > 0 || pendingDocs.length > 0) && (
        <div className="rag-section rag-section--danger">
          <button
            className={`rag-btn rag-btn--full ${confirmClear ? 'rag-btn--danger' : 'rag-btn--ghost'}`}
            onClick={() => void handleClear()}
            disabled={clearing}
          >
            {clearing
              ? 'Vaciando…'
              : confirmClear
                ? '¿Confirmar? Pulsa de nuevo para vaciar'
                : 'Vaciar índice'}
          </button>
          {confirmClear && (
            <button
              className="rag-btn rag-btn--ghost rag-btn--full"
              style={{ marginTop: 4 }}
              onClick={() => setConfirmClear(false)}
            >
              Cancelar
            </button>
          )}
        </div>
      )}

      {/* ── Feedback de operaciones ── */}
      {opStatus && (
        <div className={`rag-result rag-result--${opStatus.ok ? 'ok' : 'err'}`}>
          {opStatus.msg}
        </div>
      )}
    </div>
  )
}
