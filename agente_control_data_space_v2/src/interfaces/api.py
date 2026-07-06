# src/interfaces/api.py
"""
API Gateway Industrial MCP
==========================
Punto de entrada HTTP para el sistema multi-agente.

Endpoints
---------
  POST /api/connect      → precarga el contexto del tenant (NUEVO v2.3)
  POST /api/chat         → conversación con el sistema multi-agente
  POST /api/chat/stream  → streaming SSE de la conversación
  GET  /health           → estado del API y del LLM provider
  GET  /metrics          → métricas agregadas
  GET  /metrics/session/{session_id}

Contexto de seguridad y enrutamiento
-------------------------------------
Body JSON ó cabeceras HTTP (body tiene prioridad):
  Authorization           → Authorization: Bearer <token>
  ngsild_tenant           → NGSILD-Tenant: <tenant>
  kong_url                → X-Modelador-Kong-Url: <url>
  x_modelador_tenant      → X-Modelador-Tenant: <tenant>  (alias)
"""

import subprocess
import os
import sys
import time
import yaml
import json
from typing import Optional, Literal
from contextlib import asynccontextmanager
from pathlib import Path

# src/interfaces/api.py → src es el padre de interfaces; la raíz del proyecto
# está un nivel por encima de src. Metemos src/ en sys.path para los imports
# 'engine.*', 'project.*', etc. y resolvemos config/ y datos contra la raíz.
_SRC_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _SRC_DIR.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Rutas de config y datos, ancladas a la raíz del proyecto (no al cwd).
CONFIG_DIR    = _PROJECT_ROOT / "config"
CONFIG_PATH   = CONFIG_DIR / "config.yaml"
PROVIDERS_DIR = CONFIG_DIR / "providers"
# Buffer temporal de gráficos (lo usa el middleware del proyecto de las gafas).
CHART_OUTPUTS = _SRC_DIR / "utils" / "chart_outputs"

from fastapi import FastAPI, HTTPException, Request as FastAPIRequest
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from engine.client import MCPChatClient
from engine.logging_setup import (
    setup_logging, get_logger,
    set_log_context, clear_log_context,
    log_startup_banner, log_shutdown_banner,
)

# Importar `project` REGISTRA guardrails + prompts + comportamientos del
# proyecto en el motor. Imprescindible para el comportamiento determinista.
import project  # noqa: F401

setup_logging()
logger = get_logger("mcp.api")


# ─── Modelos de Datos ──────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    request_id: str
    session_id: str
    user_id:    str
    client_id:  str
    level_id:   str
    input_text: str
    modality:   Literal["speech", "text"]

    authorization:      Optional[str] = None
    ngsild_tenant:      Optional[str] = None
    kong_url:           Optional[str] = None
    x_modelador_tenant: Optional[str] = None


class ChatResponse(BaseModel):
    request_id:    str
    status:        str
    error_code:    Optional[str] = ""
    error_message: Optional[str] = ""
    response:      dict


class ConnectRequest(BaseModel):
    """
    Petición de pre-carga al conectar a un tenant desde la UI.
    Pulsar "Conectar" en la pantalla de conexión Orion debe llamar aquí.

    El campo obligatorio es el tenant. El resto son opcionales y se usan
    si los necesitas para validar credenciales contra Kong / Keycloak.
    """
    ngsild_tenant: str
    authorization: Optional[str] = None
    kong_url:      Optional[str] = None


class ConnectResponse(BaseModel):
    status:        str               # "connected" | "partial" | "error"
    tenant:        str
    orion:         dict              # {status, types, total_entities}
    rag:           dict              # {status, documents, total_chunks}
    quantumleap:   dict              # {status}
    error_message: Optional[str] = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def cargar_configuracion() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        provider      = config.get("agent", {}).get("provider", "local")
        provider_path = PROVIDERS_DIR / f"{provider}.yaml"
        if provider_path.exists():
            with open(provider_path, encoding="utf-8") as f:
                provider_cfg = yaml.safe_load(f) or {}
            config.setdefault("agent", {}).update(provider_cfg)
        return config
    except Exception as e:
        logger.warning("No se pudo cargar %s: %s", CONFIG_PATH, e)
        return {}


def _resolve_request_context(
    body:    ChatRequest,
    headers: "Headers",
) -> dict:
    def _h(name: str) -> Optional[str]:
        return headers.get(name) or headers.get(name.lower())

    authorization = body.authorization or _h("Authorization")
    ngsild_tenant = (
        body.x_modelador_tenant
        or body.ngsild_tenant
        or _h("X-Modelador-Tenant")
        or _h("NGSILD-Tenant")
    )
    kong_url = body.kong_url or _h("X-Modelador-Kong-Url")

    ctx = {
        "authorization":      authorization,
        "ngsild_tenant":      ngsild_tenant,
        "kong_url":           kong_url,
        "x_modelador_tenant": body.x_modelador_tenant or _h("X-Modelador-Tenant"),
    }

    if ngsild_tenant:
        logger.debug("Contexto petición │ tenant=%s │ kong=%s", ngsild_tenant, kong_url)

    return ctx


def gestionar_vllm():
    config   = cargar_configuracion()
    provider = config.get("agent", {}).get("provider", "local")

    if provider != "local":
        if provider == "azure":
            deployment = config.get("agent", {}).get("azure_deployment", "unknown")
            endpoint   = config.get("agent", {}).get("azure_endpoint",   "unknown")
            logger.info("Motor LLM │ Azure OpenAI │ deployment=%s │ endpoint=%s",
                        deployment, endpoint)
        elif provider == "openai":
            model = config.get("agent", {}).get("default_model", "gpt-4o")
            logger.info("Motor LLM │ OpenAI Cloud │ model=%s", model)
        return

    container_name = "vllm_llama"
    model_name     = config.get("agent", {}).get("default_model", "llama-3.1-8b")
    logger.info("Motor LLM │ vLLM Local │ model=%s │ container=%s",
                model_name, container_name)

    try:
        check = subprocess.run(
            ["sudo", "docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True, text=True,
        )
        if "true" in check.stdout:
            logger.info("Contenedor Docker operativo")
            return
        logger.info("Arrancando contenedor Docker │ %s", container_name)
        result = subprocess.run(
            ["sudo", "docker", "start", container_name],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            logger.info("Contenedor arrancado, esperando inicialización...")
            time.sleep(5)
        else:
            logger.error("Error arrancando contenedor │ %s", result.stderr)
    except Exception as e:
        logger.exception("Error gestionando Docker: %s", e)


# ─── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    port = int(os.getenv("API_PORT", "8081"))
    log_startup_banner("API Gateway Industrial MCP", mode="FastAPI", extra={"port": port})

    gestionar_vllm()

    logger.info("Conectando a servidores MCP...")
    ok = await client_mcp.conectar()
    if ok:
        await client_mcp.inicializar_agente()
        logger.info("✅ Sistema Operativo")
    else:
        logger.critical("❌ Servidores MCP no disponibles")

    yield

    logger.info("Cerrando conexiones MCP...")
    await client_mcp.cerrar()
    log_shutdown_banner("API Gateway", reason="lifespan finalizado")


app = FastAPI(
    title="Industrial MCP API Gateway",
    description=(
        "API Gateway Multi-Agente para sistemas industriales basado en MCP. "
        "Soporta enrutamiento multi-tenant via NGSILD-Tenant."
    ),
    version="2.3.0",
    lifespan=lifespan,
)

CHART_OUTPUTS.mkdir(exist_ok=True)
app.mount("/charts", StaticFiles(directory=str(CHART_OUTPUTS)), name="charts")

client_mcp = MCPChatClient(config_path=str(CONFIG_PATH))


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/api/connect", response_model=ConnectResponse)
async def connect_endpoint(request: ConnectRequest, raw_request: FastAPIRequest):
    """
    Precarga el contexto para un tenant. La UI debe llamar a este endpoint
    al pulsar el botón 'Conectar' en la pantalla de conexión Orion.

    Qué hace:
      1. Construye el schema de Orion para ese tenant (lo cachea en memoria).
      2. Lista los documentos del RAG para ese tenant.
      3. Hace ping a QuantumLeap con ese tenant.
      4. Devuelve un resumen para mostrar en la UI.

    A partir de aquí, las peticiones de /api/chat reutilizarán el schema
    cacheado sin volver a construirlo.

    Body:
      { "ngsild_tenant": "ibermot",
        "authorization": "Bearer ...",      // opcional
        "kong_url":      "http://kong:8000" // opcional
      }
    """
    tenant = (request.ngsild_tenant or "").strip()
    if not tenant:
        raise HTTPException(
            status_code=422,
            detail={"error": "MISSING_TENANT", "message": "ngsild_tenant es obligatorio."},
        )

    set_log_context(request_id=f"connect_{int(time.time()*1000)}")
    logger.info("Pre-carga de tenant │ %s", tenant)

    try:
        summary = await client_mcp.precargar_tenant(tenant)

        # Decidir estado global
        all_ok = (
            summary["orion"]["status"] == "ok"
            and summary["rag"]["status"] in ("ok", "empty")
            and summary["quantumleap"]["status"] in ("ok", "degraded")
        )
        any_critical_error = (
            summary["orion"]["status"] == "error"
        )
        status = "connected" if all_ok else ("error" if any_critical_error else "partial")

        logger.info(
            "Tenant pre-cargado │ %s │ status=%s │ orion=%s rag=%s ql=%s",
            tenant, status,
            summary["orion"].get("status"),
            summary["rag"].get("status"),
            summary["quantumleap"].get("status"),
        )

        return ConnectResponse(
            status=status,
            tenant=tenant,
            orion=summary["orion"],
            rag=summary["rag"],
            quantumleap=summary["quantumleap"],
        )
    except Exception as e:
        logger.exception("Error en /api/connect")
        return ConnectResponse(
            status="error",
            tenant=tenant,
            orion={"status": "error"},
            rag={"status": "error"},
            quantumleap={"status": "error"},
            error_message=str(e),
        )
    finally:
        clear_log_context()


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, raw_request: FastAPIRequest):
    """
    Chat con el sistema multi-agente. Idealmente /api/connect ya se llamó
    para este tenant; si no, la primera petición construirá el schema en
    lazy-load (un poco más lenta, pero funcional).
    """
    set_log_context(
        request_id=request.request_id,
        session_id=request.session_id,
        user_id=request.user_id,
        client_id=request.client_id,
    )
    try:
        context = _resolve_request_context(request, raw_request.headers)

        if not context.get("ngsild_tenant"):
            raise HTTPException(
                status_code=422,
                detail={
                    "error":   "MISSING_TENANT",
                    "message": (
                        "El tenant es obligatorio en peticiones API. "
                        "Incluye el header 'NGSILD-Tenant: <tenant>' o el campo "
                        "'ngsild_tenant' en el body JSON."
                    ),
                },
            )

        payload             = request.model_dump()
        payload["message"]  = payload.pop("input_text")
        payload["_context"] = context

        result = await client_mcp.procesar_peticion_api(payload)
        _enrich_artifact_response(result)

        return {
            "request_id":    request.request_id,
            "status":        result.get("status", "success"),
            "error_code":    result.get("error_code", ""),
            "error_message": result.get("error_message", ""),
            "response":      result["response"],
        }

    except Exception as e:
        logger.exception("Error inesperado en /api/chat")
        return {
            "request_id":    request.request_id,
            "status":        "error",
            "error_code":    "INTERNAL_ERROR",
            "error_message": str(e),
            "response":      {},
        }
    finally:
        clear_log_context()


@app.post("/api/chat/stream")
async def chat_stream_endpoint(request: ChatRequest, raw_request: FastAPIRequest):
    set_log_context(
        request_id=request.request_id,
        session_id=request.session_id,
        user_id=request.user_id,
        client_id=request.client_id,
    )
    try:
        context = _resolve_request_context(request, raw_request.headers)

        if not context.get("ngsild_tenant"):
            raise HTTPException(
                status_code=422,
                detail={
                    "error":   "MISSING_TENANT",
                    "message": (
                        "El tenant es obligatorio en peticiones API. "
                        "Incluye el header 'NGSILD-Tenant: <tenant>' o el campo "
                        "'ngsild_tenant' en el body JSON."
                    ),
                },
            )

        gen = client_mcp.stream_respuesta_generador(
            mensaje=request.input_text,
            session_id=request.session_id,
            context=context,
        )
        return StreamingResponse(gen, media_type="text/event-stream")
    except Exception as e:
        logger.exception("Error en /api/chat/stream")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        clear_log_context()


@app.get("/health")
async def health_check():
    config   = cargar_configuracion()
    provider = config.get("agent", {}).get("provider", "local")
    info     = {"status": "ok", "llm_provider": provider}
    if provider == "azure":
        info["deployment"] = config.get("agent", {}).get("azure_deployment", "unknown")
        info["endpoint"]   = config.get("agent", {}).get("azure_endpoint",   "unknown")
    elif provider == "openai":
        info["model"] = config.get("agent", {}).get("default_model", "gpt-4o")
    elif provider == "local":
        info["model"]    = client_mcp.model_name
        info["api_base"] = config.get("agent", {}).get("api_base", "http://localhost:8000/v1")
    # Tenants ya precargados
    info["preloaded_tenants"] = client_mcp.get_preloaded_tenants()
    return info


@app.get("/")
async def root():
    return {
        "name":    "Industrial MCP API Gateway",
        "version": "2.3.0",
        "endpoints": {
            "connect":         "/api/connect",
            "chat":            "/api/chat",
            "stream":          "/api/chat/stream",
            "health":          "/health",
            "metrics":         "/metrics",
            "metrics_session": "/metrics/session/{session_id}",
            "docs":            "/docs",
        },
    }


@app.get("/metrics")
async def get_metrics():
    try:
        return await client_mcp.get_metrics_stats()
    except Exception as e:
        logger.exception("Error obteniendo métricas")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics/session/{session_id}")
async def get_session_metrics(session_id: str):
    try:
        stats = await client_mcp.get_session_metrics(session_id)
        if not stats:
            raise HTTPException(
                status_code=404,
                detail=f"Sesión '{session_id}' no encontrada",
            )
        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error obteniendo métricas de sesión")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Helpers internos ─────────────────────────────────────────────────────────

def _enrich_artifact_response(result: dict) -> None:
    data_block = result.get("response", {}).get("data", {})
    for key in ("chart_url", "_artifact"):
        if key not in data_block:
            continue
        url_or_filename = data_block[key]
        try:
            filename = url_or_filename.split("/")[-1]
            path     = os.path.join(str(CHART_OUTPUTS), filename)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                data_block["chart_data"] = raw_data
                data_block["status"]     = "enriched_from_artifact"
                del data_block[key]
                logger.info("Artefacto inyectado │ %s (clave: %s)", filename, key)
            else:
                logger.error("Artefacto no encontrado en disco │ %s", path)
        except Exception as e:
            logger.error("Error inyectando artefacto │ %s: %s", key, e)
        break


# ─── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", "8082"))
    try:
        uvicorn.run(app, host="0.0.0.0", port=port)
    except KeyboardInterrupt:
        print("\n👋 API cerrada por interrupción de usuario")