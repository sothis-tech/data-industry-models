# Context Server Tenants — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar la WIP del context server multi-tenant según `docs/superpowers/specs/2026-07-23-context-server-tenants-design.md`: persistencia selectiva del contexto, URL estable, checks A+B, confirmación al borrar tenant, puerto 8090, docs/cleanup data_space, y extracción de módulos en el backend del modelador.

**Architecture:** El context server sigue siendo la fuente de verdad por tenant. El modelador persiste schemas/descriptor/examples siempre (con tenant); el `context.jsonld` en disco solo en carga solo-zip. Las URLs externas se comprueban vía proxy (StatusBar + bloqueo al operar). El backend del modelador delega en routers `context_server_proxy` y `model_package`.

**Tech Stack:** FastAPI, React/TypeScript, docker-compose, pytest, Vitest

**Spec:** `docs/superpowers/specs/2026-07-23-context-server-tenants-design.md`

---

## File map

| File | Responsibility |
|---|---|
| `data_space/context_server/main.py` | Añadir merge parcial: PUT que no pise `context/` si `context` viene `omit`/flag `preserveContext` |
| `modelador/backend/context_server_proxy.py` | Router proxy + `persist_model` + config public URL |
| `modelador/backend/model_package.py` | Upload zip + persistencia según reglas |
| `modelador/backend/main.py` | Incluir routers; quitar código movido |
| `modelador/frontend/src/hooks/useModel.ts` | Persistencia selectiva + URL estable + aviso externo |
| `modelador/frontend/src/hooks/useBroker.ts` | Confirm última conexión; mensaje si tenant persiste |
| `modelador/frontend/src/lib/contextReachability.ts` | Probe + hook para StatusBar |
| `modelador/frontend/src/components/StatusBar.tsx` | Indicador alcanzabilidad |
| `modelador/frontend/src/pages/entities/EntitiesPage.tsx` (y create/edit) | Bloqueo si contexto caído |
| `docker-compose.yml` | `8090:8090` |
| `data_space/docker/README.md` | Apuntar al compose raíz |
| `data_space/scripts/` | Mover scripts sueltos |
| `data_space/context_server/README.md` | Tabla persistencia + URLs |

---

### Task 1: Puerto docker `8090:8090`

**Files:**
- Modify: `docker-compose.yml` (servicio `context-server`)

- [ ] **Step 1:** Cambiar `"8095:8090"` → `"8090:8090"`.
- [ ] **Step 2:** Verificar que no haya otro servicio en host 8090 en el mismo compose (`rg '8090' docker-compose.yml`).

---

### Task 2: Context server — preservar contexto en PUT parcial

**Files:**
- Modify: `data_space/context_server/main.py`
- Modify: `data_space/context_server/tests/test_context_server.py`

El PUT actual borra todo el modelo. Necesitamos poder actualizar schemas/descriptor/examples **sin** borrar `context/`.

- [ ] **Step 1:** Extender `ModelIn` con `preserveContext: bool = False`. Si `True`, `_write_model` no borra ni reescribe `context_dir` (aunque `context` sea null).
- [ ] **Step 2:** Test: PUT con modelo completo; PUT con `preserveContext=True`, `context=null`, nuevos schemas; GET sigue teniendo el context anterior.
- [ ] **Step 3:** `cd data_space/context_server && pytest tests/ -v` → PASS.

---

### Task 3: Refactor backend — `context_server_proxy.py` + `model_package.py`

**Files:**
- Create: `modelador/backend/context_server_proxy.py`
- Create: `modelador/backend/model_package.py`
- Modify: `modelador/backend/main.py`

- [ ] **Step 1:** Extraer bloque context-server (helpers + rutas) a `APIRouter(prefix="/api/context-server")` en `context_server_proxy.py`. Exportar `persist_model_to_context_server(tenant, model, *, preserve_context=False)` y `context_server_public_base() -> str` leyendo `CONTEXT_SERVER_PUBLIC_URL` (default `http://context-server:8090`).
- [ ] **Step 2:** Extraer `upload_model_package` a `model_package.py` con router. Al persistir:
  - si `tenant` y hay contexto en el zip **y** no hay query `context_url` externa → persistir context + devolver `contextUrl` estable;
  - si `tenant` y query `context_url` → persistir con `preserveContext=True` y `context=null` (no materializar); devolver `contextUrl` = la externa;
  - campo respuesta `persisted`, `contextUrl`.
- [ ] **Step 3:** En `main.py`, `app.include_router(...)` y eliminar código duplicado.
- [ ] **Step 4:** Ajustar frontend `uploadModelPackage(file, tenant?, contextUrl?)` para pasar `context_url` query si aplica.

---

### Task 4: Frontend — persistencia selectiva + URL estable + aviso

**Files:**
- Modify: `modelador/frontend/src/hooks/useModel.ts`
- Modify: `modelador/frontend/src/api/model.ts`
- Modify: `modelador/frontend/src/api/contextServer.ts` (si hace falta flag `preserveContext` en save)

- [ ] **Step 1:** `saveTenantModel(tenant, model, { preserveContext?: boolean })` envía `preserveContext` en el body.
- [ ] **Step 2:** `onLoadUrls`: si hay `contextUrl`, `preserveContext: true` y no enviar `context` al PUT (o enviar null + flag). Mantener context en el JSON local para UI. Añadir status note de referencia externa.
- [ ] **Step 3:** `onUploadPackage`: si `packageContextUrl` → no materializar context, persistir resto con preserveContext, `contextUrl` = externa + aviso. Si no → zip solo; tras persistir, `contextUrl` = `${publicBase}/tenants/${tenant}/context.jsonld` (publicBase desde config endpoint o constante documentada; añadir `GET /api/context-server/config` con `publicBaseUrl`).
- [ ] **Step 4:** Extender `/api/context-server/config` → `{ enabled, publicBaseUrl }`.

---

### Task 5: Borrado de conexión con confirmación

**Files:**
- Modify: `modelador/frontend/src/hooks/useBroker.ts`
- Preferir `ConfirmModal` existente si el flujo UI lo permite; si `onDelete` es sync desde lista, `window.confirm` es aceptable según spec.

- [ ] **Step 1:** Si otras conexiones comparten tenant → no llamar `deleteContextTenant`; status: conexión eliminada, tenant X persiste porque otra conexión lo usa.
- [ ] **Step 2:** Si es la última → `confirm("¿Eliminar también el espacio del tenant \"X\" en el servidor de contexto?...")`. Sí → delete; No → solo quitar conexión y avisar que el tenant persiste.

---

### Task 6: Reachability A+B (StatusBar + bloqueo)

**Files:**
- Create: `modelador/frontend/src/lib/contextReachability.ts`
- Modify: `modelador/frontend/src/components/StatusBar.tsx`
- Modify: `modelador/frontend/src/hooks/useAppStatus.ts` o `App.tsx` para pasar estado
- Modify: `modelador/frontend/src/pages/entities/EntitiesPage.tsx` / create-save paths

- [ ] **Step 1:** `probeContextUrl(url): Promise<boolean>` vía `fetchViaProxy` o endpoint ligero. `useContextReachability(url | null)` con checks on mount, on url change, visibilitychange, interval 60s.
- [ ] **Step 2:** StatusBar muestra punto/texto "contexto: ok|no alcanzable|—" .
- [ ] **Step 3:** Antes de POST/PATCH entidad, si `contextUrl` y `reachable === false`, abortar con mensaje.

---

### Task 7: Docs + cleanup data_space

**Files:**
- Modify: `data_space/docker/README.md`
- Modify: `data_space/context_server/README.md`
- Move: `post_fixed_entities.py`, `reload_clean.py`, `reset_and_reload.py` → `data_space/scripts/`
- Update imports/paths en esos scripts si referencian rutas relativas
- Modify: `modelador/.env.example` añadir `CONTEXT_SERVER_URL`, `CONTEXT_SERVER_PUBLIC_URL`

- [ ] **Step 1:** Mover scripts y arreglar paths.
- [ ] **Step 2:** README docker → compose raíz.
- [ ] **Step 3:** README context_server → tabla persistencia + URLs docker/host + nota IoT Agent.
- [ ] **Step 4:** `.env.example` del modelador.

---

### Task 8: Verificación

- [ ] **Step 1:** `cd data_space/context_server && pytest tests/ -v`
- [ ] **Step 2:** Tests frontend relevantes si existen (`useAppStatus`, etc.) — ajustar mocks a `modelStore` si rompen.
- [ ] **Step 3:** Actualizar estado del spec a "aprobado / implementado".

---

## Spec coverage check

| Spec item | Task |
|---|---|
| Persistencia selectiva contexto | 2, 3, 4 |
| URL estable solo-zip | 3, 4 |
| Checks A+B | 6 |
| Confirm borrado tenant | 5 |
| Puerto 8090 | 1 |
| Docs + scripts | 7 |
| Refactor main.py | 3 |
| No tocar context-provider | — |
