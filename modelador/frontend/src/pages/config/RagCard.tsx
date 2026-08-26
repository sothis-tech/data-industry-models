import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react'
import { useTranslation, Trans } from 'react-i18next'
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
  const { t } = useTranslation()
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
      ? t('config.rag.confirmDeleteDisk', { filename })
      : t('config.rag.confirmRemoveIndex', { filename })
    if (!window.confirm(msg)) return
    try {
      await deleteRagDocument(ragSpaceId, brokerBaseUrl, filename, fromDisk, fiwareTenant)
      flash(fromDisk
        ? t('config.rag.flashDeleted', { filename })
        : t('config.rag.flashRemoved', { filename }), true)
      loadDocs()
    } catch (e) {
      flash(String(e), false)
    }
  }

  const handleVectorize = async () => {
    setVectorizing(true)
    try {
      const res = await vectorizeRagTenant(ragSpaceId, brokerBaseUrl, fiwareTenant)
      flash(t('config.rag.flashVectorized', { count: res.processed }), true)
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
      flash(t('config.rag.flashCleared'), true)
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
  if (!config) return <p className="rag-loading">{t('config.rag.loadingConfig')}</p>

  if (!config.enabled) {
    return (
      <div className="rag-panel-disabled">
        <p>{t('config.rag.notConfigured')}</p>
        <code>RAG_URL</code>
        <p className="rag-hint">{t('config.rag.setEnvVar')}</p>
      </div>
    )
  }

  if (!fiwareTenant) {
    return (
      <div className="rag-panel-needs-tenant">
        <p className="rag-needs-tenant-title">{t('config.rag.tenantRequired')}</p>
        <p>
          <Trans i18nKey="config.rag.tenantRequiredBody" components={{ strong: <strong /> }} />
        </p>
        <p className="rag-hint">
          <Trans i18nKey="config.rag.tenantRequiredHint" components={{ strong: <strong /> }} />
        </p>
        <p className="rag-hint rag-hint--dev">
          <Trans i18nKey="config.rag.tenantRequiredDev" components={{ code: <code /> }} />
        </p>
      </div>
    )
  }

  if (!isOrionAuthenticated) {
    return (
      <div className="rag-panel-needs-tenant">
        <p className="rag-needs-tenant-title">{t('config.rag.sessionRequired')}</p>
        <p>{t('config.rag.sessionRequiredBody')}</p>
        <p className="rag-hint">
          <Trans i18nKey="config.rag.sessionRequiredHint" components={{ strong: <strong /> }} />
        </p>
      </div>
    )
  }

  const pendingDocs = docs?.not_indexed ?? []
  const indexedDocs = Object.entries(docs?.indexed ?? {}) as [string, DocInfo][]

  return (
    <div className="rag-panel-content">

      <div className="rag-section">
        <p className="rag-section-label">{t('config.rag.spaceLabel')}</p>
        <p className="rag-space-id"><code>{ragSpaceId}</code></p>
        <p className="rag-hint">{t('config.rag.spaceHint')}</p>
      </div>

      {/* ── Documentos indexados ── */}
      <div className="rag-section">
        <p className="rag-section-label">
          {t('config.rag.indexed')}
          {docs !== null && <span className="rag-section-count">{indexedDocs.length}</span>}
        </p>
        {docsLoading ? (
          <p className="rag-hint">{t('common.loading')}</p>
        ) : indexedDocs.length === 0 ? (
          <p className="rag-hint">{t('config.rag.noIndexed')}</p>
        ) : (
          <ul className="rag-doc-list">
            {indexedDocs.map(([name, info]) => (
              <li key={name} className="rag-doc-item">
                <div className="rag-doc-info">
                  <span className="rag-doc-name" title={name}>{name}</span>
                  <span className="rag-doc-meta">{t('config.rag.docMeta', { chunks: info.chunks, pages: info.pages })}</span>
                </div>
                <div className="rag-doc-actions rag-doc-actions--row">
                  <button
                    type="button"
                    className="rag-btn rag-btn--ghost rag-btn--compact"
                    onClick={() => void handleDeleteDoc(name, false)}
                    title={t('config.rag.removeIndexTitle')}
                  >
                    {t('config.rag.removeIndex')}
                  </button>
                  <button
                    type="button"
                    className="rag-btn rag-btn--danger rag-btn--compact"
                    onClick={() => void handleDeleteDoc(name, true)}
                    title={t('config.rag.deleteFileTitle')}
                  >
                    {t('config.rag.deleteFile')}
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
            {t('config.rag.pending')}
            <span className="rag-section-count rag-section-count--warn">{pendingDocs.length}</span>
          </p>
          <ul className="rag-doc-list">
            {pendingDocs.map((name) => (
              <li key={name} className="rag-doc-item rag-doc-item--pending">
                <div className="rag-doc-info">
                  <span className="rag-doc-name" title={name}>{name}</span>
                  <span className="rag-doc-meta">{t('config.rag.pendingMeta')}</span>
                </div>
                <div className="rag-doc-actions rag-doc-actions--row">
                  <button
                    type="button"
                    className="rag-btn rag-btn--danger rag-btn--compact"
                    onClick={() => void handleDeleteDoc(name, true)}
                    title={t('config.rag.removeFromDiskTitle')}
                  >
                    {t('config.rag.remove')}
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
              ? t('config.rag.vectorizing')
              : t('config.rag.vectorizePending', { count: pendingDocs.length })}
          </button>
        </div>
      )}

      {/* ── Subida de documentos ── */}
      <div className="rag-section">
        <p className="rag-section-label">{t('config.rag.uploadDoc')}</p>
        <div className="rag-field">
          <label htmlFor="rag-collection">{t('config.rag.collection')}</label>
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
          aria-label={t('config.rag.dropzoneAria')}
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
              <span className="rag-drop-label">{t('config.rag.dropLabel')}</span>
              <span className="rag-drop-hint">
                {t('config.rag.dropHint', { extensions: (config.allowed_extensions ?? []).join(' · '), maxMb: config.max_mb })}
              </span>
            </>
          )}
        </div>
        {lastUpload && (
          <div className={`rag-result rag-result--${lastUpload.ok ? 'ok' : 'err'}`}>
            {lastUpload.ok
              ? t('config.rag.uploadOk', { filename: lastUpload.filename })
              : t('config.rag.uploadErr', { error: lastUpload.error ?? t('config.rag.unknownError') })}
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
              ? t('config.rag.clearing')
              : confirmClear
                ? t('config.rag.confirmClear')
                : t('config.rag.clearIndex')}
          </button>
          {confirmClear && (
            <button
              className="rag-btn rag-btn--ghost rag-btn--full"
              style={{ marginTop: 4 }}
              onClick={() => setConfirmClear(false)}
            >
              {t('common.cancel')}
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
