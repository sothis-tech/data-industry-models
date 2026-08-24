import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
type Props = {
  title: string
  message: React.ReactNode
  entityId?: string
  confirmLabel?: string
  danger?: boolean
  loading?: boolean
  onConfirm: () => void
  onCancel: () => void
}
export function ConfirmModal({
  title,
  message,
  entityId,
  confirmLabel,
  danger = false,
  loading = false,
  onConfirm,
  onCancel,
}: Props) {
  const { t } = useTranslation()
  const cancelRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const tm = setTimeout(() => cancelRef.current?.focus(), 50)
    return () => clearTimeout(tm)
  }, [])
  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Escape') { onCancel(); return }
    if (e.key !== 'Tab') return
    const overlay = e.currentTarget as HTMLElement
    const focusable = Array.from(overlay.querySelectorAll<HTMLElement>('button:not([disabled])'))
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (e.shiftKey) {
      if (document.activeElement === first) { last?.focus(); e.preventDefault() }
    } else {
      if (document.activeElement === last) { first?.focus(); e.preventDefault() }
    }
  }
  return (
    <div
      className="modal-overlay open"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-modal-title"
      onClick={e => { if (e.target === e.currentTarget) onCancel() }}
      onKeyDown={onKeyDown}
    >
      <div className="modal-box">
        <h3 id="confirm-modal-title" className="modal-title">{title}</h3>
        <p className="modal-body">
          {message}
          {entityId && <><br /><code>{entityId}</code></>}
          {danger && <><br /><strong className="modal-danger-note">{t('confirmModal.cannotUndo')}</strong></>}
        </p>
        <div className="modal-actions">
          <button ref={cancelRef} type="button" className="secondary" onClick={onCancel} disabled={loading}>
            {t('common.cancel')}
          </button>
          <button
            type="button"
            className={danger ? 'btn-confirm-danger' : undefined}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? t('common.processing') : (confirmLabel ?? t('common.confirm'))}
          </button>
        </div>
      </div>
    </div>
  )
}
