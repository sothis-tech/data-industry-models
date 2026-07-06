# Tests E2E (Playwright)

Especificaciones que abren Chromium contra la SPA real (`baseURL` en `playwright.config.ts`).

- **Ubicación:** `frontend/e2e/*.spec.ts` (config: `testDir: './e2e'`).
- **Por qué fuera de `src/`:** no importan módulos de la app; arrancan servidores y prueban flujos completos.

## Comandos

Desde `frontend/`:

```bash
npm run test:e2e
npm run test:e2e:ui
# Navegador visible mientras ejecuta (modelador en http://localhost:5173)
npm run test:e2e:headed
```

Sesión Orion (mock, sin Keycloak): `auth-session.spec.ts`.

Integración opcional con **Orion-LD** real: `orion-integration.spec.ts` (variables `ORION_E2E`, `ORION_E2E_URL`). Con entorno listo: `$env:ORION_E2E='1'; npm run test:e2e:orion` (PowerShell).

Documentación ampliada: `docs/TESTS.md`.
