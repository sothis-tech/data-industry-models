# Informe de ejecución de tests — Modelador NGSI-LD

**Fecha de ejecución:** 29 de mayo de 2026 (actualizado tras corrección de fallos)  
**Entorno:** Windows 10, Python 3.10.11, Node.js v24.11.1  
**Repositorio:** `07_INN_DATA_SPACE_MODELADOR`  
**Rama evaluada:** estado local de trabajo (incluye `auth-session.spec.ts` y fix Playwright Windows)

---

## 1. Resumen ejecutivo

| Capa | Herramienta | Total | OK | Fallo | Omitido | Duración |
|------|-------------|------:|---:|------:|--------:|---------:|
| Backend — integración | Pytest | 183 | **183** | 0 | — | ~16 s |
| Frontend — unitarios | Vitest + RTL | 156 | **156** | 0 | — | ~15 s |
| Frontend — E2E | Playwright (Chromium) | 62 | **58** | 0 | 4 | ~1,6 min |
| **Total automatizado** | | **401** | **397** | **0** | **4** | **~2 min** |

**Tasa de éxito global:** 397 / 397 ejecutados = **100 %** (excluyendo omitidos).

Los **4 tests E2E omitidos** son integración con Orion-LD real (`ORION_E2E=1` no estaba activo).

### Correcciones aplicadas (29 may 2026)

| Área | Cambio |
|------|--------|
| Pytest `test_proxy` | `ORION_AUTH_REQUIRED=false` en test de validación URL localhost |
| Vitest `graph-utils` | Expectativa alineada con subgrafo focal + vecinos |
| Vitest `orionSessionEvents` | Regex ampliada (`iniciar sesión`, `chat bloqueado`) |
| E2E `config` / `cross-page` | Botón `Guardar` (sustituye `Guardar y seleccionar`) |
| E2E onboarding | Aserción `/orion\|conexión/i` (texto UI actualizado) |
| `docs/TESTS.md` | Totales actualizados: 156 Vitest, 58 E2E |

---

## 2. Comandos de ejecución

```bash
# Backend (Pytest)
cd backend
python -m pytest tests/ -v

# Frontend unitarios (Vitest)
cd frontend
npm test

# Frontend E2E (arranca FastAPI :8000 + Vite :5173)
cd frontend
npm run test:e2e

# E2E solo sesión Orion (mock)
npm run test:e2e -- e2e/auth-session.spec.ts

# E2E integración Orion real (requiere Orion accesible)
# PowerShell:
$env:ORION_E2E='1'; npm run test:e2e:orion

# Informe HTML Playwright (tras E2E)
npx playwright show-report
```

**Requisitos E2E:** Playwright usa `python` en Windows y `python3` en Linux/Mac (`playwright.config.ts`). Puerto 8000 libre o backend ya en marcha.

---

## 3. Backend — Pytest (183 tests)

**Ubicación:** `backend/tests/`  
**Método:** FastAPI `TestClient` en memoria. No requiere Orion-LD ni servicios externos.

### 3.1 Resultado por fichero

| Fichero | Tests | OK | Fallo | Ámbito |
|---------|------:|---:|------:|--------|
| `test_helpers.py` | 50 | 50 | 0 | Funciones puras de `main.py` |
| `test_proxy.py` | 32 | 32 | 0 | Health, proxy CRUD, validación URL |
| `test_validate.py` | 26 | 26 | 0 | `POST /api/validate/entity`, `/attrs` |
| `test_upload.py` | 17 | 17 | 0 | `POST /api/upload/package` (ZIP) |
| `test_graph.py` | 31 | 31 | 0 | Grafos Orion y schema |
| `test_entities.py` | 27 | 27 | 0 | `prepare-payload`, `prepare-attrs-payload` |

### 3.2 Inventario por módulo

#### `test_helpers.py` (50)
- `_to_plain_for_schema`, `_is_normalized_entity`, `_validate_broker_url`
- `_safe_member_name`, `_strip_root_folder`, `_classify_members`
- `_build_orion_instance_graph`, `_entity_view_from_raw`
- `_build_schema_graph_data`, `_build_schema_type_view`
- Helpers de prepare-payload

#### `test_proxy.py` (32)
- `GET /api/health`
- `POST/PATCH/DELETE/GET /api/proxy/entities` — validación URL y broker caído
- `GET /api/entities/{id}/view`
- Endpoints de grafo schema embebidos en proxy

#### `test_validate.py` (26)
- Validación de entidad: modos plain/normalized/auto, arrays, schema ausente
- Validación de atributos: Property, Relationship, GeoProperty

#### `test_upload.py` (17)
- ZIP completo y parcial, ejemplos, seguridad (path traversal, límite ficheros), errores

#### `test_graph.py` (31)
- `POST /api/graph/orion/build` — nodos, links, implícitos, ghost nodes
- `POST /api/graph/schema/build` — métricas, degree
- `POST /api/graph/schema/type-view` — from/to rels

#### `test_entities.py` (27)
- `POST /api/entities/prepare-payload` — id, context, modos input
- `POST /api/entities/prepare-attrs-payload` — wrapping NGSI-LD

### 3.3 Fallos detectados (resueltos)

| Test | Resolución |
|------|------------|
| `TestProxyPostValidation::test_localhost_valid_url_not_rejected_by_validation` | `monkeypatch.setenv("ORION_AUTH_REQUIRED", "false")` en el test |

---

## 4. Frontend — Vitest (156 tests)

**Ubicación:** `frontend/src/test/`  
**Método:** Vitest + jsdom + React Testing Library. No requiere servidor.

### 4.1 Resultado por fichero

| Fichero | Tests | OK | Fallo | Ámbito |
|---------|------:|---:|------:|--------|
| `components/ConfirmModal.test.tsx` | 11 | 11 | 0 | Modal confirmación |
| `components/EntityCreate.test.tsx` | 18 | 18 | 0 | Formulario creación |
| `components/EntityEdit.test.tsx` | 16 | 16 | 0 | Formulario edición |
| `components/EntityList.test.tsx` | 16 | 16 | 0 | Listado entidades |
| `components/SelectTypeModal.test.tsx` | 15 | 15 | 0 | Modal selección tipo |
| `components/StatusMessage.test.tsx` | 5 | 5 | 0 | Mensajes estado |
| `hooks/useEntityList.test.ts` | 15 | 15 | 0 | Hook listado + paginación |
| `lib/chatBlocks.test.ts` | 5 | 5 | 0 | Bloques mensaje Marvin |
| `lib/graph-utils.test.ts` | 24 | 24 | 0 | Visibilidad nodos grafo Orion |
| `lib/model-parser.test.ts` | 23 | 23 | 0 | Parser modelo / compactación |
| `lib/orion-entities.test.ts` | 5 | 5 | 0 | Utilidades listado broker |
| `lib/orionSessionEvents.test.ts` | 3 | 3 | 0 | Detección fallo auth Orion |

### 4.2 Fallos detectados (resueltos)

| Test | Resolución |
|------|------------|
| `computeOrionVisibleNodeIds > ignores search draft when an entity is focused` | Test actualizado: foco incluye vecinos (Device); se comprueba que búsqueda sin foco oculta Machine |
| `isOrionAuthFailure > detecta mensajes de sesión en error o detail` | Regex ampliada en `orionSessionEvents.ts` |

---

## 5. Frontend — Playwright E2E (62 tests)

**Ubicación:** `frontend/e2e/*.spec.ts`  
**Config:** `playwright.config.ts` — Chromium, `baseURL` `http://localhost:5173`  
**Servidores:** FastAPI `:8000` + Vite `:5173` (arranque automático)

### 5.1 Resultado por fichero

| Fichero | Tests | OK | Fallo | Omitido | Notas |
|---------|------:|---:|------:|--------:|-------|
| `navigation.spec.ts` | 8 | 8 | 0 | 0 | Routing SPA |
| `config.spec.ts` | 7 | 7 | 0 | 0 | Broker + modelo |
| `cross-page.spec.ts` | 11 | 11 | 0 | 0 | Flujos entre páginas |
| `entities.spec.ts` | 13 | 13 | 0 | 0 | Filtros, modal, handoff |
| `visualization.spec.ts` | 13 | 13 | 0 | 0 | Schema, Orion simulado |
| `auth-session.spec.ts` | 7 | 7 | 0 | 0 | Sesión Orion mock (nuevo) |
| `orion-integration.spec.ts` | 4 | 0 | 0 | **4** | Requiere `ORION_E2E=1` |
| **Total** | **62** | **58** | **0** | **4** | |

### 5.2 Inventario detallado E2E

#### `navigation.spec.ts` (8) — ✅ todos OK
1. Página de inicio carga con título
2. Tab Configuración activa por defecto
3. Navegar a `/entidades`
4. Navegar a `/visualizacion`
5. Clic tab Entidades
6. Clic tab Visualización
7. Clic logo → Configuración
8. Ruta desconocida no rompe la app

#### `config.spec.ts` (7) — ✅ todos OK
1. Formulario broker visible
2. Botón Guardar presente
3. Guardar broker → lista
4. Eliminar broker de lista
5. Persistencia tras recargar
6. Sección cargar modelo por URL
7. Opción cargar ZIP

#### `cross-page.spec.ts` (11) — ✅ todos OK
**Modelo Config → otras páginas (4):** todos  
**Broker Config → app (2):** todos  
**Viz → Entidades (2):** todos  
**Onboarding 3 pasos (3):** todos

#### `entities.spec.ts` (13) — ✅ todos OK
- Sin broker: aviso, botón nueva entidad
- Filtros con modelo: tipos, selección, búsqueda
- SelectTypeModal: abrir, cancelar, seleccionar, alert sin tipos
- Handoff sessionStorage desde Visualización

#### `visualization.spec.ts` (13) — ✅ todos OK
- Sin broker: tabs, avisos, recargar instancias
- Con modelo: tipos, zoom, SVG, aviso Orion sin broker
- Enlace Ver entidades → sessionStorage
- Empty states schema y Orion

#### `auth-session.spec.ts` (7) — ✅ todos OK
**Sin sesión (3):** StatusBar, Marvin bloqueado, RAG bloqueado  
**Con sesión (3):** StatusBar, Marvin habilitado, RAG sin bloqueo sesión  
**Pérdida en caliente (1):** evento `ORION_SESSION_LOST` bloquea Marvin

#### `orion-integration.spec.ts` (4) — omitidos (sin Orion)
1. Comprobar conectividad Orion
2. Proxy listado entidades OK
3. Tab Instancias Orion sin error
4. CRUD E2EThing

### 5.3 Ajustes E2E aplicados

Los tests de broker usan el botón **`Guardar`** (`exact: true`). El onboarding comprueba el texto «conexión Orion» en el paso 1 completado.

---

## 6. Cobertura funcional (mapa rápido)

| Área funcional | Backend | Vitest | E2E |
|----------------|:-------:|:------:|:---:|
| Health / proxy HTTP | ✅ | — | parcial |
| Validación entidad/atributos | ✅ | — | — |
| Carga ZIP modelo | ✅ | — | parcial |
| Grafos schema / Orion (API) | ✅ | ✅ graph-utils | ✅ viz |
| Prepare payload entidades | ✅ | ✅ model-parser | — |
| Listado entidades broker | — | ✅ orion-entities | ✅ entities |
| Componentes CRUD UI | — | ✅ | ✅ entities |
| Navegación SPA | — | — | ✅ |
| Config broker/modelo | parcial | — | ✅ |
| Sesión Orion (UI) | parcial | ✅ | ✅ auth-session |
| Panel Marvin / chat | — | ✅ chatBlocks | ✅ auth-session |
| RAG sidebar | — | — | ✅ auth-session |
| Auth Keycloak real | — | — | ❌ manual / orion-integration |
| POST /api/connect | — | — | ❌ no automatizado |

---

## 7. Tests manuales documentados (no ejecutados en esta corrida)

Referencia: `docs/QA-E2E-AGENT-PANEL.md`

Guion manual con casos A–F (~40 pasos): broker + sesión Keycloak, caducidad sesión, entidades, visualización, Marvin, RAG, regresiones. Complementa los huecos de la tabla anterior.

---

## 8. Acciones recomendadas — próximo sprint

### Prioridad media (ampliar cobertura)
1. Vitest para `useAppStatus`, `BrokerCard`, hooks de sesión.
2. E2E para `POST /api/connect` (mock backend).
3. Mantener `docs/TESTS.md` alineado con el informe.

### Prioridad baja (entorno completo)
4. Pipeline CI con los tres comandos en secuencia.
5. Job opcional `ORION_E2E=1` contra entorno QA Kong/Keycloak/Orion.

---

## 9. Historial de este informe

| Versión | Fecha | Notas |
|---------|-------|-------|
| 1.0 | 2026-05-29 | Primera ejecución completa local Windows; 8 fallos detectados |
| 1.1 | 2026-05-29 | Corrección de 8 fallos; **397/397 tests OK** (4 Orion omitidos) |

---

*Documento generado para la tarea de documentación del sprint. Referencia cruzada: [`docs/TESTS.md`](./TESTS.md), [`docs/QA-E2E-AGENT-PANEL.md`](./QA-E2E-AGENT-PANEL.md).*
