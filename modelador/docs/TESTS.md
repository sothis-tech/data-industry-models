# Estrategia de tests

Documento de referencia de la cobertura de tests del proyecto. Describe qué se prueba, cómo ejecutarlo y qué requisitos necesita cada capa.

**Logs JSON y errores HTTP:** ver [`docs/LOGGING.md`](./LOGGING.md).

---

## Resumen de capas

| Capa | Herramienta | Tests | Requiere servidor |
|------|-------------|-------|-------------------|
| **Backend — integración** | Pytest + FastAPI TestClient | 183 | No |
| **Frontend — componentes y lógica** | Vitest + React Testing Library | 156 | No |
| **Frontend — E2E** | Playwright (Chromium) | 58 + **4 opcionales** | Sí (FastAPI `:8000` + Vite `:5173`; los 4 opcionales además Orion-LD) |

Informe de ejecución detallado: [`docs/INFORME-EJECUCION-TESTS.md`](./INFORME-EJECUCION-TESTS.md).

### Mapa de carpetas

```
07_INN_DATA_SPACE_MODELADOR/
├── backend/tests/          # Pytest (integración HTTP)
├── docs/TESTS.md           # Este documento
└── frontend/
    ├── e2e/                # Playwright (*.spec.ts) + README
    ├── src/test/           # Vitest (*.test.ts, *.test.tsx) + README
    ├── playwright.config.ts
    └── vite.config.ts      # include Vitest: src/test/**; exclude: e2e/**
```

Convención: **Vitest** vive bajo `src/test/` (imports al código de `src/`). **Playwright** vive en `e2e/` en la raíz del paquete frontend, fuera de `src/`, para no mezclar con el bundler.

---

## 1. Tests de backend (integración)

### Descripción

Cubren los endpoints HTTP de FastAPI sin necesidad de Orion-LD real. El `TestClient` de FastAPI lanza la aplicación en memoria y hace llamadas HTTP directas.

### Cómo ejecutar

```bash
cd backend
python -m pytest tests/ -v
```

Con reporte de cobertura:

```bash
python -m pytest tests/ --cov=main --cov-report=term-missing
```

### Estructura

```
backend/tests/
├── conftest.py          # Fixture `client` (TestClient de FastAPI)
├── test_helpers.py      # Funciones internas puras (sin HTTP)
├── test_proxy.py        # Endpoints de proxy, health, graph y entities (flujos básicos)
├── test_validate.py     # POST /api/validate/entity y /api/validate/attrs
├── test_upload.py       # POST /api/upload/package (carga de ZIP)
├── test_graph.py        # POST /api/graph/orion/build, /schema/build, /schema/type-view
└── test_entities.py     # POST /api/entities/prepare-payload y /prepare-attrs-payload
```

### Cobertura por archivo

#### `test_helpers.py` — Funciones internas puras

Prueba las funciones de `main.py` directamente, sin cliente HTTP. Son las más rápidas.

| Clase | Función cubierta | Tests |
|-------|-----------------|-------|
| `TestToPlainForSchema` | `_to_plain_for_schema` | 9 |
| `TestIsNormalizedEntity` | `_is_normalized_entity` | 5 |
| `TestValidateBrokerUrl` | `_validate_broker_url` | 10 |
| `TestSafeMemberName` | `_safe_member_name` | 5 |
| `TestStripRootFolder` | `_strip_root_folder` | 4 |
| `TestClassifyMembers` | `_classify_members` | 9 |
| `TestBuildOrionInstanceGraph` | `_build_orion_instance_graph` | 1 |
| `TestEntityViewFromRaw` | `_entity_view_from_raw` | 1 |
| `TestBuildSchemaGraphData` | `_build_schema_graph_data` | 1 |
| `TestBuildSchemaTypeView` | `_build_schema_type_view` | 1 |
| `TestPrepareEntityPayloadHelpers` | `_detect_entity_input_mode`, `_normalize_entity_for_orion`, `_normalize_attrs_payload` | 3 |

#### `test_proxy.py` — Proxy y endpoints de conectividad

| Clase | Endpoint | Qué verifica |
|-------|---------|-------------|
| `TestHealthEndpoint` | `GET /api/health` | 200 con `ok`, sin broker retorna `ok: false`, validación de URL |
| `TestProxyPostValidation` | `POST /api/proxy/entities` | URL vacía → 400, esquema inválido → 400, broker inaccesible → 200 con error |
| `TestProxyPatchValidation` | `PATCH /api/proxy/entities/{id}/attrs` | Misma validación de URL |
| `TestProxyDeleteValidation` | `DELETE /api/proxy/entities/{id}` | URL requerida, esquema inválido, broker caído |
| `TestProxyGetEntitiesValidation` | `GET /api/proxy/entities` | URL requerida, esquemas inválidos |
| `TestProxyGetEntityByIdValidation` | `GET /api/proxy/entities/{id}` | URL requerida, esquemas inválidos |
| `TestEntityViewValidation` | `GET /api/entities/{id}/view` | URL requerida, broker caído → 200 con error |
| `TestSchemaGraphBuild` | `POST /api/graph/schema/build` | Respuesta básica con nodos y links |
| `TestSchemaTypeViewBuild` | `POST /api/graph/schema/type-view` | Respuesta con `view.type_id` |
| `TestPrepareEntityPayload` | `POST /api/entities/prepare-payload` | Normalización básica y campo `id` generado |
| `TestPrepareAttrsPayload` | `POST /api/entities/prepare-attrs-payload` | Atributos planos envueltos como NGSI-LD |

#### `test_validate.py` — Validación de entidades y atributos

| Clase | Endpoint | Qué verifica |
|-------|---------|-------------|
| `TestValidateEntity` | `POST /api/validate/entity` | Payload válido/inválido, campos requeridos, modos normalized y plain, coerción a array, schema no encontrado |
| `TestValidateAttrs` | `POST /api/validate/attrs` | Tipos válidos (Property, Relationship, GeoProperty), campos faltantes, atributos inválidos |

#### `test_upload.py` — Carga de paquetes ZIP

| Clase | Qué verifica |
|-------|-------------|
| `TestUploadStructureComplete` | ZIP completo con schemas, contexto, descriptor, ejemplos |
| `TestUploadPartialStructures` | ZIPs parciales (solo schemas, solo contexto, etc.) |
| `TestUploadExamples` | Estructura de ejemplos en subfolder y flat, prioridad primer ejemplo |
| `TestUploadSecurity` | Path traversal rechazado, límite de ficheros |
| `TestUploadErrors` | ZIP vacío, no es ZIP, JSON inválido |

#### `test_graph.py` — Construcción de grafos

| Clase | Endpoint | Tests clave |
|-------|---------|------------|
| `TestOrionGraphBuild` | `POST /api/graph/orion/build` | 13: relaciones explícitas e implícitas, nodos fantasma, entidades sin id, stats |
| `TestSchemaGraphBuild` | `POST /api/graph/schema/build` | 8: nodos, links solo entre tipos conocidos, métricas de grado, grafo vacío |
| `TestSchemaTypeView` | `POST /api/graph/schema/type-view` | 9: from_rels, to_rels, property_short, flag implicit, relaciones opcionales |

#### `test_entities.py` — Preparación de payloads

| Clase | Endpoint | Tests clave |
|-------|---------|------------|
| `TestPrepareEntityPayload` | `POST /api/entities/prepare-payload` | 14: tipo inyectado, id generado/preservado, contexto inyectado/no sobreescrito, modo plain/normalized, campos id/type/`@context` no envueltos |
| `TestPrepareAttrsPayload` | `POST /api/entities/prepare-attrs-payload` | 12: string/número/booleano/lista wrapeados, Property/Relationship/GeoProperty ya normalizados preservados, mezcla, vacío |

---

## 2. Tests de frontend — componentes y lógica pura

### Descripción

Pruebas rápidas de funciones de librería y componentes React sin navegador real. Vitest corre en entorno `jsdom`.

### Cómo ejecutar

```bash
cd frontend

# Una sola pasada
npm test

# Modo watch durante desarrollo
npm run test:watch

# Con reporte de cobertura
npm run test:coverage
```

### Estructura

```
frontend/src/test/
├── README.md
├── setup.ts                         # @testing-library/jest-dom
├── lib/
│   ├── model-parser.test.ts
│   └── graph-utils.test.ts
├── hooks/
│   └── useEntityList.test.ts
└── components/
    ├── ConfirmModal.test.tsx
    ├── StatusMessage.test.tsx
    ├── SelectTypeModal.test.tsx
    ├── EntityList.test.tsx
    ├── EntityCreate.test.tsx
    └── EntityEdit.test.tsx
```

### Cobertura por archivo

#### `model-parser.test.ts`

Todas las funciones reciben el JSON raw del modelo (igual que se lee de `localStorage`).

| Función | Tests | Qué verifica |
|---------|-------|-------------|
| `parseModel` | 5 | null, JSON inválido, extracción de tipos por título, array de relaciones |
| `getTypeUri` | 4 | IRI completa de tipo conocido, fallback para tipo desconocido, JSON null o inválido |
| `getSchemaForType` | 3 | Schema por título, null para tipo no encontrado, null con JSON null |
| `getContextForPayload` | 3 | Contexto de modelo válido, fallback ETSI si null, fallback ETSI si JSON inválido |
| `buildCreateBasePayload` | 5 | `payload` y `fromExample` presentes, `type` correcto, `id` con patrón `urn:ngsi-ld:`, `@context` incluido, funciona con JSON null |

#### `graph-utils.test.ts`

| Función | Tests | Qué verifica |
|---------|-------|-------------|
| `typeKeyFromFullType` | 5 | Último segmento de IRI, valor corto sin cambios, multi-nivel, cadena vacía, URN |
| `filterOrionByTypeKeys` | 6 | Todos activos, filtrado por tipo, links con endpoints visibles, sin activos, links con endpoint oculto eliminados |
| `saveTypeFilter` + `loadSavedTypeFilter` | 5 | Guardar y restaurar, sin guardado devuelve todo, excluye no guardados, claves nuevas excluidas, guardado vacío |

#### `ConfirmModal.test.tsx`

| Tests | Qué verifica |
|-------|-------------|
| 11 | Render de título y mensaje, botones Cancelar/Confirmar, label personalizado, loading → "Procesando…" deshabilitado, JSX como mensaje, clase `danger`, tecla Escape |

#### `StatusMessage.test.tsx`

| Tests | Qué verifica |
|-------|-------------|
| 5 | Render de texto, elemento `<p>`, clase `error`, clase `success`, clase `info` por defecto |

#### `SelectTypeModal.test.tsx`

| Tests | Qué verifica |
|-------|-------------|
| 13 | Render de título y descripción, lista completa de opciones, primer tipo seleccionado por defecto, Cancelar → `onClose`, Continuar → `onConfirm(tipo)`, cambio de selección, Escape → `onClose`, clic en overlay → `onClose`, clic en modal-box no cierra, Continuar deshabilitado y no llama `onConfirm` con lista vacía, un solo tipo |

#### `EntityList.test.tsx`

| Tests | Qué verifica |
|-------|-------------|
| 20 | Botón "Nueva entidad", campo de búsqueda (`searchbox`), entidad con `name.value` visible, entidad sin nombre muestra ID, contador total, estado `loading`, lista vacía sin búsqueda, lista vacía con búsqueda activa, `onSelect` al hacer clic, clase `active` en ítem seleccionado, `onSearchChange` al escribir, Escape limpia búsqueda, valor del campo, `onNewEntity` al hacer clic, "Cargar más" según `hasMore`, sin botón si `hasMore=false`, sin botón con búsqueda activa, `onLoadMore` al hacer clic, estado `loadingMore` |

#### `useEntityList.test.ts` (hook)

| Tests | Qué verifica |
|-------|-------------|
| 18 | No fetch con `brokerUrl null`, no fetch con cadena vacía, sin auto-fetch al montar, `getEntities` llamado tras `fetchEntities()`, `allEntities` se rellena, `loading` vuelve a `false`, `error` nulo tras éxito, `typeFilter` pasa URI correcto, `hasMore=false` con `body.length < 500`, error con `typeFilter` y respuesta errónea, error al rechazar la promesa, `filteredEntities` devuelve todo sin búsqueda, filtra por ID, devuelve vacío sin coincidencias, `setSearch` actualiza `search`, `fetchEntities` limpia búsqueda, `loadMore` sin broker no llama API, `loadMore` con `hasMore=false` no llama API |

#### `EntityCreate.test.tsx`

| Tests | Qué verifica |
|-------|-------------|
| 14 | Render de textarea/botones, `initialPayload` pre-rellena textarea, `onDirty` al editar, formateo de JSON, formateo sin romper con JSON inválido, validación exitosa → pre sin clase `error`, JSON inválido → pre con clase `error`, error humanizado en validación fallida, `onCreated` tras creación exitosa, `postEntity` no llamado con validación fallida, `postEntity` no llamado con error en `prepareEntityPayload`, `postEntity` no llamado cuando ya existe el ID |

#### `EntityEdit.test.tsx`

| Tests | Qué verifica |
|-------|-------------|
| 16 | ID y tipo visibles en barra info, botones Guardar/Eliminar/Validar presentes, textarea `readonly` durante carga, textarea editable tras carga, error de carga visible cuando API devuelve error, error con status 0 (red), aviso de entidad sin atributos, `onSaved` tras PATCH correcto, `patchEntityAttrs` no llamado con validación fallida, `onDelete` llamado directamente al pulsar Eliminar, Eliminar deshabilitado durante guardado, `onDirty` al editar textarea, formateo sin romper con JSON inválido |

---

## 3. Tests E2E — Playwright

### Descripción

Simulan un usuario real navegando con Chromium. Verifican la aplicación completa de extremo a extremo. **No requieren Orion-LD real** para la mayoría de casos (broker y modelo se simulan con `localStorage`).

Playwright arranca **dos servidores** antes de los tests (si no están ya activos):

1. **FastAPI** en `http://127.0.0.1:8000` (`python -m uvicorn main:app` desde `backend/`) — necesario para `/api/graph/*`, proxy y validación.
2. **Vite** en `http://localhost:5173` — la SPA y el proxy de `/api` hacia el backend.

Los **58** tests en `e2e/*.spec.ts` (salvo el fichero opcional siguiente) **no** requieren Orion-LD: broker y modelo se simulan con `localStorage` o mocks de API (`auth-session.spec.ts`).

**Integración opcional con Orion real:** `e2e/orion-integration.spec.ts` define **4** tests adicionales. Solo se ejecutan si en el entorno está `ORION_E2E=1`. Sin esa variable, `test.skip` en `beforeEach` los marca como omitidos (CI y `npm run test:e2e` siguen verdes). Variables: `ORION_E2E_URL` (opcional, por defecto `http://localhost:1026`). **Importante:** lanzar Playwright desde la carpeta `frontend/` para usar el mismo `@playwright/test` que el proyecto (véase comentarios en el spec).

### Cómo ejecutar

```bash
cd frontend

# Todos los E2E (arranca backend :8000 y Vite :5173 si hace falta)
npm run test:e2e

# Con interfaz visual interactiva (lista de tests y trazas; el navegador puede abrirse aparte)
npm run test:e2e:ui

# Ver Chromium en primer plano mientras corren los tests (útil la primera vez)
npm run test:e2e:headed
# Equivalente: npx playwright test --headed
# Un solo fichero: npx playwright test e2e/navigation.spec.ts --headed

# Solo integración Orion (requiere Orion accesible y ORION_E2E=1 en el entorno)
# PowerShell:  $env:ORION_E2E='1'; npm run test:e2e:orion
# bash:        ORION_E2E=1 npm run test:e2e:orion
```

`reuseExistingServer: true`: si ya tienes backend y/o Vite en marcha, Playwright los reutiliza.

### Estructura

```
frontend/e2e/
├── README.md
├── navigation.spec.ts       # Routing básico de la SPA
├── config.spec.ts           # Configuración (broker y modelo)
├── entities.spec.ts         # Entidades (filtros, modal, handoff)
├── cross-page.spec.ts       # Flujos entre páginas
├── visualization.spec.ts  # Visualización (schema, Orion simulado, enlace a Entidades)
├── auth-session.spec.ts       # Sesión Orion (mock status): Marvin, RAG, StatusBar
└── orion-integration.spec.ts  # Opcional: Orion-LD real (ORION_E2E=1)
```

### Plan local con Orion en `http://localhost:1026`

1. Levantar **Orion-LD** en `:1026`.
2. Comprobación rápida: `cd backend && python -m pytest tests/ -q` y `cd frontend && npm test`.
3. E2E sin broker real: `cd frontend && npm run test:e2e`.
4. E2E contra Orion: `cd frontend`, `ORION_E2E=1` y `npm run test:e2e:orion` (o `npm run test:e2e` para el suite completo: los 4 tests opcionales corren o se omiten según la variable).

### Cobertura por archivo

#### `navigation.spec.ts` — Routing de la SPA

| Test | Verifica |
|------|---------|
| Página de inicio carga | Título de la aplicación presente |
| Tab Configuración activa por defecto | Enlace activo en `nav.tabs a.active` |
| Navegar a `/entidades` | Tab activa y URL correcta |
| Navegar a `/visualizacion` | Tab activa y URL correcta |
| Clic en tab Entidades | Navega a `/entidades` |
| Clic en tab Visualización | Navega a `/visualizacion` |
| Clic en tab Configuración | Navega a `/` |
| Ruta desconocida | No rompe la aplicación (SPA catch-all) |

#### `config.spec.ts` — Configuración

| Grupo | Tests | Verifica |
|-------|-------|---------|
| Formulario de broker | 5 | Campos nombre/URL, botón guardar, guardar muestra en lista, eliminar quita de lista, persiste tras recarga |
| Formulario de modelo | 2 | Sección NGSI-LD visible, opción ZIP visible |

#### `entities.spec.ts` — Página de Entidades

| Grupo | Tests | Verifica |
|-------|-------|---------|
| Sin broker | 2 | Mensaje de aviso, botón "Nueva entidad" presente |
| Filtros con modelo | 3 | Tipos del modelo en react-select, seleccionar tipo actualiza filtro, campo búsqueda |
| SelectTypeModal | 5 | Modal se abre sin filtro activo, botón Cancelar, cerrar no abre panel, seleccionar tipo abre panel con textarea, alert sin modelo |
| Handoff desde Visualización | 2 | `viz_filter_type` en sessionStorage aplica filtro, sin sessionStorage no aplica filtro |

#### `cross-page.spec.ts` — Flujos entre páginas

| Grupo | Tests | Verifica |
|-------|-------|---------|
| Modelo → Entidades y Viz | 4 | StatusBar "sin modelo", tipos en filtro de Entidades, SVG en Viz, limpiar modelo quita tipos |
| Broker → StatusBar | 2 | Guardar broker → URL en StatusBar, broker persiste al navegar |
| Onboarding 3 pasos | 3 | Pasos visibles, guardar broker marca paso 1, visitar Entidades marca paso 3 |

#### `visualization.spec.ts` — Visualización

| Grupo | Tests | Verifica |
|-------|-------|---------|
| Sin broker ni modelo | 5 | Tab schema activa, tab Orion visible, mensaje sin modelo, aviso Orion sin broker, botón recargar |
| Con modelo cargado | 4 | Tab visible, controles de zoom, SVG renderizado, Orion muestra aviso sin broker |
| Enlace a Entidades | 2 | Panel de detalle con enlace "Ver entidades", clic navega a `/entidades` con `viz_filter_type` en sessionStorage |
| Empty states | 2 | Mensaje correcto sin modelo+broker, enlace a Config en Orion sin broker |

#### `auth-session.spec.ts` — Sesión Orion (sin Keycloak real)

Intercepta `GET /api/auth/orion/status` y `GET /api/chat/config`. Verifica StatusBar, bloqueo de Marvin y RAG sin sesión, habilitación con sesión simulada y bloqueo tras evento `modelador:orion-session-lost`.

#### `orion-integration.spec.ts` — Orion-LD real (opcional)

Solo con `ORION_E2E=1`. Comprueba conectividad en Config, listado vía proxy, pestaña Instancias Orion sin error de conexión (panel Orion en DOM, no solo `getByRole('tabpanel')` por accesibilidad), y flujo crear/eliminar entidad `E2EThing`.

---

## 4. Decisiones de diseño

### Por qué no se mockea la API en los tests de frontend

Los tests de componentes (`Vitest`) prueban únicamente lógica pura (lib) y componentes sin efectos de red. El comportamiento con API real se delega a los tests E2E y a los tests de integración del backend, evitando así dobles de prueba frágiles.

### Por qué la mayoría de E2E no requieren Orion-LD

Los flujos críticos de la UI (routing, estado local, persistencia en `localStorage`/`sessionStorage`, mensajes de error de red) funcionan sin broker. El CRUD y el grafo de instancias contra un broker real están cubiertos de forma **opt-in** en `e2e/orion-integration.spec.ts`.

### Separación Vitest vs Playwright

Vitest ejecuta únicamente `src/test/**/*.test.{ts,tsx}`. La carpeta `e2e/` está excluida del scope de Vitest en `vite.config.ts`. Playwright usa `testDir: './e2e'` en `playwright.config.ts`.

---

## 5. Próximos pasos

| Prioridad | Acción |
|-----------|--------|
| Media | Ampliar `orion-integration.spec.ts` (más tipos, filtros de grafo, errores HTTP del broker) o pipeline CI opt-in con Orion |
| Media | Cobertura de errores de red en E2E con `page.route()` de Playwright |
| Baja | Tests de accesibilidad con `axe-playwright` |
| Baja | Rendimiento del grafo D3 con datasets grandes |

**Cerrar el tema “tests + Orion opcional”:** la base está lista (Pytest, Vitest, E2E mock, E2E Orion opt-in, carpetas documentadas). Falta solo lo que quieras añadir como política de equipo: por ejemplo ejecutar `orion-integration.spec.ts` en un job de CI manual o nocturno con Orion, o ampliar casos en ese fichero.
