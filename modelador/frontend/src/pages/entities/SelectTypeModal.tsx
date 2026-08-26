import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

type Props = {
  types: string[]
  onConfirm: (type: string) => void
  onClose: () => void
}

export function SelectTypeModal({ types, onConfirm, onClose }: Props) {
  const { t } = useTranslation()
  const [selected, setSelected] = useState(types[0] ?? '')
  const selectRef = useRef<HTMLSelectElement>(null)

  useEffect(() => {
    const t = setTimeout(() => selectRef.current?.focus(), 30)
    return () => clearTimeout(t)
  }, [])

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Escape') onClose()
  }

  return (
    <div
      className="modal-overlay open"
      role="dialog"
      aria-modal="true"
      aria-labelledby="select-type-modal-title"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
      onKeyDown={onKeyDown}
    >
      <div className="modal-box">
        <h3 id="select-type-modal-title" className="modal-title">{t('entities.selectType.title')}</h3>
        <p className="modal-body">{t('entities.selectType.intro')}</p>
        <div className="form-group" style={{ marginBottom: '1rem' }}>
          <label htmlFor="create-type-select">{t('entities.selectType.label')}</label>
          <select
            id="create-type-select"
            ref={selectRef}
            value={selected}
            onChange={e => setSelected(e.target.value)}
          >
            {types.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={onClose}>{t('common.cancel')}</button>
          <button
            type="button"
            disabled={!selected}
            onClick={() => { if (selected) onConfirm(selected) }}
          >
            {t('common.continue')}
          </button>
        </div>
      </div>
    </div>
  )
}
