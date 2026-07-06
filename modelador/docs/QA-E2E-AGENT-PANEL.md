# QA — Guion E2E manual (rama estable → pruebas)

Rama estable de referencia: `feature/agent-panel-sidebar` / `dev` (mismo HEAD tras merge).  
Rama de trabajo QA: `test/qa-e2e-agent-panel`.

## Entorno mínimo

| Componente | Uso en pruebas |
|------------|----------------|
| Modelador (Docker o `backend` + `frontend dev`) | UI bajo prueba |
| Kong + Keycloak | Login Orion (obligatorio para RAG, Marvin texto, Viz Orion, Entidades) |
| Orion-LD vía Kong | Instancias y grafos |
| Agente LLM (`CHAT_LLM_URL`) | Opcional: Conectar + chat Marvin |
| RAG | Opcional: panel Documentación con sesión activa |
| AEA (`AEA_WS_URL`) | Opcional: micrófono Marvin |

Variables útiles: ver `.env.docker.example` (`CHAT_LLM_URL`, `CHAT_LLM_CONNECT_URL`, `ORION_AUTH_REQUIRED=true`).

---

## Automatizado hoy (referencia)

| Capa | Qué cubre | Qué **no** cubre (huecos de esta entrega) |
|------|-----------|------------------------------------------|
| Pytest | Proxy, validate, graph, upload, prepare-payload | `POST /api/connect`, auth Keycloak con sesión real |
| Vitest | `orionSessionEvents`, `orion-entities`, EntityList, parsers | Marvin, `useAppStatus`, BrokerCard form |
| Playwright (51) | Nav, config básica, entities UI, viz sin broker | Panel Marvin, auth Kong, caducidad sesión, `/api/connect` |
| `orion-integration` (4, `ORION_E2E=1`) | Listado proxy, viz Orion, CRUD E2EThing | Keycloak, tenant, Marvin, RAG, refresh grafo |

Comandos:

```bash
cd backend && python -m pytest tests/ -q
cd frontend && npm test
cd frontend && npm run test:e2e
cd frontend && ORION_E2E=1 npm run test:e2e:orion   # requiere Orion; ver nota Keycloak abajo
```

**Nota:** `orion-integration.spec.ts` asume Orion directo (`:1026`) y botón «Comprobar»; con Kong/Keycloak hay que adaptar seed (tenant + login) o ejecutar el guion manual.

---

## Guion E2E manual

Marcar: ✅ OK · ⚠️ Parcial · ❌ Fallo · ➖ N/A (servicio no disponible).

### A. Configuración — Broker y sesión

| ID | Paso | Resultado esperado | Dueño si falla |
|----|------|-------------------|----------------|
| A1 | Guardar conexión (URL Kong, tenant, nombre) sin credenciales | Aparece en lista; StatusBar muestra broker | front |
| A2 | Pulsar **Conectar** con usuario/contraseña Keycloak válidos | Mensaje éxito; StatusBar «sesión iniciada»; badges «logueado» en lista | front / back |
| A3 | Tras conectar, si `CHAT_LLM_URL` configurado | Mensaje menciona preparación agente (o aviso si LLM caído) | back / infra |
| A4 | **Cerrar sesión** en una conexión guardada | StatusBar «sin sesión»; Marvin bloqueado | front |
| A5 | **Desactivar** conexión activa | Sin broker activo; Viz Orion pide Configuración | front |
| A6 | Cambiar de conexión/tenant en lista | Historial Marvin reiniciado (mensaje sistema) | front |

### B. Sesión caducada (regresión auth)

| ID | Paso | Resultado esperado | Dueño si falla |
|----|------|-------------------|----------------|
| B1 | Con sesión activa, esperar caducidad refresh (Keycloak) o reiniciar BFF | Tras ≤90s o cambiar pestaña: StatusBar «sin sesión» | front / back |
| B2 | Sin recargar F5: abrir Visualización → Orion | Error conexión o vacío; coherente con sin sesión | front |
| B3 | Mismo estado: panel Marvin | Input deshabilitado; aviso «Conecta Orion» | front |
| B4 | Mismo estado: RAG (sidebar) | Panel bloqueado / sin operaciones | front |
| B5 | Enviar mensaje Marvin con sesión ya caducada | Error 401 y reinicio historial con aviso | front / back |

### C. Entidades

| ID | Paso | Resultado esperado | Dueño si falla |
|----|------|-------------------|----------------|
| C1 | Crear entidad (tipo con ejemplo en modelo) | Textarea altura estable; checkbox QL no roba mitad del panel | front |
| C2 | Duplicar entidad | Panel create; payload con `-copy` en id | front |
| C3 | Editar atributos (PATCH) | Barra info tras carga; validar/guardar | front / back |
| C4 | Tras guardar relación (ej. `operator` → otra entidad) | Listado actualizado | front / back |
| C5 | **Ver en visualización** desde editor | Navega a Viz; foco entidad (si existe en grafo) | front |

### D. Visualización

| ID | Paso | Resultado esperado | Dueño si falla |
|----|------|-------------------|----------------|
| D1 | Tab Schema con modelo cargado | Grafo tipos; detalle al clic | front |
| D2 | Tab Instancias Orion: **Recargar** | Contador entidades/relaciones; nodos visibles | front / back |
| D3 | Filtro por tipo (desmarcar un tipo) | Nodos/aristas filtrados; barra sigue mostrando totales | front |
| D4 | Buscar entidad y seleccionar | Foco subgrafo; panel detalle | front |
| D5 | Tras editar relación en Entidades, Recargar en Orion | Nueva arista visible (o tipo vecino activo al foco) | front / back |
| D6 | Ventana estrecha / panel Marvin abierto | Modo apilado lista/detalle; filtros Orion en drawer | front |

### E. Marvin (agente)

| ID | Paso | Resultado esperado | Dueño si falla |
|----|------|-------------------|----------------|
| E1 | Sin sesión: abrir rail Marvin | Chat bloqueado; mensaje conectar | front |
| E2 | Con sesión: enviar texto | Respuesta markdown; bloques `data` si el LLM los envía | back / MCP |
| E3 | Bloque lista entidades en chat → **Abrir** | Navega a Entidades | front |
| E4 | Bloque JSON → **Abrir en editor** | Entidades en modo create | front |
| E5 | Micrófono (si AEA configurado) | Solo con sesión; transcripción/respuesta | infra / MCP |

### F. RAG

| ID | Paso | Resultado esperado | Dueño si falla |
|----|------|-------------------|----------------|
| F1 | Sin sesión: abrir sidebar RAG | Aviso conectar Orion | front |
| F2 | Con sesión: listar/subir documento | Operación OK o error de servicio claro | back / infra |
| F3 | Tras logout: sidebar RAG | Vuelve a bloqueado; docs no cargan | front |

---

## Registro de defectos

Copiar filas según haga falta.

| ID | Caso guion | Severidad | Dueño | Descripción | Evidencia | Rama/commit |
|----|------------|-----------|-------|-------------|-----------|-------------|
| DEF-001 | B3 | Alta | front | Marvin activo sin sesión Orion | captura + consola | |
| DEF-002 | | Media | back | | | |
| DEF-003 | | Baja | infra | | | |
| DEF-004 | | | MCP | Agente LLM no devuelve `data` | | |

**Severidad (sugerida)**

- **Alta:** bloqueo de flujo, datos corruptos, seguridad (acceso sin sesión).
- **Media:** funcionalidad degradada con workaround.
- **Baja:** UI menor, texto, accesibilidad.

**Dueño**

- **front** — React, CSS, estado cliente.
- **back** — FastAPI, proxy, `orion_auth`, `/api/connect`.
- **MCP** — agente LLM, contrato `data` / chat.
- **infra** — Kong, Keycloak, Orion, RAG, AEA, Docker, red.

---

## Ampliación Playwright (rama `test/qa-e2e-agent-panel`)

Incluido en esta rama:

- `frontend/e2e/auth-session.spec.ts` — 7 tests (mock de sesión; sin Keycloak).

Pendiente:

1. Extender `orion-integration.spec.ts` — tenant, botón **Conectar**, flujo Kong real.
3. `e2e/marvin-panel.spec.ts` — rail abre/cierra; placeholder con sesión simulada (route intercept).
4. Test Vitest ya añadido: `orionSessionEvents.test.ts`; valorar `useAppStatus` con fake timers.

Variables CI locales:

```bash
export E2E_KEYCLOAK_USER=...
export E2E_KEYCLOAK_PASSWORD=...
export E2E_KONG_URL=http://localhost:8010
export E2E_TENANT=...
```

---

## Cierre de la tarea

- [ ] Guion manual A–F ejecutado en entorno objetivo (Docker/Azure).
- [ ] Defectos registrados en tabla (o issue tracker) con severidad y dueño.
- [ ] Playwright ampliado **o** justificación de solo manual (p. ej. credenciales Keycloak en CI).
- [ ] `npm test` + `pytest` verdes en la rama de pruebas.
