import { useState } from 'react'
import { useTranslation, Trans } from 'react-i18next'
import { Link } from 'react-router-dom'
import { getModelJson } from '../../lib/modelStore'
import { getCurrentBroker } from '../../lib/storage'
const HIDDEN_KEY = 'ngsi_onboarding_hidden'
const STEP3_KEY = 'ngsi_onboarding_step3_done'
function hasOrionConnection() {
  return getCurrentBroker() !== null
}
function hasModel() {
  try {
    const raw = getModelJson()
    if (!raw) return false
    const m = JSON.parse(raw) as {
      schemas?: unknown[]
      context?: unknown
      descriptor?: unknown
    }
    return !!(
      (m.schemas && (m.schemas as unknown[]).length > 0) ||
      m.context ||
      m.descriptor
    )
  } catch {
    return false
  }
}
function hasVisitedApp() {
  return localStorage.getItem(STEP3_KEY) === '1'
}
type Props = {
  /** Se incrementa desde ConfigPage tras guardar broker o modelo, para refrescar. */
  refreshKey?: number
}
export function OnboardingCard({ refreshKey = 0 }: Props) {
  const { t } = useTranslation()
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(HIDDEN_KEY) === '1',
  )
  // refreshKey se lee sólo para forzar re-render cuando el padre lo cambia.
  void refreshKey
  const step1 = hasOrionConnection()
  const step2 = hasModel()
  const step3 = hasVisitedApp()
  const completed = Number(step1) + Number(step2) + Number(step3)
  function toggleCollapse() {
    const next = !collapsed
    setCollapsed(next)
    if (next) {
      localStorage.setItem(HIDDEN_KEY, '1')
    } else {
      localStorage.removeItem(HIDDEN_KEY)
    }
  }
  return (
    <div className="onboarding-card">
      <div className="onboarding-head">
        <h3>{t('config.onboarding.title', { completed })}</h3>
        <button className="onboarding-toggle" onClick={toggleCollapse}>
          {collapsed ? t('config.onboarding.show') : t('config.onboarding.hide')}
        </button>
      </div>
      {!collapsed && (
        <>
          <ol className="onboarding-steps">
            <li className={step1 ? 'done' : ''}>
              {step1 ? '✓ ' : ''}{t('config.onboarding.step1')}
            </li>
            <li className={step2 ? 'done' : ''}>
              {step2 ? '✓ ' : ''}{t('config.onboarding.step2')}
            </li>
            <li className={step3 ? 'done' : ''}>
              {step3 ? '✓ ' : ''}
              <Trans
                i18nKey="config.onboarding.step3"
                components={{
                  entities: <Link to="/entidades" />,
                  viz: <Link to="/visualizacion" />,
                }}
              />
            </li>
          </ol>

          {completed === 3 && (
            <p className="onboarding-done">
              {t('config.onboarding.allDone')}
            </p>
          )}
        </>
      )}
    </div>
  )
}
