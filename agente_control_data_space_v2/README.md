# Agente de Control de Activos Industriales

Sistema de Inteligencia Artificial Multi-Agente basado en el protocolo MCP
(Model Context Protocol) y LlamaIndex. Permite consultar y gestionar activos
industriales mediante lenguaje natural, coordinando múltiples fuentes de datos
a través de una arquitectura jerárquica de agentes especializados.

---

## Arquitectura

El sistema resuelve los problemas de alucinación y saturación de contexto
mediante la especialización de agentes. Un **Agente Gestor** actúa como
orquestador y punto único de contacto con el usuario; nunca accede directamente
a los datos. En su lugar, delega cada tarea en el **Agente Especialista**
adecuado, que dispone únicamente de las herramientas necesarias para su dominio.

```
Usuario
  │
  ▼
Agente Gestor (Orquestador)
  ├── Agente Orion-LD       → Context Broker NGSI-LD (entidades, consultas)
  ├── Agente RAG Knowledge  → Manuales técnicos y documentación (PDFs)
  ├── Agente MongoDB        → Base de datos documental, logs e historial
```

Cada agente especialista se lanza como un proceso independiente bajo demanda
mediante comunicación STDIO (stdin/stdout), garantizando aislamiento total y
eliminando conflictos de puertos.

---

## Estructura del proyecto

El proyecto separa el **motor reutilizable** (`src/engine/`) de lo **específico
del proyecto** (`src/project/`, `config/`, `src/servers/`). El código vive bajo
`src/` y se importa con nombres limpios (`engine.*`, `project.*`, …) gracias a
tener `src/` en el `PYTHONPATH`. Los datos de runtime se agrupan bajo `var/`.

```
agente_control_data_space/
├── src/                          ← TODO el código importable (PYTHONPATH=src)
│   ├── engine/                       MOTOR reutilizable (NO se toca entre proyectos)
│   │   ├── client.py                 (procesar_peticion_api, agentes, anti-evasión, reconcile)
│   │   ├── response_processing.py    (_to_text, build_response_payload)
│   │   ├── metrics.py                (PRICING + token_tracker + colector)
│   │   ├── logging_setup.py
│   │   └── validators.py             (registro genérico: validadores/prompts/dodge/reconcile)
│   ├── project/                      ESPECÍFICO del proyecto (se reescribe por proyecto)
│   │   ├── __init__.py               (al importarse REGISTRA todo en el motor)
│   │   ├── guardrails.py             (TODAS las reglas NGSI-LD, @register_validator)
│   │   ├── behavior_guards.py        (is_dodge + DODGE_RETRY_SUFFIX + reconcile_token_metrics)
│   │   ├── prompts.py                (system prompts del dominio)
│   │   └── chart_builder.py          (helper de gráficos del proyecto de las gafas)
│   ├── servers/                      MCPs (se activan/desactivan desde config/)
│   │   ├── orion_server.py  quantumleap_server.py  rag_server.py
│   │   └── chart_engine_server.py  mongodb_server.py  sparkplug_server.py
│   ├── interfaces/                   puntos de arranque del cliente
│   │   ├── api.py                    (API FastAPI)
│   │   └── cli.py                    (REPL de terminal)
│   └── utils/
│       └── chart_outputs/            (buffer temporal de gráficos — middleware gafas)
├── config/                       TODAS las configuraciones
│   ├── config.yaml  config.local.yaml  config_docker.yaml
│   ├── logging_config.yaml  .env
│   └── providers/  azure.yaml  local.yaml  openai.yaml
├── tests/
│   ├── benchmark.py
│   └── smoke_test.py             (verifica arranque + separación)
├── var/                          DATOS en runtime, agrupados
│   ├── logs/
│   │   ├── app/            (app.log)
│   │   ├── errors/         (errors.log)
│   │   ├── conversations/  (conversations.jsonl)
│   │   └── metrics/        (metrics.jsonl)
│   └── results/            (resultados de benchmark .json)
├── manuales/                     (documentación fuente para RAG)
├── Dockerfile  docker-compose.yml
├── pyproject.toml  uv.lock  .python-version  .gitignore
└── README.md  LOGGING.md
```

### Regla de oro

`engine/` **no importa nada de `project/`**. El motor arranca y funciona aunque
`project/` esté vacío (modo básico: no rechaza tools, usa un prompt genérico,
sin anti-evasión). Es `project/` quien, al importarse, **registra** sus reglas
en `engine.validators` (patrón registro de validadores). Las interfaces y los
tests hacen `import project` al arrancar para activarlo todo. Para portar el
motor a otro proyecto se reescribe `project/` + `config/` + `servers/` **sin
tocar `engine/`**.

### Arranque (desde la raíz del proyecto)

El código vive en `src/`; ponlo en el `PYTHONPATH` antes de arrancar:

```bash
export PYTHONPATH=src        # una vez por shell (en Docker ya viene fijado)

# API (host, desarrollo)
uvicorn interfaces.api:app --host 0.0.0.0 --port 8082

# Terminal REPL
python -m interfaces.cli                              # config/config.local.yaml
python -m interfaces.cli --config config/config.local.yaml  # config "de Docker"
python -m interfaces.cli --tenant ibermot

# Benchmark
python tests/benchmark.py --config config/config.local.yaml --agent orion ql
python tests/benchmark.py --config config/config.local.yaml --tenant ibermot --level 1 2 3 --agent orion ql

# Smoke test (verifica que arranca y que la separación se respeta)
python tests/smoke_test.py
```

> Importante: arranca siempre desde la raíz `agente_control_data_space/`,
> porque los servidores MCP se lanzan con rutas relativas tipo
> `src/servers/orion_server.py`.

---

## Agentes disponibles

Todos los agentes se activan o desactivan con `enabled: true/false` en
`config.yaml`, sin necesidad de cambiar ningún otro fichero.

### Orion-LD
Conecta con el Context Broker NGSI-LD (Orion-LD). Expone herramientas de
consulta y exploración de entidades: tipos disponibles, atributos, historial
temporal, suscripciones y registros. Incluye descubrimiento semántico dinámico
que combina datos reales del broker con esquemas Smart Data Models.

### RAG Knowledge
Consulta documentación técnica (manuales PDF) mediante búsqueda semántica con
reranking. Los documentos se vectorizan en ChromaDB usando el modelo
`sentence-transformers/all-MiniLM-L6-v2`. El agente puede listar los documentos
indexados y responder preguntas sobre su contenido.

### MongoDB
Gestiona documentos NoSQL: lista bases de datos y colecciones, infiere
esquemas, realiza consultas con filtros y ordenación, y ejecuta pipelines de
agregación. Útil para logs, historial de operaciones y datos no estructurados.

---

## Interfaces de uso

### Streamlit (interfaz web)
Interfaz visual con panel de control integrado para gestionar la base de
conocimiento RAG (vectorizar PDFs, eliminar documentos, consultar estado).
Recomendada para pruebas y demostraciones.

```bash
streamlit run app.py
# Disponible en http://localhost:8501
```

### FastAPI (API REST)
API de producción para integraciones externas. Soporta peticiones síncronas
y respuestas en streaming (SSE). Incluye endpoint de salud y métricas por sesión.

```bash
uvicorn interfaces.api:app --port 8082
# Disponible en http://localhost:8080
```

Endpoints principales:

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/chat` | Petición síncrona |
| `POST` | `/api/chat/stream` | Respuesta en streaming (SSE) |
| `GET`  | `/health` | Estado del sistema |
| `GET`  | `/metrics` | Métricas globales |
| `GET`  | `/metrics/session/{id}` | Métricas por sesión |

### Terminal (chat interactivo)
Modo consola para desarrollo y depuración rápida.

```bash
python -m interfaces.cli
```

---

## Instalación

**Prerrequisitos:** Python 3.12+, `uv` instalado.

```bash
# 1. Clonar y entrar en el proyecto
git clone <repositorio>
cd agente_control_smart_machine

# 2. Crear entorno virtual e instalar dependencias
uv venv
uv sync
source .venv/bin/activate   # Windows: .venv\Scripts\activate


# 3. Configurar credenciales
cp .env.example .env
nano .env
```

---

## Configuración

### Proveedor LLM

Edita **únicamente** esta línea en `config.yaml`:

```yaml
agent:
  provider: "azure"   # opciones: "azure" | "openai" | "local"
```

Los parámetros de cada proveedor (timeouts, tokens, credenciales de fallback)
se gestionan en `providers/<provider>.yaml`. Ver `providers/README.md` para
más detalle.

### Servidores MCP

Cada servidor se declara en la sección `servers` de `config.yaml`. El campo
`enabled` controla si se lanza al arrancar — el resto de la configuración
permanece intacta para poder reactivarlo en cualquier momento.

**Servidor propio** (script Python en `servers/`):

```yaml
servers:
  orion_ld:
    enabled: true
    type: "stdio"
    command: "uv"
    args: ["--quiet", "run", "servers/orion_server.py", "--server_type=stdio"]
    env:
      ORION_URL: "http://localhost:1026"
      ORION_TIMEOUT: "15"
    description: "Context Broker Orion-LD (solo lectura)"
```

**Servidor de terceros vía `uvx`** (paquete Python publicado, se ejecuta sin
instalación previa):

```yaml
  time_service:
    enabled: false
    type: "stdio"
    command: "uvx"
    args: ["mcp-server-time", "--local-timezone=Europe/Madrid"]
    description: "Servidor de hora mundial oficial"
```

**Servidor de terceros vía `npx`** (paquete npm publicado):

```yaml
  mongodb:
    enabled: false
    type: "stdio"
    command: "npx"
    args: ["-y", "mongodb-mcp-server@latest", "--readOnly"]
    env:
      MDB_MCP_CONNECTION_STRING: "mongodb://localhost:27017"
    description: "Servidor oficial de MongoDB (Solo lectura)"
```

| Campo | Obligatorio | Descripción |
|-------|-------------|-------------|
| `enabled` | ✅ | `true` para activar, `false` para desactivar |
| `type` | ✅ | Siempre `stdio` |
| `command` | ✅ | `uv` (propio), `uvx` (paquete Python), `npx` (paquete npm) |
| `args` | ✅ | Argumentos del comando. En servidores propios incluir siempre `--server_type=stdio` |
| `env` | — | Variables de entorno inyectadas al proceso del servidor |
| `description` | — | Texto informativo, no afecta al funcionamiento |

### Credenciales

Usa el archivo `.env` en la raíz del proyecto. Los valores en `.env` tienen
prioridad sobre cualquier valor escrito en los ficheros yaml.

```bash
# Azure OpenAI
AZURE_OPENAI_API_KEY=tu-clave
AZURE_OPENAI_ENDPOINT=https://tu-endpoint.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-12-01-preview

# OpenAI Cloud
OPENAI_API_KEY=sk-...

# vLLM local
VLLM_API_BASE=http://localhost:8000/v1
VLLM_API_KEY=tu-clave-local
```

---

## Proveedores LLM

| Proveedor | Configuración | Recomendado para |
|-----------|---------------|-----------------|
| **Azure OpenAI** | `provider: "azure"` | Producción |
| **OpenAI Cloud** | `provider: "openai"` | Desarrollo cloud |
| **vLLM local** | `provider: "local"` | Entornos sin conectividad, privacidad |

Para vLLM local, arranca el servidor con Docker:

```bash
sudo docker run --name vllm --gpus all \
     -v /data/huggingface_cache:/root/.cache/huggingface \
     -p 8000:8000 --ipc=host \
     vllm/vllm-openai:latest \
     --model hugging-quants/Meta-Llama-3.1-8B-Instruct-GPTQ-INT4 \
     --max-model-len 16384 \
     --gpu-memory-utilization 0.70 \
     --enable-auto-tool-choice \
     --tool-call-parser llama3_json
```

---

## Añadir un nuevo agente

1. **Crear el servidor** en `servers/mi_servidor.py` usando FastMCP:

```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("mi-servidor")

@mcp.tool(name="mi_herramienta", description="...")
def mi_herramienta(param: str) -> str:
    ...

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--server_type", default="stdio")
    args = parser.parse_args()
    mcp.run(transport=args.server_type)
```

2. **Registrarlo** en `config.yaml`:

```yaml
servers:
  mi_servidor:
    enabled: true
    type: "stdio"
    command: "uv"
    args: ["--quiet", "run", "servers/mi_servidor.py", "--server_type=stdio"]
    env:
      MI_VAR: "valor"
    description: "Descripción del servidor"
```

3. **Definir su rol** en `prompts/system_prompts.py` añadiendo su system prompt
y actualizando `get_system_prompt()` para que lo devuelva cuando se detecte su nombre.

4. **Probar**: al arrancar el cliente verás en los logs:
```
✅ mi_servidor: X herramientas cargadas.
✅ Sistema Multi-Agente operativo. N especialistas registrados.
```

---

## Logs

Los logs se generan en `logs/` con rotación diaria automática a medianoche.
El nivel de detalle y el número de días a conservar se configuran en
`logging_config.yaml`.

Contenido típico:
```
INFO  🆕 Nueva sesión: streamlit_default
INFO  📞 Gestor -> orion_ld: consultar entidades tipo ManufacturingMachine
INFO  🔧 [orion_ld] → list_entities(entity_type='ManufacturingMachine')
INFO  ✅ [orion_ld] ← list_entities: [{"id": "urn:ngsi-ld:..."}]
INFO  ⏱️  Petición req_xxx: 3.21s (Tokens: 512in/128out, Costo: $0.000082)
```

---

## Solución de problemas

**Error `name 'Path' is not defined` al arrancar el cliente**
`Path` no está importado en `src/engine/client.py`. La función `_load_config` debe
usar `os.path` en lugar de `pathlib.Path`.

**Error de permisos en `/tmp/llama_index/`**
Ocurre cuando otro proceso creó el directorio de caché con otro usuario.
```bash
sudo rm -rf /tmp/llama_index/
```
El `app.py` ya apunta la caché a `/data/proyectos/hf_cache` para evitar este problema.

**El gestor responde "No tengo acceso a esa información"**
El servidor especialista está desactivado o falló al arrancar. Revisa que
`enabled: true` en `config.yaml` y comprueba los logs en busca de errores de
conexión.

**Respuestas inestables con vLLM local**
Los modelos cuantizados (4-bit, 8-bit) pueden generar JSON inestable en
function calling. Usar un modelo más grande o cambiar a `provider: "azure"`.

**Error `Unknown model` en LlamaIndex**
LlamaIndex valida los nombres de modelo contra su lista interna. El código
incluye las subclases `VLLMOpenAI` y `VLLMAzureOpenAI` que evitan esta
validación. Verifica que estás usando `src/engine/client.py` actualizado.

**Error 429 (rate limit) con Azure OpenAI**
Puede ocurrir si hay otro proceso paralelo (benchmark, otro usuario) usando
el mismo deployment. Esperar o aumentar la cuota en el portal de Azure.