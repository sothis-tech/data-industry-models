import { test, expect } from '@playwright/test'

/**
 * Tests E2E de la página de Configuración.
 * No requieren broker real — prueban el comportamiento local de la UI.
 */

test.describe('Configuración — formulario de broker', () => {

  test.beforeEach(async ({ page }) => {
    // Limpiamos localStorage para empezar en estado limpio
    await page.goto('/')
    await page.evaluate(() => localStorage.clear())
    await page.reload()
  })

  test('muestra el formulario para añadir un broker', async ({ page }) => {
    await expect(page.getByLabel(/nombre/i).first()).toBeVisible()
    await expect(page.getByLabel(/url/i).first()).toBeVisible()
  })

  test('el botón Guardar broker está presente', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /guardar|añadir|agregar broker/i })
    ).toBeVisible()
  })

  test('guardar un broker lo muestra en la lista', async ({ page }) => {
    await page.getByLabel(/nombre/i).first().fill('Broker Local')
    await page.getByLabel(/url/i).first().fill('http://localhost:1026')
    await page.getByRole('button', { name: 'Guardar', exact: true }).click()

    await expect(page.locator('.broker-list').getByText('Broker Local', { exact: true })).toBeVisible()
    await expect(page.locator('.broker-list').getByText('http://localhost:1026')).toBeVisible()
  })

  test('eliminar un broker lo quita de la lista', async ({ page }) => {
    // Primero guardamos
    await page.getByLabel(/nombre/i).first().fill('Broker Temp')
    await page.getByLabel(/url/i).first().fill('http://localhost:1026')
    await page.getByRole('button', { name: 'Guardar', exact: true }).click()
    await expect(page.locator('.broker-list').getByText('Broker Temp', { exact: true })).toBeVisible()

    // Ahora eliminamos
    await page.getByRole('button', { name: /eliminar/i }).first().click()
    await expect(page.locator('.broker-list').getByText('Broker Temp', { exact: true })).not.toBeVisible()
  })

  test('los brokers se persisten al recargar la página', async ({ page }) => {
    await page.getByLabel(/nombre/i).first().fill('Broker Persistente')
    await page.getByLabel(/url/i).first().fill('http://broker.example.com:1026')
    await page.getByRole('button', { name: 'Guardar', exact: true }).click()

    await page.reload()
    await expect(page.locator('.broker-list').getByText('Broker Persistente', { exact: true })).toBeVisible()
  })

})

test.describe('Configuración — formulario de modelo', () => {

  test('muestra sección para cargar modelo por URL', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText(/modelo ngsi-ld/i)).toBeVisible()
  })

  test('muestra opción de cargar por paquete ZIP', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText(/zip|paquete/i).first()).toBeVisible()
  })

})
