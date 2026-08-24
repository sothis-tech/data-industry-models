import { useRef, useState } from 'react'
import { NavLink, Outlet, Route, Routes } from 'react-router-dom'
import { AgentPanel } from './components/AgentPanel'
import { StatusBar } from './components/StatusBar'
import { ThemeToggle } from './components/ThemeToggle'
import { useAppStatus } from './hooks/useAppStatus'
import { ConfigPage } from './pages/config/ConfigPage'
import { EntitiesPage } from './pages/entities/EntitiesPage'
import { VisualizationPage } from './pages/viz/VisualizationPage'
import { useTranslation } from 'react-i18next'
import { LanguageSelector } from './components/LanguageSelector'

function Layout() {
  const { t } = useTranslation()
  // refreshKey se incrementa desde páginas hijas para forzar re-lectura de
  // localStorage en StatusBar y OnboardingCard sin prop drilling profundo.
  const [refreshKey, setRefreshKey] = useState(0)
  const appBodyRef = useRef<HTMLDivElement>(null)
  const { broker, health, model } = useAppStatus(refreshKey)

  function triggerRefresh() {
    setRefreshKey((k) => k + 1)
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <h1>{t('app.title')}</h1>
	<LanguageSelector />
        <ThemeToggle />
      </header>
      <nav className="tabs">
        <NavLink to="/" end>
          {t('nav.config')}
        </NavLink>
        <NavLink to="/entidades">{t('nav.entities')}</NavLink>
        <NavLink to="/visualizacion">{t('nav.visualization')}</NavLink>
      </nav>
      <StatusBar broker={broker} health={health} model={model} />
      <div className="app-body" ref={appBodyRef}>
        <main>
          <Outlet context={{ broker, health, refreshKey, triggerRefresh }} />
        </main>
        <AgentPanel
          bodyRef={appBodyRef}
          broker={broker}
          isOrionAuthenticated={health === 'ok'}
        />
      </div>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<ConfigPage />} />
        <Route path="/entidades" element={<EntitiesPage />} />
        <Route path="/visualizacion" element={<VisualizationPage />} />
      </Route>
    </Routes>
  )
}
