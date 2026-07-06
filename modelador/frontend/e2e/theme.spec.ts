import { test, expect } from '@playwright/test'

const THEME_STORAGE_KEY = 'inn-modelador-theme'
const LABEL_PLACEMENT_KEY = 'inn-viz-graph-label-placement'

test.describe('Tema claro/oscuro', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => localStorage.clear())
    await page.reload()
  })

  test('usa tema claro por defecto sin preferencia guardada', async ({ page }) => {
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  })

  test('cambia a tema oscuro y persiste al recargar', async ({ page }) => {
    await page.getByRole('button', { name: 'Cambiar a tema oscuro' }).click()

    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')

    const stored = await page.evaluate((key) => localStorage.getItem(key), THEME_STORAGE_KEY)
    expect(stored).toBe('dark')

    await page.reload()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await expect(page.getByRole('button', { name: 'Cambiar a tema claro' })).toBeVisible()
  })

  test('vuelve a tema claro al pulsar de nuevo', async ({ page }) => {
    await page.getByRole('button', { name: 'Cambiar a tema oscuro' }).click()
    await page.getByRole('button', { name: 'Cambiar a tema claro' }).click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  })
})

test.describe('Visualización — etiquetas del grafo por defecto', () => {
  const FAKE_MODEL = JSON.stringify({
    schemas: [
      { $schema: 'https://json-schema.org/draft/2020-12/schema', title: 'Machine', type: 'object' },
    ],
    context: { '@context': { Machine: 'https://example.org/Machine' } },
    descriptor: null,
    examples: {},
  })

  test('etiquetas debajo del nodo (botón Aa inactivo) sin preferencia guardada', async ({ page }) => {
    await page.goto('/visualizacion')
    await page.evaluate((model) => {
      localStorage.clear()
      localStorage.setItem('ngsi_model', model)
    }, FAKE_MODEL)

    const graphResp = page.waitForResponse(
      (r) => r.url().includes('/api/graph/schema/build') && r.status() === 200,
      { timeout: 20_000 },
    )
    await page.reload()
    await graphResp

    const placement = await page.evaluate((key) => localStorage.getItem(key), LABEL_PLACEMENT_KEY)
    expect(placement).toBeNull()

    const aaButton = page.getByRole('button', { name: 'Mostrar nombres dentro del nodo' })
    await expect(aaButton).toBeVisible()
    await expect(aaButton).toHaveAttribute('aria-pressed', 'false')
  })
})
