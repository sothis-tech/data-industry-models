import { useTranslation } from 'react-i18next'
type Props = {
  open: boolean
  title: React.ReactNode
  onClose: () => void
  footer?: React.ReactNode
  children: React.ReactNode
}
export function NodeDetailPanel({ open, title, onClose, footer, children }: Props) {
  const { t } = useTranslation()
  return (
    <div className={`viz-detail-panel${open ? ' open' : ''}`}>
      <div className="viz-detail-header">
        <div className="viz-detail-title">{title}</div>
        <button className="viz-detail-close" onClick={onClose} title={t('common.close')}>
          ✕
        </button>
      </div>
      <div className="viz-detail-body">{children}</div>
      {footer && <div className="viz-detail-footer">{footer}</div>}
    </div>
  )
}
