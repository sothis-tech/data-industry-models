# Tests unitarios y de componentes (Vitest)

- **Patrón:** `**/*.test.{ts,tsx}` bajo esta carpeta (`setup.ts`, `lib/`, `components/`, `hooks/`).
- **Por qué bajo `src/test`:** imports cortos hacia `../../pages`, `../../hooks`, etc., y misma raíz que el código que se prueba.
- **Exclusión:** la carpeta `e2e/` de Playwright no forma parte de Vitest (véase `vite.config.ts`).

Comandos desde `frontend/`: `npm test`, `npm run test:watch`, `npm run test:coverage`.

Detalle por fichero: `docs/TESTS.md` §2.
