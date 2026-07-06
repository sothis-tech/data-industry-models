import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { StatusBar } from '../../components/StatusBar'
import type { BrokerHealthState, ModelSummary } from '../../hooks/useAppStatus'
import type { StoredBroker } from '../../types/broker'

const BROKER: StoredBroker = { url: 'http://kong:8000', name: 'Kong Test', tenant: 'qa' }
const MODEL_OK: ModelSummary  = { loaded: true,  label: '3 tipos' }
const MODEL_NONE: ModelSummary = { loaded: false, label: '' }

function renderBar(
  broker: StoredBroker | null,
  health: BrokerHealthState,
  model: ModelSummary,
) {
  return render(
    <MemoryRouter>
      <StatusBar broker={broker} health={health} model={model} />
    </MemoryRouter>,
  )
}

describe('StatusBar', () => {
  describe('sin broker configurado', () => {
    it('muestra "Sin conexión Orion"', () => {
      renderBar(null, 'unknown', MODEL_NONE)
      expect(screen.getByText(/sin conexión orion/i)).toBeTruthy()
    })

    it('ofrece al menos un enlace "Configurar"', () => {
      renderBar(null, 'unknown', MODEL_NONE)
      const links = screen.getAllByRole('link', { name: /configurar/i })
      expect(links.length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('estados de salud del broker', () => {
    it('health=ok → texto "sesión iniciada"', () => {
      renderBar(BROKER, 'ok', MODEL_NONE)
      expect(screen.getByText(/sesión iniciada/i)).toBeTruthy()
    })

    it('health=no-session → texto "sin sesión"', () => {
      renderBar(BROKER, 'no-session', MODEL_NONE)
      expect(screen.getByText(/sin sesión/i)).toBeTruthy()
    })

    it('health=error → texto "estado no disponible"', () => {
      renderBar(BROKER, 'error', MODEL_NONE)
      expect(screen.getByText(/estado no disponible/i)).toBeTruthy()
    })

    it('health=unknown → texto "comprobando sesión"', () => {
      renderBar(BROKER, 'unknown', MODEL_NONE)
      expect(screen.getByText(/comprobando sesión/i)).toBeTruthy()
    })
  })

  describe('nombre del broker', () => {
    it('broker cuyo name empieza por "Kong" muestra "Kong"', () => {
      renderBar(BROKER, 'ok', MODEL_NONE)
      expect(screen.getByText(/Kong:/i)).toBeTruthy()
    })

    it('broker sin nombre "Kong" muestra el nombre real', () => {
      const custom: StoredBroker = { ...BROKER, name: 'Orion Local' }
      renderBar(custom, 'ok', MODEL_NONE)
      expect(screen.getByText(/Orion Local/i)).toBeTruthy()
    })
  })

  describe('estado del modelo', () => {
    it('modelo cargado → muestra el label', () => {
      renderBar(BROKER, 'ok', MODEL_OK)
      expect(screen.getByText(/Modelo: 3 tipos/i)).toBeTruthy()
    })

    it('modelo no cargado → muestra "Modelo no cargado"', () => {
      renderBar(BROKER, 'ok', MODEL_NONE)
      expect(screen.getByText(/Modelo no cargado/i)).toBeTruthy()
    })
  })
})
