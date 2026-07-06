# Sistema de Logging · Industrial MCP

Guía del sistema de logging centralizado del proyecto.

---

## 1. Cómo funciona

El sistema se compone de dos ficheros:

- **`config/logging_config.yaml`** — define qué se registra, dónde y con qué formato.
- **`src/engine/logging_setup.py`** — carga esa configuración y proporciona las funciones que usa el código para registrar eventos.

Al arrancar la aplicación (ya sea la API o el cliente terminal), se llama a `setup_logging()` una sola vez. A partir de ahí, todo el código del proyecto registra eventos automáticamente.

---

## 2. Ficheros de log generados

Todos se crean bajo `./var/logs/`, **cada uno en su propia subcarpeta** (`var/logs/app/`, `var/logs/errors/`, `var/logs/conversations/`, `var/logs/metrics/`), y rotan automáticamente cada medianoche.

| Fichero | Qué contiene | Formato | Retención |
|---|---|---|---|
| `app.log` | Todo el flujo del sistema: arranques, conexiones, peticiones, llamadas a tools, flujo entre agentes, resultados | Texto legible | 14 días |
| `errors.log` | Solo avisos y errores, con fichero y línea donde ocurrieron | Texto con ubicación de código | 30 días |
| `conversations.jsonl` | Cada pregunta del usuario y la respuesta del sistema, con estado y metadatos | JSON (una línea por turno) | 60 días |
| `metrics.jsonl` | Métricas de cada petición: tiempos, tokens consumidos, coste, tools usadas | JSON (una línea por petición) | 30 días |

### Ejemplo de línea en `app.log`

```
2026-04-16 10:08:04 [INFO   ] mcp.client [terminal_user/req_177633] Petición recibida │ modality=text │ len=86
2026-04-16 10:08:05 [INFO   ] mcp.tools  [terminal_user/req_177633] tool_call_ok │ orion_ld.describe_entity_schema │ 23.4ms │ args={...}
2026-04-16 10:08:06 [INFO   ] mcp.agent  [terminal_user/req_177633] Gestor → orion_ld │ Obtener velocidad de la cinta
2026-04-16 10:08:09 [INFO   ] mcp.agent  [terminal_user/req_177633] orion_ld ← Gestor │ 950ms │ Velocidad=1.58 m/s
2026-04-16 10:08:11 [INFO   ] mcp.client [terminal_user/req_177633] Petición OK │ 7.2s │ tokens=35/61=96 │ tools=5(err=1) │ $0.000648
```

### Ejemplo de línea en `conversations.jsonl`

```json
{
  "timestamp": "2026-04-16T10:08:11.123456",
  "question": "muestra la velocidad de la cinta",
  "answer": "Velocidad: 1.58 m/s",
  "status": "success",
  "modality": "text",
  "metadata": {"llm_calls": 0, "tools_called": 5, "tools_errors": 1}
}
```

### Ejemplo de línea en `metrics.jsonl`

```json
{
  "timestamp": "2026-04-16T10:08:11.123456",
  "request_id": "req_177633",
  "total_time": 7.2,
  "llm_time": 6.8,
  "tokens_total": 96,
  "tools_called": 5,
  "tools_errors": 1,
  "cost_usd": 0.000648,
  "status": "success"
}
```

---

## 3. Qué información se registra en cada nivel

| Nivel | Qué registra | Dónde aparece | Ejemplos |
|---|---|---|---|
| **DEBUG** | Detalles internos para desarrollo | Solo `app.log` si se baja el nivel del handler a DEBUG | Input completo de la petición, texto crudo cuando falla el parseo JSON, tracebacks de errores conocidos |
| **INFO** | Eventos normales del ciclo de vida | `app.log` + consola | Conexión a Azure, servidor MCP conectado, petición recibida, tool ejecutada, flujo gestor↔especialista, petición completada |
| **WARNING** | Situaciones anómalas pero recuperables | `app.log` + `errors.log` + consola | JSON fallback, content filter Azure, servidor sin herramientas, tool devolvió HTTP 4xx/5xx |
| **ERROR** | Fallos que afectan a una petición | `app.log` + `errors.log` + consola | Tool lanzó excepción, especialista agotó iteraciones, error del agente, fallo de conexión |
| **CRITICAL** | Fallos que afectan al sistema entero | `app.log` + `errors.log` + consola | Ningún servidor MCP disponible, excepciones no manejadas |

---

## 4. Contexto automático por petición

Cada línea de log incluye automáticamente `[session_id/request_id]` entre corchetes. Esto permite filtrar toda la traza de una petición concreta aunque haya peticiones concurrentes:

```bash
grep "req_177633" var/logs/app/app.log
```

El contexto se establece automáticamente al inicio de cada petición y se limpia al final. No requiere intervención manual.

---

## 5. Información registrada por tipo de evento

### Peticiones

| Campo | Descripción |
|---|---|
| `modality` | Tipo de entrada (text/speech) |
| `total_time` | Duración total de la petición |
| `llm_time` | Tiempo dedicado al LLM |
| `tokens_prompt / tokens_completion / tokens_total` | Tokens consumidos |
| `tools_called` | Número de herramientas MCP invocadas |
| `tools_errors` | Herramientas que devolvieron error |
| `cost_usd` | Coste estimado de la petición |
| `error_code` | Código si falló: `CONTENT_FILTER`, `MAX_ITERATIONS`, `AGENT_EXEC_ERR`, `JSON_RECOVERED` |

### Llamadas a tools

| Campo | Descripción |
|---|---|
| `server` | Servidor MCP (ej: `orion_ld`, `quantumleap`) |
| `tool` | Nombre de la herramienta (ej: `list_entities`) |
| `args` | Argumentos pasados |
| `result` | Respuesta completa de la herramienta |
| `duration_ms` | Tiempo de ejecución en milisegundos |
| `error` | Error si la tool falló |

Las tools que devuelven errores HTTP embebidos (ej: `❌ HTTP 400`) se registran como **WARNING** para facilitar su detección.

### Flujo entre agentes

Se registra la comunicación entre el Gestor (orquestador) y cada Especialista:

```
Gestor → orion_ld │ Obtener velocidad de la cinta transportadora
orion_ld ← Gestor │ 950ms │ Velocidad=1.58 m/s │ {'chars': 45}
```

---

## 6. Errores controlados

### JSON fallback

Cuando el LLM no devuelve JSON válido sino texto plano, el sistema lo recupera automáticamente. Se registra como WARNING con la causa del fallo y una preview del texto recibido para diagnosticar por qué no generó JSON.

### Content filter de Azure

Cuando Azure bloquea una petición por sus filtros de contenido, se registra como WARNING con el tipo de filtro activado (autolesión, violencia, odio, sexual).

### Límite de iteraciones

Cuando un agente especialista agota el máximo de iteraciones sin converger, se registra como ERROR con mensaje claro y el número de tools que llamó. El traceback completo se guarda solo en `errors.log`.

### Excepciones no manejadas

Si un error escapa de todos los `try/except`, el sistema lo captura automáticamente y lo registra como CRITICAL con traceback completo. Ningún fallo pasa desapercibido.

---

## 7. Banners de arranque y cierre

Cada vez que se arranca o cierra el sistema se registra un banner visual para localizar inicios de ejecución en logs largos:

```
════════════════════════════════════════════════════════════════════════════════
🚀 ARRANQUE │ API Gateway Industrial MCP │ FastAPI │ pid=12345 │ 2026-04-16 14:30:00 │ port=8081
════════════════════════════════════════════════════════════════════════════════
```

```
────────────────────────────────────────────────────────────────────────────────
🛑 CIERRE │ API Gateway │ lifespan finalizado │ 2026-04-16 15:00:00
────────────────────────────────────────────────────────────────────────────────
```

---

## 8. Logs de los servidores MCP

Los servidores MCP (`orion_server.py`, `quantumleap_server.py`, `rag_server.py`) no usan este sistema de logging. Cada servidor corre en un proceso separado y escribe sus mensajes a `stderr` con un prefijo propio (`[OrionLD]`, `[QuantumLeap]`, `[RAG-Server]`).

Estos mensajes aparecen en la consola donde se ejecuta la aplicación, pero no se guardan en `app.log`. `stdout` está reservado para el protocolo MCP y no se puede usar para logs.

---

## 9. Configuración

### Variables de entorno

| Variable | Descripción | Default |
|---|---|---|
| `LOG_CFG` | Ruta al YAML de configuración | `config/logging_config.yaml` |
| `LOG_LEVEL` | Nivel usado si no hay YAML | `INFO` |
| `LOG_DIR` | Directorio de logs | `./logs` |

### Jerarquía de loggers

```
mcp                    ← padre del proyecto (consola + app.log + errors.log)
├── mcp.client         ← cliente MCP principal
├── mcp.api            ← endpoints FastAPI
├── mcp.servers        ← gestión de servidores
├── mcp.tools          ← llamadas a herramientas MCP
├── mcp.agent          ← flujo gestor ↔ especialistas
├── mcp.conversations  ← Q&A (aislado → conversations.jsonl)
├── mcp.metrics        ← métricas (aislado → metrics.jsonl)
└── mcp.uncaught       ← excepciones no manejadas
```

Los loggers `mcp.conversations` y `mcp.metrics` están **aislados**: sus mensajes solo van a sus ficheros JSON, sin aparecer en `app.log`.

El resto de loggers **propagan** al padre `mcp`, por lo que aparecen automáticamente en `app.log`, `errors.log` y consola.

### Librerías terceras silenciadas

`httpx`, `httpcore`, `openai`, `llama_index`, `urllib3`, `uvicorn.access`, `asyncio` — solo se ven sus errores graves.

### Fallback si no hay YAML

Si `logging_config.yaml` no existe o PyYAML no está instalado, el sistema aplica automáticamente una configuración básica con consola + `app.log` + `errors.log`. El sistema nunca queda sin logs.

---

## 10. Cómo añadir un nuevo logger

En cualquier módulo nuevo del proyecto:

```python
from logging_setup import get_logger
logger = get_logger("mcp.mi_modulo")

logger.info("evento normal")
logger.warning("algo inesperado")
logger.error("fallo", exc_info=True)
```

No es necesario declarar `mcp.mi_modulo` en el YAML. Al ser hijo de `mcp`, hereda automáticamente sus handlers y nivel.

---

## 11. Cómo añadir un nuevo fichero de log

Ejemplo: crear un fichero `audit.log` para auditoría.

**1. Añadir el handler en `logging_config.yaml`:**

```yaml
handlers:
  file_audit:
    class: logging.handlers.TimedRotatingFileHandler
    level: INFO
    formatter: standard
    filename: audit.log
    when: midnight
    backupCount: 90
    encoding: utf-8
    filters: [context_filter, redact_filter]
```

**2. Añadir el logger:**

```yaml
loggers:
  mcp.audit:
    level: INFO
    handlers: [file_audit]
    propagate: false    # Aislado: solo va a audit.log
```

**3. Usar en el código:**

```python
audit = get_logger("mcp.audit")
audit.info("Usuario %s accedió a %s", user_id, recurso)
```

---

## 12. Análisis de logs JSON

Los ficheros `.jsonl` se cargan directamente con pandas:

```python
import pandas as pd

conv = pd.read_json("logs/conversations.jsonl", lines=True)
metrics = pd.read_json("logs/metrics.jsonl", lines=True)

# Tasa de error
conv.groupby("status").size()

# Coste acumulado por día
metrics["date"] = pd.to_datetime(metrics["timestamp"]).dt.date
metrics.groupby("date")["cost_usd"].sum()

# Peticiones más lentas
metrics.nlargest(10, "total_time")[["request_id", "total_time", "tokens_total", "tools_called"]]
```

---

## 13. Estructura de ficheros

```
proyecto/
├── logging_config.yaml       # Configuración declarativa
├── logging_setup.py          # Módulo de logging (clases + funciones)
├── api_server.py             # Propaga contexto de petición
├── clients/
│   └── mcp_client.py         # Registra toda la lógica de negocio
├── servers/                  # Sistema separado (stderr)
│   ├── orion_server.py
│   ├── quantumleap_server.py
│   └── rag_server.py
└── logs/                     # Generado automáticamente
    ├── app.log
    ├── errors.log
    ├── conversations.jsonl
    └── metrics.jsonl
```
