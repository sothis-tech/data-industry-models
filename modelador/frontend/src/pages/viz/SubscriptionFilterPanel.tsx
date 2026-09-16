import { useTranslation } from 'react-i18next'
import {
  SUBSCRIPTION_FILTER_OPTIONS,
  type SubscriptionFilterMode,
} from '../../lib/subscriptions'

type Props = {
  mode: SubscriptionFilterMode
  onChange: (mode: SubscriptionFilterMode) => void
  subscribedCount: number
  disabled?: boolean
  error?: string | null
}

export function SubscriptionFilterPanel({
  mode,
  onChange,
  subscribedCount,
  disabled = false,
  error = null,
}: Props) {
  const { t } = useTranslation()

  return (
    <div
      className={`orion-sub-filter${disabled ? ' is-disabled' : ''}`}
      aria-disabled={disabled || undefined}
    >
      <div className="orion-sub-filter-head">
        <div className="orion-sub-filter-title">
          {t('viz.orionPanel.subscriptionsTitle')}
          <span className="orion-sub-filter-count">
            {error ? '—' : t('viz.orionPanel.subscribedCount', { count: subscribedCount })}
          </span>
        </div>
      </div>
      {error ? (
        <p className="orion-sub-filter-error" role="status">
          {error}
        </p>
      ) : (
        <div
          className="orion-sub-filter-list"
          role="radiogroup"
          aria-label={t('entities.list.subscriptionFilterAria')}
        >
          {SUBSCRIPTION_FILTER_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className={`orion-sub-filter-row${mode === opt.value ? '' : ' dimmed'}`}
            >
              <input
                type="radio"
                name="orion-sub-filter"
                value={opt.value}
                checked={mode === opt.value}
                disabled={disabled}
                onChange={() => onChange(opt.value)}
              />
              <span className="orion-sub-filter-label">{t(opt.labelKey)}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}
