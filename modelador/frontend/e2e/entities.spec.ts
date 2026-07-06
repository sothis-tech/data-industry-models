import { test, expect } from '@playwright/test'

/**
 * Tests E2E de la página de Entidades.
 *
 * Estos tests no requieren Orion-LD real. Verifican comportamiento de UI:
 * estado sin broker, filtros, búsqueda, panel de creación.
 */

const FAKE_MODEL = JSON.stringify({
  schemas: [
    { $schema: 'https://json-schema.org/draft/2020-12/schema', title: 'ManufacturingMachine', type: 'object',
      properties: { id: { type: 'string' }, type: { type: 'string' }, name: { type: 'string' } } },
    { $schema: 'https://json-schema.org/draft/2020-12/schema', title: 'Area', type: 'object',
      properties: { id: { type: 'string' }, type: { type: 'string' } } },
    { $schema: 'https://json-schema.org/draft/2020-12/schema', title: 'Device', type: 'object',
      properties: { id: { type: 'string' }, type: { type: 'string' } } },
  ],
  context: { '@context': {
    ManufacturingMachine: 'https://example.org/ManufacturingMachine',
    Area: 'https://example.org/Area',
    Device: 'https://example.org/Device',
  }},
  descriptor: null,
  examples: {},
})

// ─── Sin broker configurado ───────────────────────────────────────────────────

test.describe('Entidades — sin broker configurado', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/entidades')
    await page.evaluate(() => {
      localStorage.removeItem('ngsi_current_broker_url')
      localStorage.removeItem('ngsi_current_broker_name')
    })
    await page.reload()
  })

  test('muestra mensaje de aviso cuando no hay broker', async ({ page }) => {
    await expect(
      page.getByText(/broker|configuraci/i).first()
    ).toBeVisible()
  })

  test('el botón "Nueva entidad" está presente', async ({ page }) => {
    await expect(page.getByRole('button', { name: /nueva entidad/i })).toBeVisible()
  })

})

// ─── Con modelo cargado — filtros y tipos ────────────────────────────────────

test.describe('Entidades — filtros con modelo cargado', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/entidades')
    await page.evaluate((model) => {
      localStorage.setItem('ngsi_model', model)
    }, FAKE_MODEL)
    await page.reload()
  })

  test('el filtro de tipos muestra los tipos del modelo', async ({ page }) => {
    const combo = page.locator('.entity-list-toolbar').getByRole('combobox')
    await expect(combo).toBeVisible()
    await combo.click({ force: true })
    await expect(page.getByRole('option', { name: 'ManufacturingMachine' })).toBeVisible()
    await expect(page.getByRole('option', { name: 'Area' })).toBeVisible()
    await expect(page.getByRole('option', { name: 'Device' })).toBeVisible()
  })

  test('al seleccionar un tipo se actualiza el filtro activo', async ({ page }) => {
    const combo = page.locator('.entity-list-toolbar').getByRole('combobox')
    await combo.click({ force: true })
    await page.getByRole('option', { name: 'Area' }).click()
    await expect(page.locator('.entity-list-toolbar')).toContainText('Area')
  })

  test('la búsqueda por texto muestra el campo correspondiente', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/buscar|search/i).first()
    await expect(searchInput).toBeVisible()
    await searchInput.fill('test-query')
    await expect(searchInput).toHaveValue('test-query')
  })

})

// ─── Panel de creación — SelectTypeModal ─────────────────────────────────────

test.describe('Entidades — creación y SelectTypeModal', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/entidades')
    await page.evaluate((model) => {
      localStorage.setItem('ngsi_model', model)
      // Broker necesario para abrir el panel de creación tras el modal
      localStorage.setItem('ngsi_current_broker_url', 'http://localhost:1026')
      localStorage.setItem('ngsi_current_broker_name', 'E2E Orion')
    }, FAKE_MODEL)
    await page.reload()
  })

  test('clic en "Nueva entidad" sin filtro de tipo abre el modal de selección', async ({ page }) => {
    await page.getByRole('button', { name: /nueva entidad/i }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.locator('#create-type-select option[value="ManufacturingMachine"]')).toBeAttached()
  })

  test('el modal de selección tiene un botón Cancelar', async ({ page }) => {
    await page.getByRole('button', { name: /nueva entidad/i }).click()
    await expect(page.getByRole('button', { name: /cancelar/i })).toBeVisible()
  })

  test('cancelar el modal de selección no abre el panel', async ({ page }) => {
    await page.getByRole('button', { name: /nueva entidad/i }).click()
    await page.getByRole('button', { name: /cancelar/i }).click()
    await expect(page.getByRole('dialog')).not.toBeVisible()
  })

  test('seleccionar un tipo en el modal abre el panel de creación', async ({ page }) => {
    await page.getByRole('button', { name: /nueva entidad/i }).click()
    await page.locator('#create-type-select').selectOption('ManufacturingMachine')
    await page.getByRole('button', { name: /continuar/i }).click()
    await expect(page.locator('textarea#create-json')).toBeVisible()
  })

  test('"Nueva entidad" sin modelo y sin broker muestra alert de no hay tipos', async ({ page }) => {
    // Modelo sin types
    await page.evaluate(() => localStorage.removeItem('ngsi_model'))
    await page.reload()
    page.on('dialog', async dialog => {
      expect(dialog.message()).toContain('modelo')
      await dialog.accept()
    })
    await page.getByRole('button', { name: /nueva entidad/i }).click()
  })

})

// ─── Handoff desde Visualización ─────────────────────────────────────────────

test.describe('Entidades — handoff desde Visualización', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/entidades')
    await page.evaluate((model) => {
      localStorage.setItem('ngsi_model', model)
    }, FAKE_MODEL)
  })

  test('llegando con viz_filter_type en sessionStorage aplica el filtro de tipo', async ({ page }) => {
    await page.evaluate(() => {
      sessionStorage.setItem('viz_filter_type', 'Area')
    })
    await page.reload()
    await expect(page.locator('.entity-list-toolbar')).toContainText('Area')
  })

  test('sin viz_filter_type en sessionStorage no aplica ningún filtro previo', async ({ page }) => {
    await page.evaluate(() => {
      sessionStorage.removeItem('viz_filter_type')
      sessionStorage.removeItem('viz_select_id')
    })
    await page.reload()
    await expect(page.locator('.entity-list-toolbar').getByText(/todos los tipos/i)).toBeVisible()
  })

})
