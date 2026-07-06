import { test, expect } from '@playwright/test'
import { ORION_SESSION_LOST } from '../src/lib/orionSessionEvents'

/**
 * Sesión Orion (BFF /api/auth/orion/status) y coherencia UI:
 * StatusBar, Marvin y RAG comparten health === 'ok'.
 *
 * No requiere Keycloak real: se intercepta el endpoint de estado.
 */

const BROKER = {
  url: 'http://kong:8000',
  name: 'Kong QA',
  tenant: 'qa-tenant',
}

const RAG_CONFIG = {
  enabled: true,
  max_mb: 20,
  allowed_extensions: ['.pdf', '.txt', '.md'],
  chroma_db: 'default',
}

async function seedBroker(page: import('@playwright/test').Page) {
  await page.evaluate(
    ({ url, name, tenant }) => {
      localStorage.setItem('ngsi_current_broker_url', url)
      localStorage.setItem('ngsi_current_broker_name', name)
      localStorage.setItem('ngsi_current_broker_tenant', tenant)
    },
    BROKER,
  )
}

function mockOrionStatus(page: import('@playwright/test').Page, loggedIn: boolean) {
  return page.route('**/api/auth/orion/status**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ logged_in: loggedIn }),
    })
  })
}

function mockChatConfig(page: import('@playwright/test').Page) {
  return page.route('**/api/chat/config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ aea_ws_url: '', text_chat_enabled: true }),
    })
  })
}

/** Retardo para que la UI muestre isSending (textarea disabled + typing dots) antes de resolver. */
function mockChatText(page: import('@playwright/test').Page, delayMs = 800) {
  return page.route('**/api/chat/text', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue()
      return
    }
    await new Promise((resolve) => setTimeout(resolve, delayMs))
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 200,
        body: { text: 'Respuesta de prueba E2E', session_id: 'e2e-session' },
        error: null,
      }),
    })
  })
}

function mockRagConfig(page: import('@playwright/test').Page) {
  return page.route('**/api/rag/config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(RAG_CONFIG),
    })
  })
}

/** Rail único; al abrir hay dos botones «Cerrar panel de Marvin». */
async function openMarvinPanel(page: import('@playwright/test').Page) {
  await page.locator('button.agent-panel-rail').click()
  await expect(page.locator('.agent-panel--open')).toBeVisible()
}

function marvinTextarea(page: import('@playwright/test').Page) {
  return page.locator('.agent-panel--open').getByRole('textbox', { name: /mensaje para marvin/i })
}

/** Rail único; al abrir hay dos botones «Cerrar panel RAG». */
async function openRagSidebar(page: import('@playwright/test').Page) {
  await page.locator('button.rag-sidebar-rail').click()
  await expect(page.locator('.rag-sidebar--open')).toBeVisible()
}

function ragPanelBody(page: import('@playwright/test').Page) {
  return page.locator('.rag-sidebar--open .rag-sidebar-body')
}

test.describe('Sesión Orion — UI bloqueada sin sesión', () => {
  test.beforeEach(async ({ page }) => {
    await mockOrionStatus(page, false)
    await mockChatConfig(page)
    await mockRagConfig(page)
    await page.goto('/')
    await seedBroker(page)
    await page.reload()
    await expect(page.getByText(/sin sesión/i).first()).toBeVisible({ timeout: 15_000 })
  })

  test('StatusBar indica sin sesión con broker activo', async ({ page }) => {
    await expect(page.getByText(/sin sesión/i).first()).toBeVisible()
    await expect(page.locator('.status-bar')).toContainText(/Kong/i)
  })

  test('Marvin: input deshabilitado y aviso de conectar Orion', async ({ page }) => {
    await openMarvinPanel(page)
    const input = marvinTextarea(page)
    await expect(input).toBeDisabled()
    await expect(input).toHaveAttribute('placeholder', /conecta orion/i)
    await expect(page.getByText(/conecta orion para acceder a marvin/i)).toBeVisible()
  })

  test('RAG: panel muestra sesión requerida', async ({ page }) => {
    await openRagSidebar(page)
    const body = ragPanelBody(page)
    await expect(body.getByText('Sesión Orion requerida')).toBeVisible()
    await expect(body.getByText(/iniciar sesión primero en la conexión orion/i)).toBeVisible()
  })
})

test.describe('Sesión Orion — UI habilitada con sesión', () => {
  test.beforeEach(async ({ page }) => {
    await mockOrionStatus(page, true)
    await mockChatConfig(page)
    await mockRagConfig(page)
    await page.goto('/')
    await seedBroker(page)
    await page.reload()
    await expect(page.getByText(/sesión iniciada/i).first()).toBeVisible({ timeout: 15_000 })
  })

  test('StatusBar indica sesión iniciada', async ({ page }) => {
    await expect(page.getByText(/sesión iniciada/i).first()).toBeVisible()
    await expect(page.locator('.status-bar')).toContainText(/Kong/i)
  })

  test('Marvin: input habilitado cuando hay sesión y chat configurado', async ({ page }) => {
    await openMarvinPanel(page)
    const input = marvinTextarea(page)
    await expect(input).toBeEnabled()
    await expect(input).toHaveAttribute('placeholder', /pregúntale a marvin/i)
  })

  test('Marvin: recupera el foco del textarea tras enviar mensaje', async ({ page }) => {
    await mockChatText(page)
    await openMarvinPanel(page)
    const input = marvinTextarea(page)
    await expect(input).toBeEnabled()

    await input.fill('Hola Marvin')
    const chatResponse = page.waitForResponse(
      (res) => res.url().includes('/api/chat/text') && res.request().method() === 'POST',
    )
    await input.press('Enter')

    await expect(page.locator('.chatbot-message--typing')).toBeVisible()
    await expect(input).toBeDisabled()
    await chatResponse
    await expect(page.getByText('Respuesta de prueba E2E')).toBeVisible({ timeout: 15_000 })
    await expect(input).toBeEnabled()
    await expect(input).toBeFocused()
  })

  test('RAG: no muestra bloqueo por sesión (puede fallar por servicio RAG caído)', async ({ page }) => {
    await openRagSidebar(page)
    await expect(ragPanelBody(page).getByText('Sesión Orion requerida')).toHaveCount(0)
  })
})

test.describe('Sesión Orion — pérdida de sesión en caliente', () => {
  test('evento ORION_SESSION_LOST bloquea Marvin sin recargar', async ({ page }) => {
    await mockOrionStatus(page, true)
    await mockChatConfig(page)
    await mockRagConfig(page)
    await page.goto('/')
    await seedBroker(page)
    await page.reload()
    await expect(page.getByText(/sesión iniciada/i).first()).toBeVisible({ timeout: 15_000 })

    await openMarvinPanel(page)
    const input = marvinTextarea(page)
    await expect(input).toBeEnabled()

    await page.evaluate((eventName) => {
      window.dispatchEvent(new CustomEvent(eventName))
    }, ORION_SESSION_LOST)

    await expect(page.getByText(/sin sesión/i).first()).toBeVisible()
    await expect(input).toBeDisabled()
    await expect(page.getByText(/conecta orion para acceder a marvin/i)).toBeVisible()
  })
})
