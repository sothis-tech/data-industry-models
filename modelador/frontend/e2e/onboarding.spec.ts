import { test, expect } from '@playwright/test'

/**
 * Tests E2E del progreso de onboarding visible en la StatusBar / pantalla de inicio.
 *
 * Verifica que el indicador de pasos evoluciona según el estado de localStorage
 * (broker configurado → modelo cargado → sesión iniciada).
 *
 * No requieren servicios reales: se usa localStorage + route mocks.
 */

const BROKER = { url: 'http://kong:8000', name: 'Kong QA', tenant: 'qa-tenant' }

const MODEL_2_TIPOS = JSON.stringify({
  schemas: [{ title: 'A' }, { title: 'B' }],
  context: { '@context': {} },
  descriptor: null,
  examples: {},
})

async function seedBroker(page: import('@playwright/test').Page) {
  await page.evaluate(({ url, name, tenant }) => {
    localStorage.setItem('ngsi_current_broker_url', url)
    localStorage.setItem('ngsi_current_broker_name', name)
    localStorage.setItem('ngsi_current_broker_tenant', tenant)
  }, BROKER)
}

async function seedModel(page: import('@playwright/test').Page) {
  await page.evaluate((raw) => {
    localStorage.setItem('ngsi_model', raw)
  }, MODEL_2_TIPOS)
}

function mockOrionLoggedIn(page: import('@playwright/test').Page) {
  return page.route('**/api/auth/orion/status**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ logged_in: true }),
    }),
  )
}

function mockOrionLoggedOut(page: import('@playwright/test').Page) {
  return page.route('**/api/auth/orion/status**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ logged_in: false }),
    }),
  )
}

test.describe('Onboarding — progreso de configuración', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => localStorage.clear())
    await page.reload()
  })

  test('sin configuración la StatusBar muestra "Sin conexión Orion"', async ({ page }) => {
    await mockOrionLoggedOut(page)
    await page.goto('/')
    await expect(page.getByText(/sin conexión orion/i)).toBeVisible()
  })

  test('con broker configurado la StatusBar muestra el nombre', async ({ page }) => {
    await mockOrionLoggedOut(page)
    await seedBroker(page)
    await page.reload()
    // connectionLabel() trunca "Kong QA" → "Kong"; se muestra como "Kong: ..."
    await expect(page.getByText(/Kong:/)).toBeVisible()
  })

  test('con sesión iniciada la StatusBar muestra "sesión iniciada"', async ({ page }) => {
    await mockOrionLoggedIn(page)
    await seedBroker(page)
    await page.reload()
    await expect(page.getByText(/sesión iniciada/i)).toBeVisible()
  })

  test('con modelo cargado la StatusBar muestra el número de tipos', async ({ page }) => {
    await mockOrionLoggedIn(page)
    await seedBroker(page)
    await seedModel(page)
    await page.reload()
    await expect(page.getByText(/modelo: 2 tipos/i)).toBeVisible()
  })

  test('sin modelo la StatusBar muestra "Modelo no cargado"', async ({ page }) => {
    await mockOrionLoggedIn(page)
    await seedBroker(page)
    await page.reload()
    await expect(page.getByText(/modelo no cargado/i)).toBeVisible()
  })

  test('sin sesión la StatusBar muestra "sin sesión"', async ({ page }) => {
    await mockOrionLoggedOut(page)
    await seedBroker(page)
    await page.reload()
    await expect(page.getByText(/sin sesión/i)).toBeVisible()
  })

})
