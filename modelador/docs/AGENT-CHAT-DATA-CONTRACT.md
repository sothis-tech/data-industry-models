# Contrato `data` del chat Marvin (modelador ↔ agente LLM)

Documento para alinear el **frontend del modelador** con el **agente LLM / AEA**. El texto de respuesta sigue yendo en `text` (markdown); el campo **`data`** alimenta bloques de UI (tablas, JSON, grafo).

## Conexión del agente por tenant (`POST /api/connect`)

Al pulsar **Conectar** en Configuración (tras login Orion OK), el BFF del modelador llama al agente LLM:

- **Front → BFF:** `POST /api/connect` con `{ "ngsild_tenant": "<tenant>", "broker_base_url": "<kong>" }`
- **BFF → agente:** mismo path en el host de `CHAT_LLM_URL` (o `CHAT_LLM_CONNECT_URL`), con cabeceras Orion de la sesión HTTP-only.

Respuesta esperada (ejemplo): `status`, `tenant`, `orion`, `rag`, `quantumleap`. El agente puede precargar schemas y estado RAG para ese tenant antes del chat.

El historial de Marvin en el navegador se reinicia al cambiar tenant/conexión activa (independiente de este endpoint).

## Flujo

1. El usuario escribe en Marvin (o usa voz → AEA → mismo agente).
2. El BFF (`POST /api/chat/text`) reenvía al LLM (el campo `context` de UI está desactivado en el front hasta que el agente lo use).
3. La respuesta normalizada incluye `text`, `speech` y **`data`**.
4. El frontend ejecuta `parseChatBlocks(data)` y renderiza bloques bajo el markdown.

Referencia backend: `_extract_chat_response` en `backend/main.py`.  
Referencia frontend: `frontend/src/lib/chatBlocks.ts`.

## Formas soportadas de `data`

### 1. Lista de entidades

```json
{
  "entities": [
    {
      "id": "urn:ngsi-ld:Device:001",
      "type": "Device",
      "name": { "type": "Property", "value": "Sensor A" }
    }
  ]
}
```

Alias: `entity_list`, `items`, o bloque explícito:

```json
{
  "blocks": [
    { "kind": "entity-list", "entities": [ { "id": "...", "type": "..." } ] }
  ]
}
```

**UI:** tabla con botón *Abrir* → vista Entidades.

### 2. Entidad / payload JSON-LD

```json
{
  "entity": {
    "id": "urn:ngsi-ld:Horno:1",
    "type": "Horno",
    "name": { "type": "Property", "value": "Horno 1" }
  }
}
```

Alias: `payload`, `ngsi_ld`, o `{ "kind": "json", "value": { ... } }`.

**UI:** bloque JSON con *Copiar* y *Abrir en editor* (crear entidad).

### 3. Grafo de relaciones (sencillo)

```json
{
  "graph": {
    "nodes": [
      { "id": "urn:ngsi-ld:A:1", "label": "A" },
      { "id": "urn:ngsi-ld:B:1", "label": "B" }
    ],
    "edges": [
      { "source": "urn:ngsi-ld:A:1", "target": "urn:ngsi-ld:B:1", "label": "monitors" }
    ]
  }
}
```

Alias: `nodes` + `edges` en la raíz de `data`, o solo `relationships`:

```json
{
  "relationships": [
    { "source": "urn:ngsi-ld:A:1", "target": "urn:ngsi-ld:B:1", "label": "ref" }
  ]
}
```

**UI:** SVG circular con nodos y aristas.

### 4. Varios bloques

```json
{
  "blocks": [
    { "kind": "entity-list", "entities": [] },
    { "kind": "json", "title": "Propuesta", "value": {} },
    { "kind": "graph", "nodes": [], "edges": [] }
  ]
}
```

## Contexto enviado al LLM (`POST /api/chat/text`) — desactivado en UI

> El modelador **no envía** `context` desde el panel Marvin por ahora. Referencia para cuando se reactive.

Si se reactivara *Incluir contexto*, el body podría incluir:

```json
{
  "message": "...",
  "context": {
    "route": "/entidades",
    "route_label": "Entidades",
    "entity_panel": "edit",
    "entity_id": "urn:ngsi-ld:...",
    "entity_type": "Device",
    "entity_label": "Sensor A",
    "draft_kind": "attrs",
    "json_draft": { }
  }
}
```

El agente puede usar esto para respuestas acotadas al estado de la UI.

## Acciones en bloques del chat → vistas del modelador

| Bloque | Acción | Destino |
|--------|--------|---------|
| Lista de entidades | *Abrir* | `/entidades` + edición de la entidad (`AGENT_OPEN_ENTITY`) |
| Lista / JSON (con URN) | *Ver relaciones* | `/visualizacion` + foco Orion (`AGENT_OPEN_VIZ_ENTITY`) |
| JSON / entidad | *Abrir en editor* | `/entidades` + alta con payload normalizado (`AGENT_APPLY_ENTITY`) |
| JSON | *Copiar JSON* | Portapapeles (sin cambiar de vista) |
| Grafo en `data` | *Ver en visualización* | Igual que *Ver relaciones* |

El editor de Entidades sigue enviando `json_draft` al LLM vía contexto cuando *Incluir contexto* está activo.

## Visualización Orion-LD desde bloques `data` (chat)

Solo si Marvin devuelve `data` estructurado (no texto libre):

| Bloque `data` | Botón en UI |
|---------------|-------------|
| `entities` / lista | *Abrir* → Entidades; *Ver relaciones* → Visualización Orion |
| `entity` / `json` | *Abrir en editor*; *Ver relaciones* (si hay `id` URN) |
| `graph` | *Ver en visualización* (nodo central del grafo) |

Entidades → Visualización: botón **Ver en visualización** en el editor (mismo efecto que elegir un resultado del buscador Orion).

## Ciclo de vida del historial del chat

| Acción | ¿Se pierde el historial? |
|--------|-------------------------|
| Cambiar vista (Configuración / Entidades / Visualización) | No |
| Cerrar o redimensionar el panel Marvin | No |
| Cerrar sesión Orion (logout / tenant desconectado) | **Sí** — se reinicia mensajes y `session_id` |
| Cambiar de conexión o tenant en Configuración | **Sí** |
| Recargar la página (F5) | **Sí** (estado en memoria; persistencia entre recargas pendiente de definir) |

Al reiniciar por desconexión se muestra un mensaje de sistema y se cierra la voz activa si la hubiera.
