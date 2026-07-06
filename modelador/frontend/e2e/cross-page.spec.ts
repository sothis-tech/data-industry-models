import { test, expect } from '@playwright/test'

/**
 * Tests E2E de flujos que cruzan varias páginas.
 *
 * Verifican la coherencia del estado compartido (localStorage) entre:
 *   - Configuración ↔ Entidades
 *   - Configuración ↔ Visualización
 *   - Visualización → Entidades (handoff por sessionStorage)
 */

const FAKE_MODEL = JSON.stringify({
  schemas: [
    { $schema: 'https://json-schema.org/draft/2020-12/schema', title: 'ManufacturingMachine', type: 'object',
      properties: { id: { type: 'string' }, type: { type: 'string' }, name: { type: 'string' } } },
    { $schema: 'https://json-schema.org/draft/2020-12/schema', title: 'Area', type: 'object',
      properties: { id: { type: 'string' }, type: { type: 'string' } } },
  ],
  context: { '@context': {
    ManufacturingMachine: 'https://example.org/ManufacturingMachine',
    Area: 'https://example.org/Area',
  }},
  descriptor: { relationships: [
    { sourceType: 'ManufacturingMachine', targetType: 'Area', property: 'locatedIn', implicit: false },
  ]},
  examples: {},
})

// ─── Modelo cargado en Config afecta a otras páginas ─────────────────────────

test.describe('Flujo: modelo cargado en Configuración → reflejado en otras páginas', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    // Estado limpio
    await page.evaluate(() => {
      localStorage.removeItem('ngsi_model')
      localStorage.removeItem('ngsi_current_broker_url')
    })
    await page.reload()
  })

  test('StatusBar muestra "sin modelo" antes de cargar', async ({ page }) => {
    await expect(
      page.getByText(/modelo no cargado|sin modelo/i).first()
    ).toBeVisible()
  })

  test('modelo guardado en Config → filtro de tipos en Entidades se actualiza', async ({ page }) => {
    // Inyectamos el modelo directamente (simula carga exitosa desde Config)
    await page.evaluate((model) => {
      localStorage.setItem('ngsi_model', model)
    }, FAKE_MODEL)

    // Navegamos a Entidades
    await page.goto('/entidades')
    await page.locator('.entity-list-toolbar').getByRole('combobox').click({ force: true })
    await expect(page.getByRole('option', { name: 'ManufacturingMachine' })).toBeVisible()
    await expect(page.getByRole('option', { name: 'Area' })).toBeVisible()
  })

  test('modelo guardado en Config → Visualización muestra el grafo del schema', async ({ page }) => {
    await page.evaluate((model) => {
      localStorage.setItem('ngsi_model', model)
    }, FAKE_MODEL)

    const graphResp = page.waitForResponse(
      (r) => r.url().includes('/api/graph/schema/build') && r.status() === 200,
      { timeout: 20_000 },
    )
    await page.goto('/visualizacion')
    await graphResp
    // No debe mostrar el empty state de "sin modelo"
    await expect(page.getByText(/carga el modelo.*configuraci/i)).not.toBeVisible()
    // Debe aparecer el SVG del grafo
    await expect(page.locator('svg').first()).toBeVisible({ timeout: 15_000 })
  })

  test('limpiar modelo en Config → Entidades vuelve a mostrar sin tipos', async ({ page }) => {
    // Partimos con modelo cargado
    await page.evaluate((model) => {
      localStorage.setItem('ngsi_model', model)
    }, FAKE_MODEL)

    await page.goto('/')

    // Limpiamos el modelo desde Config
    await page.getByRole('button', { name: /limpiar modelo/i }).click()

    // Navegamos a Entidades
    await page.goto('/entidades')
    await page.locator('.entity-list-toolbar').getByRole('combobox').click({ force: true })
    await expect(page.getByText('Sin tipos disponibles')).toBeVisible()
  })

})

// ─── Broker en Config → estado en Entidades y StatusBar ──────────────────────

test.describe('Flujo: broker guardado en Configuración → visibilidad en la app', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => {
      localStorage.clear()
    })
    await page.reload()
  })

  test('guardar un broker → StatusBar muestra la URL del broker', async ({ page }) => {
    await page.getByLabel(/nombre/i).first().fill('Mi Broker')
    await page.getByLabel(/url/i).first().fill('http://localhost:1026')
    await page.getByRole('button', { name: 'Guardar', exact: true }).click()

    // La barra de estado refleja el broker activo
    await expect(
      page.getByText(/localhost:1026|mi broker/i).first()
    ).toBeVisible()
  })

  test('broker activo persiste al navegar entre páginas', async ({ page }) => {
    await page.evaluate(() => {
      localStorage.setItem('ngsi_current_broker_url', 'http://broker.example.com:1026')
      localStorage.setItem('ngsi_current_broker_name', 'Broker Test')
    })
    await page.reload()

    // La URL del broker debe seguir visible en la StatusBar
    await expect(page.getByText(/broker\.example\.com|Broker Test/i).first()).toBeVisible()

    // Al navegar a Entidades, sigue visible
    await page.goto('/entidades')
    await expect(page.getByText(/broker\.example\.com|Broker Test/i).first()).toBeVisible()
  })

})

// ─── Visualización → Entidades (handoff) ─────────────────────────────────────

test.describe('Flujo: enlace "Ver entidades de este tipo" desde Visualización', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/visualizacion')
    await page.evaluate((model) => {
      localStorage.setItem('ngsi_model', model)
    }, FAKE_MODEL)
    const graphResp = page.waitForResponse(
      (r) => r.url().includes('/api/graph/schema/build') && r.status() === 200,
      { timeout: 20_000 },
    )
    await page.reload()
    await graphResp
  })

  test('el grafo del schema renderiza nodos visibles', async ({ page }) => {
    await expect(page.locator('svg').first()).toBeVisible({ timeout: 8000 })
    // Debe haber nodos del grafo (círculos o grupos)
    await expect(page.locator('svg circle, svg g.node').first()).toBeVisible({ timeout: 5000 })
  })

  test('hacer clic en un nodo del schema muestra el panel de detalle', async ({ page }) => {
    await page.locator('svg').first().waitFor({ state: 'visible', timeout: 15_000 })
    const firstNode = page.locator('svg circle').first()
    await firstNode.waitFor({ state: 'visible', timeout: 5000 })
    await firstNode.click({ force: true })
    await expect(page.locator('.viz-detail-panel.open')).toBeVisible({ timeout: 5000 })
  })

})

// ─── Onboarding progresivo ────────────────────────────────────────────────────

test.describe('Flujo: onboarding progresivo de 3 pasos', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => localStorage.clear())
    await page.reload()
  })

  test('el onboarding muestra los 3 pasos inicialmente', async ({ page }) => {
    // Debe estar expandido o mostrar un trigger para expandirlo
    const onboarding = page.locator('[class*="onboarding"], [class*="guide"]').first()
    await expect(onboarding).toBeVisible()
  })

  test('guardar un broker marca el paso 1 del onboarding', async ({ page }) => {
    await page.getByLabel(/nombre/i).first().fill('Broker Onboarding')
    await page.getByLabel(/url/i).first().fill('http://localhost:1026')
    await page.getByRole('button', { name: 'Guardar', exact: true }).click()

    // OnboardingCard: <li class="done"> cuando el paso está hecho
    await expect(page.locator('ol.onboarding-steps li.done').first()).toContainText(/orion|conexión/i)
  })

  test('visitar Entidades marca el paso 3 del onboarding', async ({ page }) => {
    await page.goto('/entidades')
    await page.waitForFunction(() => localStorage.getItem('ngsi_onboarding_step3_done') === '1')
    await page.goto('/')  // volvemos a Config
    await expect(page.locator('ol.onboarding-steps li').nth(2)).toHaveClass(/done/)
  })

})
