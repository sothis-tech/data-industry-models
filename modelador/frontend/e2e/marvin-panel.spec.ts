import { test, expect } from '@playwright/test'

/**
 * Tests E2E del panel lateral de Marvin.
 *
 * Verifica que el panel se abre, se puede cerrar y que el textarea
 * refleja correctamente el estado de autenticación Orion.
 *
 * No requieren servicios LLM reales — se interceptan las llamadas API.
 */

const BROKER = { url: 'http://kong:8000', name: 'Kong QA', tenant: 'qa-tenant' }

async function seedBroker(page: import('@playwright/test').Page) {
  await page.evaluate(({ url, name, tenant }) => {
    localStorage.setItem('ngsi_current_broker_url', url)
    localStorage.setItem('ngsi_current_broker_name', name)
    localStorage.setItem('ngsi_current_broker_tenant', tenant)
  }, BROKER)
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

function mockChatConfig(page: import('@playwright/test').Page) {
  return page.route('**/api/chat/config', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ aea_ws_url: '', text_chat_enabled: true }),
    }),
  )
}

test.describe('Marvin — panel lateral', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => localStorage.clear())
    await page.reload()
  })

  test('el botón de Marvin abre el panel', async ({ page }) => {
    await mockOrionLoggedIn(page)
    await mockChatConfig(page)
    await seedBroker(page)
    await page.goto('/entidades')

    const toggleBtn = page.getByRole('button', { name: /abrir panel de marvin/i })
    await expect(toggleBtn).toBeVisible()
    await toggleBtn.click()

    await expect(page.getByRole('textbox', { name: /mensaje para marvin/i })).toBeVisible()
  })

  test('el panel se puede cerrar', async ({ page }) => {
    await mockOrionLoggedIn(page)
    await mockChatConfig(page)
    await seedBroker(page)
    await page.goto('/entidades')

    await page.getByRole('button', { name: /abrir panel de marvin/i }).click()

    const input = page.getByRole('textbox', { name: /mensaje para marvin/i })
    await expect(input).toBeVisible()

    await page.getByRole('button', { name: /cerrar panel de marvin/i }).first().click()
    await expect(input).not.toBeVisible()
  })

  test('sin sesión Orion el textarea muestra placeholder de bloqueo', async ({ page }) => {
    await mockOrionLoggedOut(page)
    await mockChatConfig(page)
    await seedBroker(page)
    await page.goto('/entidades')

    await page.getByRole('button', { name: /abrir panel de marvin/i }).click()

    const input = page.getByRole('textbox', { name: /mensaje para marvin/i })
    await expect(input).toBeVisible()
    await expect(input).toBeDisabled()
    await expect(input).toHaveAttribute('placeholder', /conecta orion/i)
  })

  test('con sesión Orion el textarea está habilitado', async ({ page }) => {
    await mockOrionLoggedIn(page)
    await mockChatConfig(page)
    await seedBroker(page)
    await page.reload()
    // Confirmar sesión antes de abrir el panel (el panel está disponible desde /)
    await expect(page.getByText(/sesión iniciada/i)).toBeVisible()

    await page.getByRole('button', { name: /abrir panel de marvin/i }).click()

    const input = page.getByRole('textbox', { name: /mensaje para marvin/i })
    await expect(input).toBeEnabled()
  })

  test('el mensaje de bienvenida de Marvin es visible al abrir el panel', async ({ page }) => {
    await mockOrionLoggedIn(page)
    await mockChatConfig(page)
    await seedBroker(page)
    await page.goto('/entidades')

    await page.getByRole('button', { name: /abrir panel de marvin/i }).click()

    await expect(page.getByText(/¡hola! soy marvin/i)).toBeVisible()
  })

})
