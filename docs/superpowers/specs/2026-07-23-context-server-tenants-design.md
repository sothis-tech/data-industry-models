# Context server multi-tenant — diseño de cierre

Fecha: 2026-07-23  
Rama: `feature/context-server-tenants`  
Estado: implementado (2026-07-23) — ver plan en `docs/superpowers/plans/2026-07-23-context-server-tenants.md`

## Objetivo

Completar la WIP del servidor de contexto multi-tenant (`data_space/context_server`) como fuente de verdad del modelo NGSI por tenant, con reglas claras de persistencia del contexto, ciclo de vida al borrar conexiones, URL estable HTTP para Orion/IoT Agent/simulador, documentación, puerto unificado, limpieza menor en `data_space` y primera extracción de módulos en `modelador/backend/main.py`.

No se toca el servicio `context-provider` (nginx estático del compañero).

## Contexto (AS-IS de la WIP)

Ya existe:

- API FastAPI en `data_space/context_server` con carpetas `<TENANTS_ROOT>/<tenant>/{context,schemas,examples,descriptor.json,meta.json}`
- Proxy en el backend del modelador (`/api/context-server/...`)
- Frontend: `modelStore`, alta de tenant al conectar/guardar, baja al eliminar conexión, migración legacy `ngsi_model` → servidor
- Servicio en docker-compose maestro

## Decisiones de diseño

### Identidad del espacio

Un **tenant** (mismo string que Orion/RAG) = una carpeta en el context server. Varias conexiones del modelador pueden compartir tenant (misma URL de Kong distinta + mismo tenant, etc.); comparten el mismo modelo en disco.

### Persistencia del modelo

**Regla:** cada carga sustituye el contenido del tenant. Si hay conflicto zip vs URL sobre el mismo dato (p. ej. contexto), **gana la URL**.

| Entrada | Persistido en disco del tenant | `@context` usado en payloads / servicios |
|---|---|---|
| Solo URLs | schemas + descriptor + examples. Sin `context/` en disco | URL externa (`meta.contextUrl`) |
| Solo zip | Todo, incluido `context/context.jsonld` | URL estable del context server |
| Zip + URL de contexto | schemas + descriptor + examples del zip; sin `context/` (URL gana) | URL externa |

En memoria del modelador se puede cachear el JSON del contexto descargado para UI/validación aunque no esté en disco del context server.

### URL estable (solo tras zip con contexto materializado)

Tras persistir solo-zip con tenant activo, el modelador fija `contextUrl` a la URL **canónica en red Docker** (mismo criterio que `http://context-provider/...`):

```text
http://context-server:8090/tenants/<tenant>/context.jsonld
```

Configurable con env opcional `CONTEXT_SERVER_PUBLIC_URL` (default `http://context-server:8090`) si en algún despliegue el hostname cambia.

- Orion / IoT Agent / simulador **dentro de Docker** usan esa URL directamente.
- Desde el **host**, la documentación menciona el equivalente `http://localhost:<puerto-publicado>/tenants/<tenant>/context.jsonld` (p. ej. `8095` si el host 8090 está ocupado). El modelador en navegador, si necesita leer el JSON-LD, lo hace vía proxy del backend (como ya hace con contextos localhost), no asumiendo que el browser resuelve `context-server`.

El endpoint `GET /tenants/{tenant}/context.jsonld` ya existe. No se añade nginx delante en esta iteración. No se registra el contexto en Orion (`jsonldContexts`): eso no sustituye una URL fetcheable por el IoT Agent.

### Aviso y comprobación de contexto externo (solo URLs / zip+URL)

Aplica cuando el modelo tiene `contextUrl` que **no** es la URL del context server del tenant (referencia externa).

1. **Al cargar:** mensaje informativo de que el contexto es referencia externa y debe seguir alcanzable.
2. **StatusBar (B):** comprobar alcanzabilidad vía proxy del backend:
   - al montar / cuando cambie `contextUrl` o el tenant;
   - al evento `visibilitychange` (volver a la pestaña);
   - cada ~60s mientras la pestaña esté visible.
   Indicador en StatusBar: ok / no alcanzable.
3. **Al operar (A):** al crear/editar entidad o preparar payload hacia Orion, si la URL externa no responde, error bloqueante con mensaje claro.

Combinación acordada: **C = A + B**. Si `contextUrl` es la del propio context server, el check usa esa URL (también detecta tenant sin contexto o servicio caído).

### Ciclo de vida al borrar una conexión Orion

- **Quedan otras conexiones con el mismo tenant:** no borrar el espacio. Mensaje: se eliminó la conexión; el tenant persiste porque otra conexión lo usa.
- **Era la última conexión con ese tenant:** `confirm()` antes de borrar el espacio. Sí → conexión + carpeta del tenant; No → solo conexión, el tenant permanece en el servidor.

### Docker / data_space

- Publicar context-server: interno `:8090`; en host preferir `8090:8090` si está libre, o `8095:8090` si choca (p. ej. con otros servicios).
- `data_space/docker/`: README indicando usar el compose raíz.
- Mover scripts sueltos de la raíz de `data_space` (`post_fixed_entities.py`, `reload_clean.py`, `reset_and_reload.py`) a `scripts/`.
- Documentar en README del context server (y referencia desde modelador) la tabla de persistencia y las URLs.
- **No** modificar `context-provider`.

### Primera refactor de `modelador/backend/main.py`

Extraer sin cambiar comportamiento:

1. `context_server_proxy.py` — rutas `/api/context-server/*` y helper de persistencia
2. `model_package.py` — `/api/upload/model-package`

`main.py` registra los routers. Resto de dominios (Orion, RAG, chat, graphs) en iteraciones posteriores.

## Fuera de alcance

- Nginx delante del context server o fusión con `context-provider`
- Eliminar fallback `localStorage` legacy (`ngsi_model` sin tenant)
- API granular por entidad (`/schemas/{Entidad}`)
- Cambiar el default del simulador/IoT Agent al context server (solo documentar la URL)
- Borrado remoto del tenant desde un botón dedicado distinto del flujo de conexiones (salvo el confirm del caso última conexión)

## Criterios de aceptación

1. Carga solo-URLs con tenant: persiste schemas/descriptor/examples; **sin** `context/` en disco (sustituye carga anterior); `contextUrl` externa en meta; StatusBar refleja alcanzabilidad; operar con URL caída bloquea con error.
2. Carga solo-zip con tenant: persiste contexto; `contextUrl` pasa a la URL estable del context server; `GET` a esa URL devuelve el JSON-LD.
3. Zip + URL: no materializa context del zip (URL gana); usa URL externa; mismos checks A+B.
4. Borrar conexión con otras que comparten tenant: no borra carpeta; mensaje explicativo.
5. Borrar última conexión: confirmación; cancelar deja el tenant; aceptar lo elimina.
6. Puerto host publicado (p. ej. `8095:8090` si 8090 del host está ocupado); `CONTEXT_SERVER_URL` interno sigue en `http://context-server:8090`.
7. Scripts movidos; README docker actualizado; tabla de prioridad documentada.
8. Backend: lógica de context-server y upload de paquete fuera de `main.py` en módulos propios; tests del context server siguen pasando.

## Notas para el compañero (IoT Agent / simulador)

El `context-provider` (nginx) resolvía “ruta de fichero vs URL HTTP”. El context server **también** expone URL HTTP. Ejemplo en red Docker:

`http://context-server:8090/tenants/ibermot/context.jsonld`

Requisito: el tenant debe tener contexto cargado (zip). Si falla en la práctica con el IoT Agent, se valorará nginx delante en una iteración posterior; no se asume necesario a priori.
