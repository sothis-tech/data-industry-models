# Despliegue

Guía mínima para configurar credenciales y arrancar el proyecto. Para la
descripción funcional, ver `README.md`.

## 1. El fichero `.env`

Las credenciales viven en **`config/.env`** (no en la raíz). Se crea copiando
la plantilla:

```bash
cp config/.env.example config/.env
```

Reglas:
- Los valores de `config/.env` **tienen prioridad** sobre los de
  `config/providers/<provider>.yaml`.
- `config/.env` **no se versiona**: confirma que está en `.gitignore`.
- En Docker se inyecta solo (el compose monta `./config/.env` y lo carga con
  `env_file`); en host lo carga el cliente al arrancar.

## 2. Qué rellenar según el proveedor

El proveedor **activo** se elige en el YAML (`agent.provider`), no en el `.env`.
Rellena solo el bloque correspondiente:

| Proveedor | `agent.provider` | Variables en `config/.env` |
|-----------|------------------|----------------------------|
| Azure OpenAI | `azure` | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION` |
| OpenAI Cloud | `openai` | `OPENAI_API_KEY` |
| vLLM local | `local` | `VLLM_API_BASE`, `VLLM_API_KEY` |

`AZURE_OPENAI_DEPLOYMENT` debe ser el nombre exacto de tu *deployment* en Azure
(el proyecto está ajustado para `gpt-4.1-nano`).

## 3. Qué NO va en el `.env`

Los hosts y puertos de los servicios (Orion, QuantumLeap, ChromaDB) y el tenant
**no van en `.env`**: están en el bloque `env` de cada servidor dentro del YAML
de configuración. El reparto es:

- `config/.env` → secretos y credenciales del LLM.
- `config/config*.yaml` → qué servidores se activan y a qué host/puerto/tenant
  apuntan.

Qué YAML se usa:
- **Host** (CLI / benchmark): `config/config.local.yaml` (puertos publicados:
  Orion `localhost:1027`, QL `localhost:8669`, Chroma `localhost:8012`).
- **Docker**: `config/config_docker.yaml` (nombres de servicio: `orion-ld:1026`,
  `quantumleap:8668`, `chromadb:8002`); el compose lo monta como
  `config/config.yaml`.

## 4. Arranque

Desde la raíz del proyecto, con `src/` en el `PYTHONPATH`.

**Host (desarrollo):**

```bash
export PYTHONPATH=src
uv venv && uv sync && source .venv/bin/activate
cp config/.env.example config/.env      # y rellena tus credenciales

# API
uvicorn interfaces.api:app --host 0.0.0.0 --port 8082
# Terminal
python -m interfaces.cli --config config/config.local.yaml
```

**Docker** (el servicio `mcp-server` dentro del compose común, en la red
`red_dataspace`):

```bash
docker compose up -d --build mcp-server
```

## 5. Verificación

```bash
python -m py_compile src/engine/client.py    # sintaxis OK
curl http://localhost:8082/health            # estado + proveedor LLM
curl -X POST http://localhost:8082/api/connect \
     -H "Content-Type: application/json" \
     -d '{"ngsild_tenant":"ibermot"}'        # precarga schema + RAG + QL
```

`/health` debe devolver el `llm_provider` y el deployment correctos; si ves un
deployment distinto al esperado, revisa `AZURE_OPENAI_DEPLOYMENT` en
`config/.env`.