import { test, expect } from '@playwright/test'

/**
 * Integración con Orion-LD real. No se ejecutan en CI por defecto.
 *
 * Requisitos:
 *   - Orion accesible (por defecto http://localhost:1026)
 *   - Backend FastAPI en :8000 (Playwright ya lo arranca con webServer)
 *
 * Ejecutar siempre desde la carpeta frontend/ (mismo `playwright.config.ts` y `@playwright/test` que el proyecto):
 *   PowerShell:  cd frontend; $env:ORION_E2E='1'; npm run test:e2e:orion
 *   bash:        cd frontend && ORION_E2E=1 npm run test:e2e:orion
 *   (Desde la raíz del repo, `npx playwright` suele usar otro binario y falla al registrar los tests.)
 *
 * Opcional: ORION_E2E_URL=https://otro:1026
 */

const ORION_URL = (process.env.ORION_E2E_URL ?? 'http://localhost:1026').replace(/\/$/, '')

/** Modelo mínimo: un solo tipo para crear/borrar entidad de prueba */
const MIN_MODEL = JSON.stringify({
  schemas: [
    {
      $schema: 'https://json-schema.org/draft/2020-12/schema',
      title: 'E2EThing',
      type: 'object',
      properties: {
        id: { type: 'string' },
        type: { type: 'string' },
      },
      required: ['id', 'type'],
    },
  ],
  context: { '@context': { E2EThing: 'https://uri.etsi.org/ngsi-ld/default-context/E2EThing' } },
  descriptor: null,
  examples: {},
})

function seedOrionState(page: import('@playwright/test').Page) {
  return page.evaluate(
    ({ brokerUrl, model }) => {
      localStorage.clear()
      localStorage.setItem('ngsi_model', model)
      localStorage.setItem('ngsi_current_broker_url', brokerUrl)
      localStorage.setItem('ngsi_current_broker_name', 'Orion E2E')
    },
    { brokerUrl: ORION_URL, model: MIN_MODEL },
  )
}

test.describe('Orion-LD real (ORION_E2E=1; ORION_E2E_URL opcional, por defecto :1026)', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(
      process.env.ORION_E2E !== '1',
      'Definir ORION_E2E=1 y tener Orion en ORION_E2E_URL (por defecto :1026)',
    )
    await page.goto('/')
    await seedOrionState(page)
    await page.reload()
  })

  test('Config: Comprobar conectividad con Orion', async ({ page }) => {
    await page.getByLabel(/url/i).first().fill(ORION_URL)
    await page.getByRole('button', { name: /comprobar/i }).click()
    await expect(
      page.getByText(/broker accesible|accesible/i).first(),
    ).toBeVisible({ timeout: 45_000 })
  })

  test('Entidades: petición al proxy de listado responde OK', async ({ page }) => {
    await page.goto('/entidades')
    const res = await page.waitForResponse(
      (r) =>
        r.url().includes('/api/proxy/entities') &&
        r.request().method() === 'GET' &&
        !r.url().includes('/attrs'),
      { timeout: 45_000 },
    )
    expect(res.ok(), `Listado entidades HTTP ${res.status()}`).toBeTruthy()
    await expect(page.getByRole('button', { name: /nueva entidad/i })).toBeVisible()
  })

  test('Visualización: tab Instancias Orion carga sin error de conexión', async ({ page }) => {
    const graphWait = page.waitForResponse(
      (r) => r.url().includes('/api/graph/schema/build') && r.ok(),
      { timeout: 30_000 },
    )
    await page.goto('/visualizacion')
    await graphWait.catch(() => {})
    await page.getByRole('tab', { name: /instancias orion/i }).click()
    await page.getByRole('button', { name: /recargar instancias/i }).click()
    await page.waitForResponse(
      (r) =>
        r.url().includes('/api/proxy/entities') &&
        r.request().method() === 'GET' &&
        !r.url().includes('/attrs'),
      { timeout: 45_000 },
    )
    // No usar getByRole('tabpanel').nth(1): con la pestaña Orion activa el panel de esquema
    // tiene display:none y suele excluirse del árbol de accesibilidad, así que solo hay un
    // tabpanel “visible” y nth(1) no existe. El orden en DOM es siempre esquema → Orion.
    const orionPanel = page.locator('.viz-page > .viz-panel[role="tabpanel"]').nth(1)
    await expect(orionPanel.getByText(/error al conectar con el broker/i)).toHaveCount(0)
    const statusBar = orionPanel.locator('.viz-status-bar')
    const emptyBroker = orionPanel.getByText('No hay entidades en el broker.')
    const emptyFiltered = orionPanel.getByText('No hay nodos para los tipos seleccionados.')
    await expect(statusBar.or(emptyBroker).or(emptyFiltered)).toBeVisible({ timeout: 15_000 })
  })

  test('Crear entidad E2EThing y eliminarla', async ({ page }) => {
    const uniqueId = `urn:ngsi-ld:E2EThing:e2e-${Date.now()}`

    await page.goto('/entidades')
    await page.getByRole('button', { name: /nueva entidad/i }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.locator('#create-type-select').selectOption('E2EThing')
    await page.getByRole('button', { name: /continuar/i }).click()

    const ta = page.locator('#create-json')
    await expect(ta).toBeVisible()
    const raw = await ta.inputValue()
    const obj = JSON.parse(raw) as Record<string, unknown>
    obj.id = uniqueId
    await ta.fill(JSON.stringify(obj, null, 2))

    const postWait = page.waitForResponse(
      (r) =>
        r.url().includes('/api/proxy/entities') &&
        r.request().method() === 'POST',
      { timeout: 60_000 },
    )
    await page.getByRole('button', { name: /crear entidad/i }).click()
    const postRes = await postWait
    expect(
      postRes.ok(),
      `POST entidad falló: ${postRes.status()} ${await postRes.text().catch(() => '')}`,
    ).toBeTruthy()

    await expect(page.getByRole('button', { name: /guardar cambios/i })).toBeVisible({
      timeout: 30_000,
    })

    await page.getByRole('button', { name: /eliminar entidad/i }).click()
    const delDialog = page.getByRole('dialog').filter({ hasText: /eliminar entidad/i })
    await expect(delDialog).toBeVisible()
    const delWait = page.waitForResponse(
      (r) => r.request().method() === 'DELETE' && r.url().includes('/api/proxy/entities'),
      { timeout: 45_000 },
    )
    await delDialog.getByRole('button', { name: /^Eliminar$/ }).click()
    const delRes = await delWait
    expect(delRes.ok() || delRes.status() === 204, `DELETE ${delRes.status()}`).toBeTruthy()
  })
})

