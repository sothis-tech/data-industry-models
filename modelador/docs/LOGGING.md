# Logs y errores (JSON)

Referencia rápida de cómo se registran eventos y errores en backend (FastAPI) y frontend (React).

---

## Backend (`backend/`)

### Formato

- Por defecto cada línea de log es un **objeto JSON** (una línea = un evento), adecuado para Loki, CloudWatch, ELK, etc.
- Variable de entorno **`LOG_FORMAT=text`**: formato legible en consola (útil en desarrollo local sin agregador).

### Nivel (`LOG_LEVEL`)

- Variable **`LOG_LEVEL`**: `DEBUG`, `INFO`, `WARNING` (o `WARN`), `ERROR`, `CRITICAL`. Por defecto **`INFO`**.
- Valores desconocidos se tratan como **INFO**.
- Afecta al logger raíz y a **uvicorn** / **uvicorn.access** / **uvicorn.error** (mismo umbral).

### Dependencia

- `python-json-logger` (declarada en `requirements.txt`).

### Arranque

Al importar `main.py` se llama a `setup_logging()` en `logging_config.py`, que configura:

- el logger raíz y los loggers de **uvicorn** / **uvicorn.access** / **uvicorn.error** con el mismo handler.

### Qué se registra

| Origen | Contenido |
|--------|-----------|
| **`modelador.api`** | Tras cada petición HTTP: `event=http_request`, `method`, `path`, `status_code`, `duration_ms`. |
| **`modelador.api`** | Si ocurre una excepción no manejada: `event=unhandled_exception`, `path`, `method`, más traza en el campo estándar de excepción del JSON. |
| **Uvicorn** | Mensajes de arranque y líneas de acceso en el mismo formato (JSON o texto). |

### Respuesta HTTP ante fallos internos

Las excepciones no capturadas devuelven **JSON** al cliente:

```json
{
  "detail": "Error interno del servidor",
  "error_code": "internal_error"
}
```

Los `HTTPException` y errores de validación de FastAPI siguen usando el formato habitual (`detail`, etc.).

---

## Frontend (`frontend/src/`)

### Módulo `lib/logger.ts`

- Emite **una línea JSON** por llamada: `ts`, `level`, `service` (`modelador-web`), `msg`, y campos extra que pases.
- Consola del navegador: `console.info` / `warn` / `error` / `debug` con la cadena JSON (filtrable en DevTools).

### Nivel (`VITE_LOG_LEVEL`)

- **`VITE_LOG_LEVEL`**: `debug`, `info`, `warn` (o `warning`), `error`. Por defecto **`info`** (solo se emiten `info`, `warn` y `error`; no `debug`).
- Con **`debug`** se muestran todos los niveles.

### Modo texto en desarrollo

En `.env.local` (no commitear) o entorno Vite:

```env
VITE_LOG_FORMAT=text
VITE_LOG_LEVEL=debug
```

`VITE_LOG_FORMAT=text` solo en **`import.meta.env.DEV`**: mensajes más legibles; en build de producción sigue siendo JSON.

### Dónde se usa ya

- **`lib/http.ts`**: fallos al parsear JSON (`event=http_read_json_failed`) y errores de red (`event=http_network_error` vía `networkError`).
- **`api/graph.ts`**: errores HTTP y excepciones en llamadas a `/api/graph/*` y vista de entidad (`event=graph_*`).

Puedes importar `log` en más módulos (`log.info`, `log.warn`, `log.error`) con el mismo patrón.

---

## Cómo ver los logs

**API:** ejecuta Uvicorn y observa la salida estándar; con `LOG_FORMAT=json` cada línea es parseable con `jq` u otras herramientas.

**React:** abre DevTools → pestaña Consola; cada mensaje estructurado es un string JSON.

---

## Archivos relevantes

| Archivo | Rol |
|---------|-----|
| `backend/logging_config.py` | Configuración de logging y formato JSON/texto. |
| `backend/main.py` | Middleware de petición, manejador global de excepciones. |
| `frontend/src/lib/logger.ts` | API de logging JSON del cliente. |
