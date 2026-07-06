import { test, expect } from '@playwright/test'

/**
 * Tests E2E de navegación básica — no requieren broker real.
 * Verifican que la SPA carga y el routing entre páginas funciona.
 */

test.describe('Navegación entre páginas', () => {

  test('la página de inicio carga con el título de la aplicación', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/modelador/i)
  })

  test('la tab "Configuración" está activa por defecto', async ({ page }) => {
    await page.goto('/')
    // Navegación principal: <nav class="tabs"><NavLink class="active">
    const activeLink = page.locator('nav.tabs a.active').first()
    await expect(activeLink).toContainText(/configuraci/i)
  })

  test('navegar a /entidades muestra la página de entidades', async ({ page }) => {
    await page.goto('/entidades')
    await expect(page.locator('body')).toBeVisible()
    const activeLink = page.locator('nav.tabs a.active').first()
    await expect(activeLink).toContainText(/entidad/i)
  })

  test('navegar a /visualizacion muestra la página de visualización', async ({ page }) => {
    await page.goto('/visualizacion')
    await expect(page.locator('body')).toBeVisible()
    const activeLink = page.locator('nav.tabs a.active').first()
    await expect(activeLink).toContainText(/visualiz/i)
  })

  test('clic en tab Entidades navega a /entidades', async ({ page }) => {
    await page.goto('/')
    await page.locator('nav.tabs').getByRole('link', { name: 'Entidades' }).click()
    await expect(page).toHaveURL(/entidades/)
  })

  test('clic en tab Visualización navega a /visualizacion', async ({ page }) => {
    await page.goto('/')
    await page.locator('nav.tabs').getByRole('link', { name: 'Visualización' }).click()
    await expect(page).toHaveURL(/visualizacion/)
  })

  test('clic en el logo / nombre navega a Configuración', async ({ page }) => {
    await page.goto('/entidades')
    await page.locator('nav.tabs').getByRole('link', { name: 'Configuración' }).click()
    await expect(page).toHaveURL(/\/$|\/configuracion/)
  })

  test('ruta desconocida no rompe la aplicación', async ({ page }) => {
    // React Router devuelve la SPA; no debe mostrar un error 404 vacío
    await page.goto('/ruta-que-no-existe')
    await expect(page.locator('body')).toBeVisible()
  })

})
