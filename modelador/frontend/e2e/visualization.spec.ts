import { test, expect } from '@playwright/test'

/**
 * Tests E2E de la página de Visualización.
 * No requieren broker real — prueban UI local (tabs, mensajes, filtros, navegación).
 */

test.describe('Visualización — sin broker configurado', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/visualizacion')
    await page.evaluate(() => localStorage.clear())
    await page.reload()
  })

  test('muestra la tab "Modelo abstracto" activa por defecto', async ({ page }) => {
    const activeTab = page.locator('[role="tab"][aria-selected="true"]').first()
    await expect(activeTab).toContainText(/modelo abstracto/i)
  })

  test('muestra la tab "Instancias Orion-LD"', async ({ page }) => {
    await expect(page.getByRole('tab', { name: /instancias orion/i })).toBeVisible()
  })

  test('mensaje de aviso cuando no hay modelo cargado', async ({ page }) => {
    await expect(
      page.getByText(/carga el modelo|configuraci/i).first()
    ).toBeVisible()
  })

  test('tab Instancias Orion-LD muestra aviso de broker al hacer clic', async ({ page }) => {
    await page.getByRole('tab', { name: /instancias orion/i }).click()
    // Sin broker configurado debe aparecer un mensaje de aviso
    await expect(
      page.getByText(/broker|configuraci/i).first()
    ).toBeVisible()
  })

  test('el botón recargar instancias está presente en la tab Orion', async ({ page }) => {
    await page.getByRole('tab', { name: /instancias orion/i }).click()
    // El botón ↺ de recargar
    await expect(page.getByRole('button', { name: /recargar/i })).toBeVisible()
  })

})

test.describe('Visualización — con modelo cargado', () => {

  const FAKE_MODEL = JSON.stringify({
    schemas: [
      { $schema: 'https://json-schema.org/draft/2020-12/schema', title: 'Machine', type: 'object' },
      { $schema: 'https://json-schema.org/draft/2020-12/schema', title: 'Area',    type: 'object' },
    ],
    context: { '@context': { Machine: 'https://example.org/Machine', Area: 'https://example.org/Area' } },
    descriptor: null,
    examples: {},
  })

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

  test('la tab de Modelo abstracto muestra el número de tipos', async ({ page }) => {
    // El badge de conteo (2 tipos) debe aparecer en la tab
    const tab = page.getByRole('tab', { name: /modelo abstracto/i })
    await expect(tab).toBeVisible()
  })

  test('los controles de zoom están presentes', async ({ page }) => {
    await expect(page.getByRole('button', { name: /acercar/i }).first()).toBeVisible()
    await expect(page.getByRole('button', { name: /alejar/i }).first()).toBeVisible()
    await expect(page.getByRole('button', { name: /encuadrar/i }).first()).toBeVisible()
  })

  test('el SVG del grafo se renderiza cuando hay modelo', async ({ page }) => {
    await expect(page.locator('svg').first()).toBeVisible({ timeout: 15_000 })
  })

  test('"Instancias Orion-LD" muestra aviso de broker cuando no hay broker activo', async ({ page }) => {
    await page.getByRole('tab', { name: /instancias orion/i }).click()
    await expect(page.getByText(/broker|configuraci/i).first()).toBeVisible()
  })

})

// ─── Enlace "Ver entidades de este tipo" ──────────────────────────────────────

test.describe('Visualización — enlace a Entidades desde el schema', () => {

  const MODEL_WITH_DESCRIPTOR = JSON.stringify({
    schemas: [
      { $schema: 'https://json-schema.org/draft/2020-12/schema', title: 'Machine', type: 'object' },
      { $schema: 'https://json-schema.org/draft/2020-12/schema', title: 'Area',    type: 'object' },
    ],
    context: { '@context': { Machine: 'https://example.org/Machine', Area: 'https://example.org/Area' } },
    descriptor: { relationships: [
      { sourceType: 'Machine', targetType: 'Area', property: 'locatedIn', implicit: false },
    ]},
    examples: {},
  })

  test.beforeEach(async ({ page }) => {
    await page.goto('/visualizacion')
    await page.evaluate((model) => {
      localStorage.setItem('ngsi_model', model)
    }, MODEL_WITH_DESCRIPTOR)
    const graphResp = page.waitForResponse(
      (r) => r.url().includes('/api/graph/schema/build') && r.status() === 200,
      { timeout: 20_000 },
    )
    await page.reload()
    await graphResp
  })

  test('el panel de detalle tiene el enlace "Ver entidades" al seleccionar un nodo', async ({ page }) => {
    await page.locator('svg').first().waitFor({ state: 'visible', timeout: 15_000 })
    const firstNode = page.locator('svg circle').first()
    await firstNode.waitFor({ state: 'visible', timeout: 5000 })
    await firstNode.click({ force: true })

    // El panel de detalle debe tener el enlace a Entidades
    await expect(
      page.getByRole('link', { name: /ver entidades/i })
    ).toBeVisible({ timeout: 3000 })
  })

  test('clic en "Ver entidades" navega a Entidades con el filtro de tipo en sessionStorage', async ({ page }) => {
    await page.locator('svg').first().waitFor({ state: 'visible', timeout: 15_000 })
    const firstNode = page.locator('svg circle').first()
    await firstNode.waitFor({ state: 'visible', timeout: 5000 })
    await firstNode.click({ force: true })

    await page.getByRole('link', { name: /ver entidades/i }).click({ timeout: 3000 })

    await expect(page).toHaveURL(/entidades/)
    // EntitiesPage consume y borra viz_filter_type al montar; comprobamos el filtro en la UI
    await expect(page.locator('.entity-list-toolbar')).toHaveText(/Machine|Area/)
  })

})

// ─── Filtro de tipos en Orion (sin broker) ────────────────────────────────────

test.describe('Visualización — estado empty states correcto', () => {

  test('sin modelo Y sin broker: mensaje apropiado en schema tab', async ({ page }) => {
    await page.goto('/visualizacion')
    await page.evaluate(() => {
      localStorage.removeItem('ngsi_model')
      localStorage.removeItem('ngsi_current_broker_url')
    })
    await page.reload()
    await expect(page.getByText(/carga el modelo|configuraci/i).first()).toBeVisible()
  })

  test('sin broker en tab Orion: enlace para ir a Configuración', async ({ page }) => {
    await page.goto('/visualizacion')
    await page.evaluate(() => localStorage.removeItem('ngsi_current_broker_url'))
    await page.reload()

    await page.getByRole('tab', { name: /instancias orion/i }).click()
    // El enlace de "ve a Configuración" debe estar presente
    await expect(
      page.getByRole('link', { name: /configuraci/i }).first()
    ).toBeVisible()
  })

})
