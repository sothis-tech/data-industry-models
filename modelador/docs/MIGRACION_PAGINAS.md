# Migración a React — Registro por fases

Documento de referencia del progreso de la migración del frontend de HTML/JS monolítico a React + TypeScript (Vite). Se actualiza al completar cada bloque de trabajo.

---

## Resumen de fases

| Fase | Descripción | Estado |
|------|-------------|--------|
| **Fase 1** | Modularizar JS legado | ✅ Completada |
| **Fase 2** | Mover lógica de negocio al backend | ✅ Completada |
| **Fase 3** | Shell React + migración progresiva de vistas | ✅ Completada (3/3 páginas) |
| **Fase 4** | Apagado del legado HTML | ✅ Completada |

---

## Fase 1 — Modularizar el JS legado

**Objetivo:** partir del HTML monolítico con scripts inline hacia módulos JS organizados y reutilizables, sin cambiar el comportamiento visible.

### Punto de partida (AS-IS)

- Tres HTML (`index.html`, `entidades.html`, `visualizacion.html`) con lógica JS embebida como scripts inline o en un único `app.js`.
- Sin separación entre utilidades, estado, API y presentación.
- Difícil de testear, reutilizar o extender.

### Cambios realizados

#### Estructura creada en `static/js/`

```
static/js/
├── core/
│   └── http.js           # API_BASE, readJson, parseProxyEnvelope, networkError
├── state/
│   └── storage.js        # getStoredBrokers, setStoredBrokers, getCurrentBroker…
├── ui/
│   └── notifications.js  # showToast, renderStatusBar, withLoading, debounce…
├── api/
│   ├── orion.js          # checkBrokerHealth, postEntity, getEntities, getEntityById…
│   ├── model.js          # fetchViaProxy, fetchManyViaProxy, uploadModelPackage
│   └── validation.js     # validateEntityPayload, validateAttrsPayload
├── app.js                # Punto de entrada global (UI, brokers, estado)
├── model-parser.js       # parseModel, getTypeUri, getContextForPayload, getSchemaForType…
└── pages/
    ├── entities-page.js      # Lógica extraída de entidades.html
    └── visualization-page.js # Lógica extraída de visualizacion.html
```

#### Cambios en las páginas HTML

- Se sustituyeron los scripts inline `<script>…</script>` por `<script src="…">` apuntando a los módulos.
- El bloque inline original quedó deshabilitado con `type="application/disabled-javascript"` para trazabilidad histórica.
- Sin cambios en funcionalidad ni en la estructura visual.

### Resultado

- Código organizado en capas (HTTP, estado, API, UI, páginas).
- Base limpia sobre la que aplicar Fase 2 y Fase 3.
- `model-parser.js` y `test-model-parser.js` (tests Node) completamente operativos.

---

## Fase 2 — Mover lógica de negocio al backend

**Objetivo:** trasladar al backend la lógica compleja de negocio que estaba en el cliente (construcción de grafos, normalización de payloads, validación contra schema).

### Endpoints incorporados en FastAPI

| Método | Ruta | Función |
|--------|------|---------|
| `POST` | `/api/graph/orion/build` | Construir grafo de instancias Orion-LD (nodos/enlaces/estadísticas) |
| `GET`  | `/api/entities/{entity_id}/view` | Vista enriquecida de entidad (atributos formateados con metadatos) |
| `POST` | `/api/graph/schema/build` | Construir grafo abstracto del modelo (tipos/relaciones/métricas) |
| `POST` | `/api/graph/schema/type-view` | Detalle de tipo del schema (`from_rels` / `to_rels`) |
| `POST` | `/api/entities/prepare-payload` | Preparar y normalizar payload de creación (`type`, `id`, `@context`, `input_mode`) |
| `POST` | `/api/entities/prepare-attrs-payload` | Preparar y normalizar payload de edición (`PATCH attrs`) |

### Cambios en el frontend legado

- Las páginas `visualizacion.html` y `entidades.html` pasan a consumir los nuevos endpoints para construcción, enriquecimiento y normalización.
- Se eliminaron los fallbacks locales de lógica de negocio del cliente.
- La capa `static/js/api/orion.js` quedó homogenizada en manejo de errores (`status`, `error`).

### Validación de cierre

- Suite de tests backend actualizada y en verde: `test_helpers.py`, `test_proxy.py`, `test_upload.py`, `test_validate.py`.
- Verificación manual de flujos: crear, editar, borrar, visualizar grafos, detalle de paneles.

---

## Fase 3 — Shell React + migración de vistas

**Objetivo:** montar un proyecto React moderno (Vite + TypeScript) que conviva con el legado y sustituya progresivamente cada vista. Cuando las tres páginas estén migradas, el legado HTML se puede apagar.

### Infraestructura del frontend React

> Directorio raíz: `frontend/`

#### Setup del proyecto

| Elemento | Detalle |
|----------|---------|
| Bundler | Vite 8 |
| Lenguaje | TypeScript estricto |
| Routing | `react-router-dom` |
| Proxy dev | `/api` → `http://127.0.0.1:8000` (configrado en `vite.config.ts`) |
| Node | `>=20.19.0 <23` (fijado en `.nvmrc` y `package.json#engines`) |

#### Estructura de código

```
frontend/src/
├── types/          # Interfaces TypeScript sin lógica (broker, model, entity, graph…)
├── lib/            # Utilidades puras sin React (http, storage, model-parser, graph-utils)
├── api/            # Clientes HTTP hacia el backend (orion, model, validation, graph)
├── hooks/          # Lógica React reutilizable (estado + efectos)
├── components/     # Componentes de UI genéricos (StatusBar, ConfirmModal…)
├── styles/         # CSS modular por responsabilidad
│   ├── tokens.css / base.css / layout.css / components.css
│   └── pages/      # Un archivo por ruta (config, entities, visualization)
└── pages/          # Una carpeta por ruta
    ├── config/
    ├── entities/
    └── viz/
```

#### Archivos clave de infraestructura

| Archivo | Descripción |
|---------|-------------|
| `lib/http.ts` | `readJson` (captura body crudo en fallos con preview), `parseProxyEnvelope`, `networkError` |
| `lib/storage.ts` | Acceso a `localStorage`: brokers guardados, broker activo |
| `lib/model-parser.ts` | Puerto TS de `model-parser.js`: `parseModel`, `getTypeUri`, `getContextForPayload`, `getSchemaForType`, `buildCreateBasePayload`, `compactAttributeKeysForSchema` |
| `lib/graph-utils.ts` | `zoomFit`, `createTypeColorScale`, `resolveTypeColor`, `filterOrionByTypeKeys`, persistencia del filtro en `localStorage` |
| `api/orion.ts` | `checkBrokerHealth`, `postEntity`, `getEntities`, `getEntityById`, `patchEntityAttrs`, `deleteEntity`, `prepareEntityPayload`, `prepareAttrsPayload` (mapea snake_case → camelCase) |
| `api/model.ts` | `fetchViaProxy`, `fetchManyViaProxy`, `uploadModelPackage` |
| `api/validation.ts` | `validateEntityPayload`, `validateAttrsPayload`, `humanizeSchemaError` (robusto ante `detail[]` de Pydantic) |
| `api/graph.ts` | `buildSchemaGraph`, `buildSchemaTypeView`, `buildOrionGraph`, `getEntityView` |
| `hooks/useAppStatus.ts` | Estado global: broker activo, salud, resumen del modelo |
| `hooks/useSplitResize.ts` | Resize del panel izquierdo con ratón y teclado, ancho persistido |
| `hooks/useEntityList.ts` | Listado de entidades: paginación, filtro de tipo, búsqueda en cliente |

#### Dependencias de producción

| Paquete | Versión | Motivo |
|---------|---------|--------|
| `react` | ^19 | Biblioteca de UI |
| `react-dom` | ^19 | Renderizado DOM |
| `react-router-dom` | ^7 | Routing SPA (`/`, `/entidades`, `/visualizacion`) |
| `d3` | ^7 | Grafos de fuerza interactivos en la vista Visualización |
| `react-select` | ^5 | Dropdown con búsqueda integrada (selector de tipo en `/entidades`) |

> `@types/d3` se instala como `devDependency` — solo se usa en compilación TypeScript, no en producción.

#### Estilos

`index.css` contiene solo `@import`. Los estilos viven en `src/styles/`:

| Archivo | Contenido |
|---------|-----------|
| `tokens.css` | Custom properties: colores (tema oscuro), sombras, radios, fuentes, alturas del shell |
| `base.css` | Reset, scrollbar oscura, `button` global (variantes primary/secondary/danger), inputs, `code` |
| `layout.css` | `app-shell`, `topbar` (con sombra), `tabs` (underline animado), `page-centered` |
| `components.css` | `StatusBar`, `OnboardingCard`, `StatusMessage`, modales (con animación de entrada) |
| `pages/config.css` | Estilos exclusivos de `/` (tarjetas, formularios, lista de brokers) |
| `pages/entities.css` | Estilos exclusivos de `/entidades` (split panel, lista, textarea expandida) |
| `pages/visualization.css` | Estilos exclusivos de `/visualizacion` (grafos D3, paneles, filtros de tipo) |

---

### `/` — Configuración

**Estado:** ✅ Completada  
**Legado sustituido:** `static/index.html` + `static/js/pages/config-page.js` *(eliminados en Fase 4)*

#### Componentes creados

| Componente | Descripción |
|------------|-------------|
| `pages/config/ConfigPage.tsx` | Orquestador; recibe `refreshKey` y `triggerRefresh` del Layout |
| `pages/config/BrokerCard.tsx` | Formulario añadir/seleccionar/desactivar broker |
| `pages/config/ModelCard.tsx` | Formulario cargar modelo por URLs o paquete ZIP |
| `pages/config/OnboardingCard.tsx` | Guía "Primeros pasos" colapsable con progreso |
| `components/StatusBar.tsx` | Barra de estado global en el Layout (broker + modelo) |
| `components/StatusMessage.tsx` | Mensajes `info` / `success` / `error` reutilizables |

#### Hooks creados

| Hook | Descripción |
|------|-------------|
| `hooks/useBroker.ts` | Estado y acciones del formulario de broker |
| `hooks/useModel.ts` | Estado y acciones del formulario de modelo |
| `hooks/useAppStatus.ts` | Lee `localStorage` reactivamente al `refreshKey` del Layout |

#### Funcionalidades preservadas

- Añadir, seleccionar, desactivar y **eliminar** brokers (persistidos en `localStorage`)
- Comprobar salud del broker (`GET /api/health`)
- Cargar modelo por URLs o subir paquete `.zip`
- Borrar modelo activo
- Barra de estado: punto de color (verde/amarillo/rojo) + nombre del broker + resumen del modelo
- Guía de primeros pasos: 3 pasos con estado en `localStorage`, colapsable

---

### `/entidades` — Entidades

**Estado:** ✅ Completada  
**Legado sustituido:** `static/entidades.html` + `static/js/pages/entities-page.js` *(eliminados en Fase 4)*

#### Componentes creados

| Componente | Descripción |
|------------|-------------|
| `pages/entities/EntitiesPage.tsx` | Orquestador: split layout, modales, dirty-guard |
| `pages/entities/EntityList.tsx` | Panel izquierdo: filtro, búsqueda, lista, "Cargar más" |
| `pages/entities/EntityCreate.tsx` | Panel de alta: template JSON, formatear, validar, crear |
| `pages/entities/EntityEdit.tsx` | Panel de edición: cargar attrs, formatear, validar, PATCH |
| `pages/entities/SelectTypeModal.tsx` | Modal para elegir tipo al crear sin filtro activo |
| `components/ConfirmModal.tsx` | Modal de confirmación genérico (trampa de foco, accesible) |

#### Hooks creados

| Hook | Descripción |
|------|-------------|
| `hooks/useEntityList.ts` | Fetch, paginación (`PAGE_SIZE=500`), filtro de tipo, búsqueda en cliente, "cargar más" con fallback por tipos |
| `hooks/useSplitResize.ts` | Resize del panel izquierdo con ratón y teclado (`ArrowLeft/Right/Home/End`), ancho en `localStorage` |

#### Funcionalidades preservadas

- Panel izquierdo redimensionable con ratón y teclado
- Filtro por tipo de entidad + búsqueda en tiempo real (nombre, ID, tipo)
- Paginación con "Cargar más" y fallback por tipos cuando Orion no soporta paginación global
- Crear entidad con template del paquete (ejemplo NGSI-LD) o base mínima generada
- Editar atributos vía PATCH con validación contra JSON Schema del modelo
- Eliminar entidad con modal de confirmación accesible
- Duplicar entidad (compacta IRIs expandidas que devuelve Orion)
- Navegación entrante desde el grafo (`viz_filter_type`, `viz_select_id` en `sessionStorage`)
- `Ctrl+S` para guardar según el panel activo
- Aviso al cerrar con cambios sin guardar (`beforeunload`)

---

### `/visualizacion` — Visualización

**Estado:** ✅ Completada  
**Legado sustituido:** `static/visualizacion.html` + `static/js/pages/visualization-page.js` *(eliminados en Fase 4)*

#### Archivos y tipos nuevos

| Archivo | Descripción |
|---------|-------------|
| `types/graph.ts` | `SchemaGraphNode/Link`, `OrionGraphNode/Link`, `EntityView`, `SchemaTypeView`, `NsBadge`, `EntityViewAttr` |
| `api/graph.ts` | `buildSchemaGraph`, `buildSchemaTypeView`, `buildOrionGraph`, `getEntityView` |
| `lib/graph-utils.ts` | `zoomFit`, `createTypeColorScale`, `resolveTypeColor`, `filterOrionByTypeKeys`, persistencia del filtro de tipos en `localStorage` |

#### Componentes creados

| Componente | Descripción |
|------------|-------------|
| `pages/viz/VisualizationPage.tsx` | Orquestador: dos tabs, estado completo, flujo de borrado |
| `pages/viz/SchemaGraph.tsx` | Grafo D3 del modelo abstracto; `forwardRef` + `useImperativeHandle` para zoom |
| `pages/viz/OrionGraph.tsx` | Grafo D3 de instancias Orion; aplica filtro de visibilidad sin reconstruir la simulación |
| `pages/viz/NodeDetailPanel.tsx` | Panel slide-in reutilizable (schema y Orion comparten el mismo componente) |
| `pages/viz/SchemaInfoPanel.tsx` | Panel colapsable con lista de tipos y tabla de relaciones; asa redimensionable |
| `pages/viz/TypeFilterPanel.tsx` | Checkboxes de filtro por tipo para el grafo Orion; checkbox maestro con estado `indeterminate` |

#### Funcionalidades preservadas

- **Tab "Modelo abstracto"**: grafo de tipos con colores por `d3.schemeTableau10`, highlight al hover, arrastre de nodos, zoom/fit, panel de detalle con relaciones `→` / `←` del tipo, panel de info colapsable y redimensionable con lista de tipos y tabla de relaciones
- **Tab "Instancias Orion-LD"**: carga lazy al abrir el tab por primera vez, filtro por tipos con checkbox maestro, panel de detalle con atributos enriquecidos (`ns`, `typeTag`, `display`), botón recargar, borrado con `ConfirmModal` accesible
- Zoom in / out / fit en ambos grafos (controles en overlay)
- Arrastre de nodos sin activar el click de detalle
- Navegación a `/entidades` desde ambos paneles de detalle (escribe `viz_filter_type` y `viz_select_id` en `sessionStorage`)
- Marca el paso 3 de onboarding como completado al entrar en la página

---

## Fase 4 — Apagado del legado

**Estado:** ✅ Completada

### Cambios realizados

#### Eliminaciones
- Carpeta `static/` completa: `index.html`, `entidades.html`, `visualizacion.html`, `modelo.html`, `css/app.css` y toda la carpeta `js/` (~6 000 líneas de código legado).

#### `backend/main.py` — nuevo bloque de frontend

El bloque que servía el legacy HTML ha sido reemplazado por uno que sirve el build de producción de React:

```python
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    # Archivos estáticos compilados (JS, CSS, imágenes)
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    # Catch-all: cualquier ruta que no sea /api/* devuelve index.html
    # para que React Router gestione la navegación en cliente.
    @app.get("/{full_path:path}")
    def serve_react(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_DIST / "index.html"))
```

### Flujo de trabajo resultante

#### Desarrollo (sin cambios respecto a Fase 3)
```
# Terminal 1 — backend
cd backend && uvicorn main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev        # Vite en :5173, proxy /api → :8000
```

#### Producción / despliegue
```
# 1. Generar el build de React (solo cuando hay cambios en el frontend)
cd frontend && npm run build      # genera frontend/dist/

# 2. Arrancar únicamente el backend (sirve API + frontend compilado)
cd backend && uvicorn main:app --host 0.0.0.0 --port 8000
```

> **Nota:** `frontend/dist/` está en `.gitignore` — el build no se commitea.
> Hay que ejecutar `npm run build` en cada despliegue antes de arrancar uvicorn.

---

## Convenciones del proyecto

- **Imports**: rutas relativas (`../api/orion`, `../../lib/storage`) — sin alias `@/`
- **Tipos**: en `types/` si se comparten entre módulos; inline si son locales al archivo
- **Estado global**: sin context/store por ahora — `refreshKey` via `useOutletContext` sincroniza Layout con páginas hijas
- **CSS**: custom properties en `tokens.css`; un archivo por página en `styles/pages/`
- **PowerShell**: no usar `&&` — ejecutar `npm run build` y `npm run lint` como comandos separados
