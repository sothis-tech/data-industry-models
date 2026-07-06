import { useRef, useState } from 'react'
import { NavLink, Outlet, Route, Routes } from 'react-router-dom'
import { AgentPanel } from './components/AgentPanel'
import { StatusBar } from './components/StatusBar'
import { ThemeToggle } from './components/ThemeToggle'
import { useAppStatus } from './hooks/useAppStatus'
import { ConfigPage } from './pages/config/ConfigPage'
import { EntitiesPage } from './pages/entities/EntitiesPage'
import { VisualizationPage } from './pages/viz/VisualizationPage'

function Layout() {
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
        <h1>INN Data Space Modelador</h1>
        <ThemeToggle />
      </header>
      <nav className="tabs">
        <NavLink to="/" end>
          Configuración
        </NavLink>
        <NavLink to="/entidades">Entidades</NavLink>
        <NavLink to="/visualizacion">Visualización</NavLink>
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
