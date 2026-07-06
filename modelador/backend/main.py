"""
Backend ligero para el Modelador NGSI-LD.
- Proxy de peticiones a Orion-LD (evitar CORS).
- Comprobación de conectividad al broker.
- Opcional: servir estáticos (o usar otro servidor para el frontend).
"""
import asyncio

from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from pydantic import BaseModel
from typing import Optional, Any
import logging
import os
import time
import httpx
import uuid
import zipfile
import tarfile
import io
import json
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.exceptions import CannotDetermineSpecification
from referencing.jsonschema import DRAFT202012
import urllib.parse
import ipaddress

import orion_auth

from starlette.websockets import WebSocketDisconnect

from logging_config import setup_logging

setup_logging()

# Ruta al build del frontend React (un nivel arriba de backend)
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# ── Límites para subida de paquetes ──
MAX_UPLOAD_BYTES   = 50 * 1024 * 1024   # 50 MB
MAX_ZIP_MEMBERS    = 200
MAX_MEMBER_BYTES   = 10 * 1024 * 1024   # 10 MB por fichero descomprimido


def _fiware_headers(base: dict, fiware_service: str | None, fiware_service_path: str | None = None) -> dict:
    """
    Añade cabeceras Fiware-Service y Fiware-ServicePath al dict de headers dado.
    Solo se incluyen si tienen valor; así los endpoints sin tenant no las envían.
    """
    result = dict(base)
    if fiware_service:
        result["Fiware-Service"] = fiware_service
    if fiware_service_path:
        result["Fiware-ServicePath"] = fiware_service_path
    return result


def _orion_tenant_headers(base: dict, tenant: str | None) -> dict:
    """
    Añade NGSILD-Tenant para Kong, que es el contrato TO-BE.
    Fiware-Service queda como compatibilidad local si ORION_SEND_FIWARE_SERVICE=true.
    """
    headers = dict(base)
    if tenant and os.environ.get("ORION_SEND_FIWARE_SERVICE", "").lower() in ("1", "true", "yes"):
        headers = _fiware_headers(headers, tenant)
    if tenant:
        headers["NGSILD-Tenant"] = tenant
    return headers


async def _orion_proxy_headers(
    request: Request,
    base: dict[str, str],
    broker_base_url: str,
    fiware_service: str,
) -> tuple[dict[str, str], str | None]:
    headers = _orion_tenant_headers(dict(base), fiware_service or None)
    return await orion_auth.apply_session_authorization(
        request,
        headers,
        broker_base_url,
        fiware_service or "",
    )


_PROXY_AUTH_MESSAGES = {
    "orion_auth_required": "Sesión Orion requerida; conéctate en Configuración.",
    "orion_token_expired": "Sesión Orion expirada; vuelve a conectar.",
}


def _proxy_auth_failure(error_code: str, empty_body: Any) -> dict:
    return {
        "status": 401,
        "body": empty_body,
        "error": _PROXY_AUTH_MESSAGES.get(error_code, "Autenticación Orion requerida"),
        "error_code": error_code,
    }


async def _modelador_service_headers(
    request: Any,
    broker_base_url: str,
    tenant: str,
    detail: str = "Sesión Orion requerida; conéctate en Configuración.",
) -> dict[str, str]:
    """
    Headers de backend a backend para servicios protegidos por Kong.

    El token nunca se expone al navegador: se obtiene de la sesión HTTP-only del BFF
    y se reusa solo en llamadas servidor-servidor hacia MCP/Voice/RAG/Quantum.
    """
    broker_base_url = broker_base_url.strip()
    tenant = tenant.strip()
    if not broker_base_url or not tenant:
        raise HTTPException(401, detail)
    _validate_broker_url(broker_base_url)

    headers = _orion_tenant_headers({}, tenant)
    headers["X-Modelador-Kong-Url"] = broker_base_url.rstrip("/")
    headers["X-Modelador-Tenant"] = tenant
    out, error_code = await orion_auth.apply_session_authorization(
        request,
        headers,
        broker_base_url,
        tenant,
    )
    if error_code:
        raise HTTPException(401, _PROXY_AUTH_MESSAGES.get(error_code, detail))
    return out


def _validate_broker_url(url: str) -> None:
    """
    Valida que broker_base_url sea una URL http/https razonable.
    Rechaza esquemas peligrosos y direcciones de metadatos cloud (169.254.x.x).
    Para uso interno se permiten localhost e IPs privadas (RFC-1918) porque
    Orion-LD suele correr en la red local.
    """
    if not url:
        raise HTTPException(400, "broker_base_url es requerido")
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        raise HTTPException(400, "broker_base_url no es una URL válida")
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "broker_base_url debe usar esquema http o https")
    hostname = parsed.hostname or ""
    # Bloquear rangos de metadatos cloud (169.254.x.x) que no son Orion
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_link_local:
            raise HTTPException(400, "broker_base_url apunta a una dirección link-local no permitida")
    except ValueError:
        pass  # No es una IP literal; nombres de host son aceptables

app = FastAPI(
    title="NGSI-LD Data Space Modelador",
    description="API de proxy y comprobación de brokers Orion-LD",
    version="0.1.0",
)

api_logger = logging.getLogger("modelador.api")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Errores no previstos: log JSON con traza y respuesta uniforme al cliente."""
    api_logger.error(
        "unhandled_exception",
        exc_info=True,
        extra={
            "event": "unhandled_exception",
            "path": request.url.path,
            "method": request.method,
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Error interno del servidor",
            "error_code": "internal_error",
        },
    )


@app.middleware("http")
async def log_request_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    api_logger.info(
        "request_completed",
        extra={
            "event": "http_request",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


def _cors_allow_origins_and_credentials():
    """
    Orígenes permitidos vía CORS_ORIGINS (lista separada por comas).
    Por defecto: localhost típico de uvicorn (8000) y Vite (5173).
    CORS_ORIGINS=* desactiva credenciales en la respuesta CORS (requisito del navegador).
    """
    default = [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]
    raw = (os.environ.get("CORS_ORIGINS") or "").strip()
    if not raw:
        return default, True
    if raw == "*":
        return ["*"], False
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return (origins if origins else default), True


_cors_origins, _cors_credentials = _cors_allow_origins_and_credentials()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Proxy / Conectividad Orion-LD ----------


class OrionAuthBody(BaseModel):
    broker_base_url: str
    fiware_service: str = ""
    username: str
    password: str


class OrionHealthAuthBody(BaseModel):
    broker_base_url: str
    fiware_service: str = ""
    username: str = ""
    password: str = ""


@app.get("/api/health")
async def check_broker_connectivity(broker_base_url: str, fiware_service: str = ""):
    """
    Comprueba conectividad con un broker Orion-LD.
    Siempre devuelve 200; si el broker no responde, ok=false y error con el motivo.
    """
    base = broker_base_url.rstrip("/")
    url = f"{base}/version"  # Orion-LD suele exponer /version
    fs_headers = _orion_tenant_headers({}, fiware_service or None)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, headers=fs_headers)
            return {"ok": r.status_code < 400, "status": r.status_code, "url": url}
    except Exception:
        try:
            url_alt = f"{base}/ngsi-ld/v1/"
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(url_alt, headers=fs_headers)
                return {"ok": r.status_code < 400, "status": r.status_code, "url": url_alt}
        except Exception as e2:
            err = str(e2).strip()
            if "connection" in err.lower() or "refused" in err.lower() or "attempts failed" in err.lower():
                err = "No hay ningún servicio escuchando en esa URL. Comprueba que Orion-LD esté en marcha."
            return {
                "ok": False,
                "status": None,
                "url": url,
                "error": err,
            }


@app.post("/api/health/orion")
async def check_orion_auth_connectivity(body: OrionHealthAuthBody):
    """
    Comprueba conectividad y, si se envían credenciales, valida el login OIDC contra Keycloak vía Kong.
    """
    _validate_broker_url(body.broker_base_url)
    if not body.username.strip() or not body.password:
        return {
            "connectivity_ok": False,
            "auth_ok": False,
            "http_status": None,
            "detail": "Para comprobar Orion vía Kong introduce usuario y contraseña.",
        }

    connectivity = await check_broker_connectivity(body.broker_base_url, body.fiware_service)
    auth_ok: bool | None = None
    auth_error: str | None = None
    auth_status: int | None = None
    try:
        token_data = await orion_auth.request_password_token(
            body.broker_base_url,
            body.username.strip(),
            body.password,
        )
        token_type = str(token_data.get("token_type") or "Bearer")
        headers = _orion_tenant_headers({}, body.fiware_service or None)
        headers["Authorization"] = f"{token_type} {token_data['access_token']}"
        base = body.broker_base_url.rstrip("/")
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{base}/version", headers=headers)
            auth_status = r.status_code
            if r.status_code >= 400:
                r = await client.get(f"{base}/ngsi-ld/v1/", headers=headers)
                auth_status = r.status_code
        auth_ok = auth_status < 400
        if not auth_ok:
            auth_error = f"Kong/Orion rechazó el token para el tenant (HTTP {auth_status})"
    except HTTPException as exc:
        auth_ok = False
        auth_error = str(exc.detail)
    except Exception as exc:
        auth_ok = False
        auth_error = str(exc)
    return {
        "connectivity_ok": bool(connectivity.get("ok")) or auth_ok is True,
        "auth_ok": auth_ok,
        "http_status": auth_status or connectivity.get("status"),
        "detail": auth_error or connectivity.get("error"),
    }


@app.post("/api/auth/orion/login")
async def orion_login(request: Request, response: Response, body: OrionAuthBody):
    _validate_broker_url(body.broker_base_url)
    await orion_auth.login_set_cookie(
        request,
        response,
        body.broker_base_url,
        body.fiware_service or "",
        body.username,
        body.password,
    )
    return {"ok": True}


@app.post("/api/auth/orion/logout")
async def orion_logout(
    request: Request,
    response: Response,
    broker_base_url: str = "",
    fiware_service: str = "",
):
    await orion_auth.logout(response, request, broker_base_url, fiware_service or "")
    return {"ok": True}


@app.get("/api/auth/orion/status")
async def orion_auth_status(request: Request, broker_base_url: str, fiware_service: str = ""):
    _validate_broker_url(broker_base_url)
    return {
        "logged_in": orion_auth.status_logged_in(
            request,
            broker_base_url,
            fiware_service or "",
        )
    }


@app.post("/api/proxy/entities")
async def proxy_post_entities(request: Request, body: dict, broker_base_url: str = "", fiware_service: str = ""):
    """Proxy POST /ngsi-ld/v1/entities al broker seleccionado. broker_base_url por query."""
    _validate_broker_url(broker_base_url)
    base = broker_base_url.rstrip("/")
    url = f"{base}/ngsi-ld/v1/entities"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Orion-LD exige application/ld+json cuando hay @context en body.
            has_context = isinstance(body, dict) and body.get("@context") is not None
            base_headers = {"Content-Type": "application/ld+json" if has_context else "application/json"}
            headers, err_code = await _orion_proxy_headers(request, base_headers, broker_base_url, fiware_service)
            if err_code:
                return _proxy_auth_failure(err_code, {})
            r = await client.post(url, json=body, headers=headers)
            try:
                resp_body = r.json() if r.content else {}
            except Exception:
                resp_body = {}
            return {"status": r.status_code, "body": resp_body}
    except Exception as e:
        return {"status": 0, "body": {}, "error": str(e)}


@app.post("/api/proxy/subscriptions")
async def proxy_post_subscriptions(request: Request, body: dict, broker_base_url: str = "", fiware_service: str = ""):
    """Proxy POST /ngsi-ld/v1/subscriptions al broker seleccionado. broker_base_url por query."""
    _validate_broker_url(broker_base_url)
    base = broker_base_url.rstrip("/")
    url = f"{base}/ngsi-ld/v1/subscriptions"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Orion-LD exige application/ld+json cuando hay @context en body.
            has_context = isinstance(body, dict) and body.get("@context") is not None
            base_headers = {"Content-Type": "application/ld+json" if has_context else "application/json"}
            headers, err_code = await _orion_proxy_headers(request, base_headers, broker_base_url, fiware_service)
            if err_code:
                return _proxy_auth_failure(err_code, {})
            r = await client.post(url, json=body, headers=headers)
            try:
                resp_body = r.json() if r.content else {}
            except Exception:
                resp_body = {}
            return {"status": r.status_code, "body": resp_body}
    except Exception as e:
        return {"status": 0, "body": {}, "error": str(e)}


@app.patch("/api/proxy/entities/{entity_id}/attrs")
async def proxy_patch_entity_attrs(
    request: Request,
    entity_id: str,
    body: dict,
    broker_base_url: str = "",
    fiware_service: str = "",
):
    """Proxy PATCH /ngsi-ld/v1/entities/{id}/attrs. broker_base_url por query."""
    _validate_broker_url(broker_base_url)
    base = broker_base_url.rstrip("/")
    url = f"{base}/ngsi-ld/v1/entities/{entity_id}/attrs"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            has_context = isinstance(body, dict) and body.get("@context") is not None
            base_headers = {"Content-Type": "application/ld+json" if has_context else "application/json"}
            headers, err_code = await _orion_proxy_headers(request, base_headers, broker_base_url, fiware_service)
            if err_code:
                return _proxy_auth_failure(err_code, {})
            r = await client.patch(url, json=body, headers=headers)
            try:
                resp_body = r.json() if r.content else {}
            except Exception:
                resp_body = {}
            error = None if r.status_code < 400 else (r.text[:300] if r.text else "Error Orion")
            return {"status": r.status_code, "body": resp_body, "error": error}
    except Exception as e:
        return {"status": 0, "body": {}, "error": str(e)}


@app.delete("/api/proxy/entities/{entity_id}")
async def proxy_delete_entity(
    request: Request,
    entity_id: str,
    broker_base_url: str,
    fiware_service: str = "",
):
    """Proxy DELETE /ngsi-ld/v1/entities/{id}."""
    _validate_broker_url(broker_base_url)
    base = broker_base_url.rstrip("/")
    url = f"{base}/ngsi-ld/v1/entities/{entity_id}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers, err_code = await _orion_proxy_headers(request, {}, broker_base_url, fiware_service)
            if err_code:
                return _proxy_auth_failure(err_code, None)
            r = await client.delete(url, headers=headers)
            error = None if r.status_code < 400 else (r.text[:300] if r.text else "Error Orion")
            return {"status": r.status_code, "error": error}
    except Exception as e:
        return {"status": 0, "error": str(e)}


@app.get("/api/proxy/entities/{entity_id}")
async def proxy_get_entity_by_id(
    request: Request,
    entity_id: str,
    broker_base_url: str,
    fiware_service: str = "",
):
    """Proxy GET /ngsi-ld/v1/entities/{id} — devuelve la entidad completa en formato normalizado."""
    _validate_broker_url(broker_base_url)
    base = broker_base_url.rstrip("/")
    url = f"{base}/ngsi-ld/v1/entities/{entity_id}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers, err_code = await _orion_proxy_headers(request, {}, broker_base_url, fiware_service)
            if err_code:
                return _proxy_auth_failure(err_code, None)
            r = await client.get(url, headers=headers)
            if not r.content:
                return {"status": r.status_code, "body": None}
            try:
                body = r.json()
            except Exception:
                body = None
            error = None if r.status_code < 400 else (r.text[:300] if r.text else "Error Orion")
            return {"status": r.status_code, "body": body, "error": error}
    except Exception as e:
        return {"status": 0, "body": None, "error": str(e)}


@app.get("/api/proxy/entities")
async def proxy_get_entities(
    request: Request,
    broker_base_url: str,
    fiware_service: str = "",
    type: str = None,
    id: str = None,
    limit: int = None,
    offset: int = None,
    local: str = None,
):
    """
    Proxy GET /ngsi-ld/v1/entities.
    Orion-LD exige al menos uno de: entity-type, entity-id, local=true, etc.
    Si no se pasa type ni id, se añade local=true para poder listar todas las entidades.
    Soporta offset para paginación.
    """
    _validate_broker_url(broker_base_url)
    base = broker_base_url.rstrip("/")
    url = f"{base}/ngsi-ld/v1/entities"
    params = {}
    if type:
        params["type"] = type
    if id:
        params["id"] = id
    if limit is not None:
        params["limit"] = limit
    if offset is not None and offset > 0:
        params["offset"] = offset
    if not type and not id:
        params["local"] = "true"
    if local is not None:
        params["local"] = local
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers, err_code = await _orion_proxy_headers(request, {}, broker_base_url, fiware_service)
            if err_code:
                return _proxy_auth_failure(err_code, [])
            r = await client.get(url, params=params, headers=headers)
            if not r.content:
                return {"status": r.status_code, "body": []}
            try:
                body = r.json()
            except Exception:
                body = []
            if not isinstance(body, list):
                body = [body] if isinstance(body, dict) and body.get("id") else []
            return {"status": r.status_code, "body": body, "error": None if r.status_code < 400 else (r.text[:200] if r.text else "Error Orion")}
    except Exception as e:
        return {"status": 0, "body": [], "error": str(e)}


# ---------- Proxy de carga (schemas, contexto, descriptor) para evitar CORS ----------

def _allow_url(u: str) -> bool:
    u = (u or "").strip().lower()
    return u.startswith("http://") or u.startswith("https://")


class FetchBody(BaseModel):
    url: Optional[str] = None
    urls: Optional[list[str]] = None


class ChatTextRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    client_id: Optional[str] = None
    level_id: Optional[str] = None
    broker_base_url: Optional[str] = None
    tenant: Optional[str] = None
    context: Optional[dict[str, Any]] = None


class AgentConnectRequest(BaseModel):
    ngsild_tenant: str
    broker_base_url: Optional[str] = None


def _chat_llm_url() -> str:
    return (os.environ.get("CHAT_LLM_URL") or os.environ.get("LLM_AGENT_URL") or "").strip()


def _llm_connect_url() -> str:
    """URL del endpoint POST /api/connect del agente LLM (mismo host que CHAT_LLM_URL por defecto)."""
    explicit = (os.environ.get("CHAT_LLM_CONNECT_URL") or "").strip()
    if explicit:
        return explicit
    chat = _chat_llm_url()
    if not chat:
        return ""
    parsed = urllib.parse.urlparse(chat)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}/api/connect"


def _chat_llm_timeout() -> float:
    raw = (os.environ.get("CHAT_LLM_TIMEOUT_SECONDS") or "30").strip()
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 30.0


@app.get("/api/chat/config")
async def chat_config():
    """Configuración pública que necesita el widget de chat en runtime."""
    return {
        "aea_ws_url": (os.environ.get("AEA_WS_URL") or "").strip(),
        "text_chat_enabled": bool(_chat_llm_url()),
        "agent_connect_enabled": bool(_llm_connect_url()),
    }


@app.post("/api/connect")
async def agent_connect(request: Request, body: AgentConnectRequest):
    """
    Prepara el agente LLM para un tenant NGSI-LD (schemas, Orion, RAG, etc.).

    Proxy hacia POST /api/connect del servicio del agente. Requiere sesión Orion activa
    en el BFF para reenviar credenciales a Kong.
    """
    tenant = (body.ngsild_tenant or "").strip()
    if not tenant:
        raise HTTPException(400, "ngsild_tenant es requerido")

    broker_base_url = (body.broker_base_url or "").strip()
    headers = await _modelador_service_headers(
        request,
        broker_base_url,
        tenant,
        "Conecta Orion en Configuración antes de preparar el agente.",
    )

    connect_url = _llm_connect_url()
    if not connect_url:
        raise HTTPException(503, "CHAT_LLM_URL no está configurado (no se puede llamar al agente)")
    if not _allow_url(connect_url):
        raise HTTPException(500, "URL de connect del agente no permitida")

    headers["Content-Type"] = "application/json"
    api_key = (os.environ.get("CHAT_LLM_API_KEY") or "").strip()
    if api_key and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {"ngsild_tenant": tenant}

    try:
        async with httpx.AsyncClient(timeout=_chat_llm_timeout()) as client:
            r = await client.post(connect_url, json=payload, headers=headers)
            raw = r.json() if r.content else {}
            if r.status_code >= 400:
                detail = raw.get("detail") if isinstance(raw, dict) else r.text[:300]
                return {
                    "status": r.status_code,
                    "body": raw if isinstance(raw, dict) else {},
                    "error": detail or f"Error HTTP {r.status_code}",
                }
            return {
                "status": r.status_code,
                "body": raw if isinstance(raw, dict) else {},
                "error": None,
            }
    except httpx.HTTPError as e:
        return {"status": 0, "body": {}, "error": str(e)}


def _aea_ws_backend_url() -> str:
    """URL del voice-agent tal como la ve el contenedor del modelador (no el navegador)."""
    return (os.environ.get("AEA_WS_BACKEND_URL") or "ws://host.docker.internal:8000/ws/audio").strip()


@app.websocket("/api/aea/ws")
async def aea_websocket_proxy(websocket: WebSocket):
    """
    Proxy WebSocket → voice-agent. Permite usar solo el puerto del modelador (p. ej. SSH -L 8844)
    sin reenviar el 8000: el navegador abre ws://localhost:8844/api/aea/ws.
    """
    import websockets as ws_client
    import inspect

    log = logging.getLogger("aea_ws_proxy")
    backend = _aea_ws_backend_url()
    upstream_headers: dict[str, str] = {}
    try:
        await websocket.accept()
    except Exception as e:
        log.warning("aea proxy accept failed: %s", e)
        return

    broker_base_url = (websocket.query_params.get("broker_base_url") or "").strip()
    tenant = (websocket.query_params.get("tenant") or "").strip()
    try:
        upstream_headers = await _modelador_service_headers(
            websocket,
            broker_base_url,
            tenant,
            "Voice bloqueado hasta iniciar sesión en Orion.",
        )
    except Exception as e:
        log.info("aea proxy blocked without Orion session: %s", e)
        await websocket.close(code=1008)
        return

    upstream_headers["X-User-Id"] = orion_auth.get_session_user_id(
        websocket, broker_base_url, tenant
    )

    try:
        connect_kwargs: dict[str, Any] = {
            "max_size": None,
            "ping_interval": 120,
            "ping_timeout": 120,
            "close_timeout": 10,
        }
        if upstream_headers:
            header_arg = "additional_headers"
            if "additional_headers" not in inspect.signature(ws_client.connect).parameters:
                header_arg = "extra_headers"
            connect_kwargs[header_arg] = upstream_headers
        async with ws_client.connect(
            backend,
            **connect_kwargs,
        ) as upstream:
            async def pump_client_to_upstream() -> None:
                try:
                    while True:
                        try:
                            msg = await websocket.receive()
                        except WebSocketDisconnect:
                            break
                        if msg.get("type") == "websocket.disconnect":
                            break
                        if msg.get("text") is not None:
                            await upstream.send(msg["text"])
                        elif msg.get("bytes") is not None:
                            await upstream.send(msg["bytes"])
                except WebSocketDisconnect:
                    pass
                except Exception as ex:
                    log.debug("aea pump client→upstream: %s", ex)

            async def pump_upstream_to_client() -> None:
                try:
                    async for raw in upstream:
                        if isinstance(raw, str):
                            await websocket.send_text(raw)
                        else:
                            await websocket.send_bytes(raw)
                except ws_client.exceptions.ConnectionClosed:
                    pass
                except Exception as ex:
                    log.debug("aea pump upstream→client: %s", ex)

            c2u = asyncio.create_task(pump_client_to_upstream())
            u2c = asyncio.create_task(pump_upstream_to_client())
            _done, pending = await asyncio.wait({c2u, u2c}, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
    except Exception as e:
        log.warning("aea WebSocket proxy (upstream %s): %s", backend, e)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


def _extract_chat_response(data: Any) -> dict[str, Any]:
    """Normaliza respuestas del agente LLM compatible con AEA o formatos simples.

    Prioridad para el chat (markdown): ``text``; ``speech`` es el guion de voz si viene distinto.
    """
    if not isinstance(data, dict):
        s = str(data)
        return {"text": s, "speech": s, "data": {}, "raw": data}

    response = data.get("response")
    if isinstance(response, dict):
        text = (response.get("text") or "").strip()
        speech = (response.get("speech") or "").strip()
        if not text:
            text = speech
        if not speech:
            speech = text
        return {
            "text": text,
            "speech": speech,
            "data": response.get("data") or {},
            "raw": data,
        }

    text = (data.get("text") or data.get("message") or "").strip()
    if not text and isinstance(response, str):
        text = response.strip()
    if not text:
        text = (data.get("speech") or "").strip()
    speech = (data.get("speech") or "").strip()
    if not speech:
        speech = text
    return {
        "text": text,
        "speech": speech,
        "data": data.get("data") or {},
        "raw": data,
    }


@app.post("/api/chat/text")
async def chat_text(request: Request, body: ChatTextRequest):
    """
    Envía texto al agente LLM desde el backend del modelador.

    El navegador no debe conocer credenciales ni endpoints internos del LLM.
    Configuración:
      - CHAT_LLM_URL o LLM_AGENT_URL: endpoint HTTP del agente.
      - CHAT_LLM_API_KEY: opcional, se envía como Bearer token.
      - CHAT_CLIENT_ID / CHAT_LEVEL_ID: defaults del payload si no llegan del front.
    """
    message = (body.message or "").strip()
    if not message:
        raise HTTPException(400, "message es requerido")
    headers = await _modelador_service_headers(
        request,
        body.broker_base_url or "",
        body.tenant or "",
        "Chat bloqueado hasta iniciar sesión en Orion.",
    )

    llm_url = _chat_llm_url()
    if not llm_url:
        raise HTTPException(503, "CHAT_LLM_URL no está configurado")
    if not _allow_url(llm_url):
        raise HTTPException(500, "CHAT_LLM_URL debe ser http/https")

    request_id = str(uuid.uuid4())
    session_id = body.session_id or str(uuid.uuid4())
    session_user_id = orion_auth.get_session_user_id(
        request, body.broker_base_url or "", body.tenant or ""
    )
    payload = {
        "request_id": request_id,
        "session_id": session_id,
        "user_id": body.user_id or session_user_id,
        "client_id": body.client_id or os.environ.get("CHAT_CLIENT_ID") or "modelador",
        "level_id": body.level_id or os.environ.get("CHAT_LEVEL_ID") or "default_level",
        "input_text": message,
        "modality": "text",
    }
    if body.context:
        payload["context"] = body.context

    headers["Content-Type"] = "application/json"
    api_key = (os.environ.get("CHAT_LLM_API_KEY") or "").strip()
    if api_key and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=_chat_llm_timeout()) as client:
            r = await client.post(llm_url, json=payload, headers=headers)
            raw = r.json() if r.content else {}
            if r.status_code >= 400:
                return {
                    "status": r.status_code,
                    "body": {},
                    "error": raw.get("detail") if isinstance(raw, dict) else r.text[:300],
                }
            return {
                "status": r.status_code,
                "body": {
                    "request_id": request_id,
                    "session_id": session_id,
                    **_extract_chat_response(raw),
                },
                "error": None,
            }
    except httpx.HTTPError as e:
        return {"status": 0, "body": {}, "error": str(e)}


class ValidateEntityBody(BaseModel):
    payload: dict
    schema_doc: dict
    payload_mode: Optional[str] = "auto"  # auto | plain | normalized


class ValidateAttrsBody(BaseModel):
    attrs_payload: dict


class OrionGraphBuildBody(BaseModel):
    entities: list[dict[str, Any]]
    relationships: Optional[list[dict[str, Any]]] = None


class SchemaGraphBuildBody(BaseModel):
    types: list[str]
    relationships: Optional[list[dict[str, Any]]] = None


class SchemaTypeViewBody(BaseModel):
    type_id: str
    relationships: Optional[list[dict[str, Any]]] = None


class PrepareEntityPayloadBody(BaseModel):
    payload: dict[str, Any]
    type: str
    default_context: Optional[Any] = None


class PrepareAttrsPayloadBody(BaseModel):
    attrs_payload: dict[str, Any]


def _short_prop_name(key: str) -> str:
    if not key:
        return key
    try:
        u = urllib.parse.urlparse(key)
        frag = (u.fragment or "").strip()
        if frag:
            return frag
        parts = [p for p in (u.path or "").split("/") if p]
        return parts[-1] if parts else key
    except Exception:
        return key.split("/")[-1] or key


def _is_ngsi_id(s: Any) -> bool:
    return isinstance(s, str) and s.startswith("urn:ngsi-ld:")


def _entity_label(entity: dict[str, Any]) -> str:
    name = entity.get("name")
    if isinstance(name, dict) and name.get("value") is not None:
        return str(name.get("value"))
    if isinstance(name, str):
        return name
    part = (entity.get("id") or "").split(":")[-1] or (entity.get("id") or "")
    return part


def _build_orion_instance_graph(entities: list[dict[str, Any]], relationships: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    nodes = [
        {
            "id": e.get("id"),
            "type": e.get("type", ""),
            "label": _entity_label(e),
        }
        for e in entities
        if isinstance(e, dict) and e.get("id")
    ]
    node_map = {n["id"]: n for n in nodes}
    links: list[dict[str, Any]] = []
    skip = {"id", "type", "@context"}

    rel_props = set()
    for r in (relationships or []):
        if not isinstance(r, dict):
            continue
        if r.get("implicit"):
            continue
        rel_props.add(_short_prop_name(str(r.get("property") or "")))

    def add_link(source_id: str, target_id: str | None, key: str, implicit: bool) -> None:
        if not target_id:
            return
        links.append({
            "source": source_id,
            "target": target_id,
            "property": _short_prop_name(key),
            "implicit": bool(implicit),
        })
        if target_id not in node_map:
            node_map[target_id] = {
                "id": target_id,
                "type": "",
                "label": (target_id.split(":")[-1] or target_id),
            }
            nodes.append(node_map[target_id])

    def process_attr_instance(entity_id: str, key: str, inst: Any) -> None:
        if not isinstance(inst, dict):
            return
        short_key = _short_prop_name(key)

        if inst.get("type") == "Relationship" and inst.get("object") is not None:
            targets = inst.get("object")
            targets = targets if isinstance(targets, list) else [targets]
            for obj in targets:
                t_id = obj if isinstance(obj, str) else (obj.get("id") if isinstance(obj, dict) else None)
                add_link(entity_id, t_id, key, False)
            return

        if inst.get("type") == "Property" and inst.get("value") is not None:
            known_rel = short_key in rel_props
            value = inst.get("value")
            if _is_ngsi_id(value):
                add_link(entity_id, value, key, not known_rel)
            elif isinstance(value, list):
                for v in value:
                    if _is_ngsi_id(v):
                        add_link(entity_id, v, key, not known_rel)

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        entity_id = entity.get("id")
        if not entity_id:
            continue
        for key, val in entity.items():
            if key in skip or val is None:
                continue
            if isinstance(val, list):
                for inst in val:
                    process_attr_instance(entity_id, key, inst)
            else:
                process_attr_instance(entity_id, key, val)

    return {
        "nodes": nodes,
        "links": links,
        "stats": {
            "nodes": len(nodes),
            "links": len(links),
            "input_entities": len(entities),
        },
    }


def _attr_meta(raw_key: str) -> dict[str, Any]:
    try:
        parsed = urllib.parse.urlparse(raw_key)
        short = (parsed.fragment or "").strip()
        if not short:
            parts = [p for p in (parsed.path or "").split("/") if p]
            short = parts[-1] if parts else raw_key
        host = (parsed.hostname or "").lower()
        if "smartdatamodels" in host:
            ns = {"label": "SDM", "color": "#2a9d8f"}
        elif "schema.org" in host:
            ns = {"label": "schema.org", "color": "#8b8bcc"}
        elif "etsi.org" in host:
            ns = {"label": "NGSI-LD", "color": "#6366f1"}
        elif "w3.org" in host:
            ns = {"label": "W3C", "color": "#9ca3af"}
        elif "purl.org" in host:
            ns = {"label": "Dublin", "color": "#9ca3af"}
        elif host:
            host_parts = host.replace("www.", "").split(".")
            ns = {"label": ".".join(host_parts[-2:]), "color": "#9ca3af"}
        else:
            ns = None
        return {"short": short, "ns": ns}
    except Exception:
        return {"short": raw_key, "ns": None}


def _entity_view_from_raw(entity: dict[str, Any]) -> dict[str, Any]:
    skip = {"id", "type", "@context"}
    attrs: list[dict[str, Any]] = []
    for key, val in entity.items():
        if key in skip:
            continue
        meta = _attr_meta(key)
        type_tag = ""
        val_str = "–"
        if isinstance(val, dict):
            type_tag = str(val.get("type") or "")
            if type_tag == "Property":
                v = val.get("value")
                if isinstance(v, list):
                    val_str = ", ".join([(x.split(":")[-1] if _is_ngsi_id(x) else str(x)) for x in v])
                else:
                    val_str = json.dumps(v if v is not None else "–", ensure_ascii=False)
            elif type_tag == "Relationship":
                val_str = str(val.get("object") or "–")
            elif type_tag == "GeoProperty":
                geo = val.get("value")
                if isinstance(geo, dict):
                    coords = geo.get("coordinates") or []
                    val_str = f'{geo.get("type", "")} [{", ".join([str(c) for c in coords])}]'
                else:
                    val_str = "–"
            else:
                val_str = json.dumps(val, ensure_ascii=False)
        else:
            val_str = str(val if val is not None else "–")

        attrs.append({
            "key": key,
            "short": meta["short"],
            "ns": meta["ns"],
            "typeTag": type_tag,
            "value": val_str,
            "display": (val_str[:48] + "…") if len(val_str) > 50 else val_str,
        })
    return {
        "id": entity.get("id"),
        "type": entity.get("type"),
        "attrs": attrs,
    }


def _build_schema_graph_data(types: list[str], relationships: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    nodes = [{"id": t} for t in (types or []) if isinstance(t, str) and t.strip()]
    node_ids = {n["id"] for n in nodes}
    rels = relationships or []
    links = [
        {
            "source": r.get("from"),
            "target": r.get("to"),
            "property": r.get("property"),
            "implicit": bool(r.get("implicit")),
        }
        for r in rels
        if isinstance(r, dict) and r.get("from") in node_ids and r.get("to") in node_ids
    ]

    out_deg = {n["id"]: 0 for n in nodes}
    in_deg = {n["id"]: 0 for n in nodes}
    for l in links:
        out_deg[l["source"]] = out_deg.get(l["source"], 0) + 1
        in_deg[l["target"]] = in_deg.get(l["target"], 0) + 1
    total_deg = {k: out_deg.get(k, 0) + in_deg.get(k, 0) for k in out_deg.keys()}

    return {
        "nodes": nodes,
        "links": links,
        "metrics": {
            "out_degree": out_deg,
            "in_degree": in_deg,
            "total_degree": total_deg,
        },
        "stats": {
            "nodes": len(nodes),
            "links": len(links),
        },
    }


def _build_schema_type_view(type_id: str, relationships: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rels = [r for r in (relationships or []) if isinstance(r, dict)]
    from_rels = []
    to_rels = []
    for r in rels:
        property_raw = str(r.get("property") or "")
        meta = _attr_meta(property_raw)
        row = {
            "from": r.get("from"),
            "to": r.get("to"),
            "property": property_raw,
            "property_short": meta["short"],
            "property_ns": meta["ns"],
            "implicit": bool(r.get("implicit")),
        }
        if r.get("from") == type_id:
            from_rels.append(row)
        if r.get("to") == type_id:
            to_rels.append(row)
    return {
        "type_id": type_id,
        "from_rels": from_rels,
        "to_rels": to_rels,
    }


def _detect_entity_input_mode(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return "plain"
    for k, v in payload.items():
        if k in ("id", "type", "@context"):
            continue
        if isinstance(v, dict) and v.get("type") in ("Property", "Relationship", "GeoProperty"):
            return "normalized"
    return "plain"


def _to_ngsi_ld_attribute(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        t = value.get("type")
        if t in ("Property", "Relationship", "GeoProperty") and ("value" in value or "object" in value):
            return value
    return {"type": "Property", "value": value}


def _normalize_entity_for_orion(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    for k in list(out.keys()):
        if k in ("id", "type", "@context"):
            continue
        out[k] = _to_ngsi_ld_attribute(out[k])
    return out


def _normalize_attrs_payload(attrs_payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (attrs_payload or {}).items():
        out[k] = _to_ngsi_ld_attribute(v)
    return out


@app.post("/api/graph/orion/build")
async def build_orion_graph(body: OrionGraphBuildBody):
    """
    Construye en backend el grafo de instancias Orion-LD a partir de entidades
    NGSI-LD normalizadas y relaciones declaradas del descriptor.
    """
    try:
        graph = _build_orion_instance_graph(body.entities or [], body.relationships or [])
        return {"ok": True, **graph}
    except Exception as e:
        raise HTTPException(400, f"No se pudo construir el grafo de Orion: {e}")


@app.post("/api/graph/schema/build")
async def build_schema_graph(body: SchemaGraphBuildBody):
    """
    Construye en backend el grafo abstracto del modelo (tipos + relaciones).
    """
    try:
        graph = _build_schema_graph_data(body.types or [], body.relationships or [])
        return {"ok": True, **graph}
    except Exception as e:
        raise HTTPException(400, f"No se pudo construir el grafo de schema: {e}")


@app.post("/api/graph/schema/type-view")
async def build_schema_type_view(body: SchemaTypeViewBody):
    """
    Construye detalle enriquecido de un tipo del schema para el panel UI.
    """
    try:
        view = _build_schema_type_view(body.type_id, body.relationships or [])
        return {"ok": True, "view": view}
    except Exception as e:
        raise HTTPException(400, f"No se pudo construir la vista de tipo: {e}")


@app.post("/api/entities/prepare-payload")
async def prepare_entity_payload(body: PrepareEntityPayloadBody):
    """
    Prepara payload de creación de entidad:
    - aplica type e id por defecto
    - aplica @context por defecto si falta
    - detecta modo (plain/normalized)
    - normaliza para Orion cuando llega en formato plain
    """
    try:
        payload = dict(body.payload or {})
        payload["type"] = body.type
        if not payload.get("id"):
            payload["id"] = f"urn:ngsi-ld:{body.type}:001"
        if payload.get("@context") is None and body.default_context is not None:
            payload["@context"] = body.default_context

        input_mode = _detect_entity_input_mode(payload)
        payload_to_send = _normalize_entity_for_orion(payload) if input_mode == "plain" else payload
        return {
            "ok": True,
            "input_mode": input_mode,
            "payload_for_validation": payload,
            "payload_to_send": payload_to_send,
        }
    except Exception as e:
        raise HTTPException(400, f"No se pudo preparar el payload de entidad: {e}")


@app.post("/api/entities/prepare-attrs-payload")
async def prepare_attrs_payload(body: PrepareAttrsPayloadBody):
    """
    Prepara payload de edición de atributos para PATCH:
    - si llega en formato plano, lo envuelve como NGSI-LD Property
    - mantiene atributos ya normalizados (Property/Relationship/GeoProperty)
    """
    try:
        attrs = dict(body.attrs_payload or {})
        normalized = _normalize_attrs_payload(attrs)
        return {
            "ok": True,
            "attrs_payload_to_send": normalized,
        }
    except Exception as e:
        raise HTTPException(400, f"No se pudo preparar attrs payload: {e}")


@app.get("/api/entities/{entity_id}/view")
async def get_entity_view(request: Request, entity_id: str, broker_base_url: str, fiware_service: str = ""):
    """
    Devuelve una vista enriquecida de la entidad para consumo directo del panel UI.
    """
    _validate_broker_url(broker_base_url)
    base = broker_base_url.rstrip("/")
    url = f"{base}/ngsi-ld/v1/entities/{entity_id}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers, err_code = await _orion_proxy_headers(request, {}, broker_base_url, fiware_service)
            if err_code:
                return {
                    "status": 401,
                    "error": _PROXY_AUTH_MESSAGES.get(err_code, "Autenticación Orion requerida"),
                    "error_code": err_code,
                    "view": None,
                }
            r = await client.get(url, headers=headers)
            if not r.content:
                return {"status": r.status_code, "error": "Entidad vacía", "view": None}
            try:
                entity = r.json()
            except Exception:
                entity = None
            if r.status_code >= 400 or not isinstance(entity, dict):
                return {
                    "status": r.status_code,
                    "error": (r.text[:300] if r.text else "Error Orion"),
                    "view": None,
                }
            return {"status": r.status_code, "error": None, "view": _entity_view_from_raw(entity)}
    except Exception as e:
        return {"status": 0, "error": str(e), "view": None}


@app.post("/api/proxy/fetch")
async def proxy_fetch(body: FetchBody):
    """
    Proxy para cargar contenido desde URLs externas (schemas, contexto, descriptor).
    Body: { "url": "https://..." } o { "urls": ["https://...", ...] }.
    Devuelve el contenido como JSON cuando es posible.
    """
    if body.url:
        urls = [body.url]
    elif body.urls:
        urls = body.urls
    else:
        raise HTTPException(400, "Indica 'url' o 'urls' en el body")

    results = []
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for u in urls:
            if not _allow_url(u):
                results.append({"url": u, "ok": False, "error": "URL no permitida (solo http/https)"})
                continue
            try:
                r = await client.get(u)
                if r.status_code != 200:
                    results.append({"url": u, "ok": False, "status": r.status_code, "error": r.text[:200]})
                    continue
                ct = (r.headers.get("content-type") or "").lower()
                if "application/json" in ct or r.text.strip().startswith("{"):
                    try:
                        content = r.json()
                    except Exception:
                        content = r.text
                else:
                    content = r.text
                results.append({"url": u, "ok": True, "content": content})
            except Exception as e:
                results.append({"url": u, "ok": False, "error": str(e)})

    if body.url:
        single = results[0]
        if not single.get("ok"):
            raise HTTPException(502, detail=single.get("error", "Error al cargar la URL"))
        return single.get("content")
    return {"results": results}


# ---------- Context proxy (para que Orion pueda resolver contextos locales) ----------

@app.get("/api/context")
async def serve_context(url: str):
    """
    Descarga y reenvía un contexto JSON-LD desde la URL indicada.
    Permite que Orion-LD (en Docker) resuelva contextos de localhost usando
    http://host.docker.internal:<puerto>/api/context?url=<url_original>.
    """
    if not url or not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Parámetro 'url' inválido")
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            from fastapi.responses import Response
            return Response(
                content=r.content,
                media_type=r.headers.get("content-type", "application/ld+json"),
            )
    except Exception as e:
        raise HTTPException(502, detail=f"No se pudo obtener el contexto: {e}")


# ---------- Carga de paquete de modelo comprimido ----------

def _safe_member_name(name: str) -> str | None:
    """Devuelve el nombre normalizado o None si contiene path traversal."""
    # Rechazar rutas absolutas y componentes ".."
    normalized = name.replace("\\", "/").lstrip("/")
    parts = normalized.split("/")
    if any(p == ".." for p in parts):
        return None
    return normalized


def _extract_zip(content: bytes) -> dict[str, str]:
    """Extrae un ZIP en memoria → {ruta_normalizada: contenido_utf8}.
    Aplica límites de número de entradas y tamaño descomprimido por entrada."""
    result = {}
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if len(names) > MAX_ZIP_MEMBERS:
            raise HTTPException(400, f"El ZIP supera el límite de {MAX_ZIP_MEMBERS} ficheros")
        for name in names:
            safe = _safe_member_name(name)
            if safe is None:
                continue  # Ignorar entradas con path traversal
            info = zf.getinfo(name)
            if info.file_size > MAX_MEMBER_BYTES:
                continue  # Ignorar ficheros individuales demasiado grandes
            with zf.open(name) as f:
                result[safe] = f.read().decode("utf-8", errors="replace")
    return result


def _extract_tar(content: bytes) -> dict[str, str]:
    """Extrae un TAR / TAR.GZ en memoria → {ruta_normalizada: contenido_utf8}.
    Ignora symlinks y aplica límites de tamaño y número de entradas."""
    result = {}
    with tarfile.open(fileobj=io.BytesIO(content)) as tf:
        members = [m for m in tf.getmembers() if m.isfile() and not m.issym() and not m.islnk()]
        if len(members) > MAX_ZIP_MEMBERS:
            raise HTTPException(400, f"El TAR supera el límite de {MAX_ZIP_MEMBERS} ficheros")
        for member in members:
            safe = _safe_member_name(member.name)
            if safe is None:
                continue
            if member.size > MAX_MEMBER_BYTES:
                continue
            f = tf.extractfile(member)
            if f:
                result[safe] = f.read().decode("utf-8", errors="replace")
    return result


def _strip_root_folder(members: dict[str, str]) -> dict[str, str]:
    """
    Si todos los ficheros están bajo una única carpeta raíz (ej. mi-modelo/schemas/...)
    la elimina para normalizar a rutas relativas (schemas/...).
    Funciona sea cual sea el nombre del archivo comprimido.
    """
    if not members:
        return members
    paths = list(members.keys())
    first_segments = [p.lstrip("/").split("/")[0] for p in paths]
    # Si todos comparten la misma carpeta raíz Y ningún fichero está en la raíz directa
    if len(set(first_segments)) == 1 and all("/" in p.lstrip("/") for p in paths):
        prefix = first_segments[0] + "/"
        return {p[len(prefix):] if p.startswith(prefix) else p: v for p, v in members.items()}
    return members


def _classify_members(members: dict[str, str]) -> dict:
    """
    Clasifica los ficheros del paquete según la estructura estándar:
      schemas/      → JSON Schema definitions
      context/      → JSON-LD context (primer fichero encontrado)
      descriptor.json → descriptor de relaciones (opcional)
      examples/     → ejemplos de entidades (opcional)
    """
    schemas    = []
    context    = None
    descriptor = None
    examples   = {}
    unrecognized = []

    for path, raw in members.items():
        parts = path.strip("/").split("/")
        if not parts or not parts[-1]:
            continue

        fname  = parts[-1].lower()
        folder = parts[0].lower() if len(parts) > 1 else ""

        # Intentar parsear como JSON (schemas y ejemplos deben ser JSON válido)
        parsed = None
        if fname.endswith((".json", ".jsonld")):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                unrecognized.append(path)
                continue

        if folder == "schemas" and fname.endswith(".json") and parsed is not None:
            schemas.append(parsed)

        elif folder == "context" and fname.endswith((".jsonld", ".json")) and parsed is not None:
            if context is None:
                context = parsed  # solo el primero

        elif fname == "descriptor.json" and parsed is not None:
            if descriptor is None:
                descriptor = parsed

        elif folder == "examples" and fname.endswith(".json") and parsed is not None:
            if len(parts) >= 3:
                # Estructura con subcarpeta por tipo: examples/Building/example.json
                # La clave es el nombre de la subcarpeta (original case), no el fichero.
                # Si ya hay un ejemplo para ese tipo, no lo sobreescribimos (se queda el primero).
                example_key = parts[1]
                if example_key not in examples:
                    examples[example_key] = parsed
            else:
                # Estructura plana: examples/Building.json
                example_key = parts[-1][:-5] if parts[-1].lower().endswith(".json") else parts[-1]
                if example_key not in examples:
                    examples[example_key] = parsed

    return {
        "schemas": schemas,
        "context": context,
        "descriptor": descriptor,
        "examples": examples,
        "unrecognized": unrecognized,
    }


# ---------- RAG (documentos para ChromaDB / servicio externo) ----------

RAG_ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}
RAG_MAX_MB_DEFAULT = 20


def _rag_url() -> str:
    return (os.environ.get("RAG_URL") or "").strip()


def _rag_api_key() -> str:
    return (os.environ.get("RAG_API_KEY") or "").strip()


def _rag_base_url() -> str:
    """Base URL del servicio RAG (sin path). Deriva de RAG_BASE_URL o de RAG_URL."""
    base = (os.environ.get("RAG_BASE_URL") or "").strip().rstrip("/")
    if not base:
        raw = _rag_url()
        if raw:
            parsed = urllib.parse.urlparse(raw)
            base = f"{parsed.scheme}://{parsed.netloc}"
    return base


def _rag_auth_headers() -> dict:
    key = _rag_api_key()
    return {"Authorization": f"Bearer {key}"} if key else {}


def _rag_max_mb() -> int:
    raw = (os.environ.get("RAG_MAX_MB") or str(RAG_MAX_MB_DEFAULT)).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return RAG_MAX_MB_DEFAULT


def _rag_chroma_db() -> str:
    """Fallback cuando el cliente no envía tenant (p. ej. integraciones). El panel RAG usa Fiware-Service del broker."""
    return (os.environ.get("RAG_CHROMA_DB") or "default").strip()


def _require_authenticated_orion_session(
    request: Request,
    broker_base_url: str,
    tenant: str,
    detail: str = "Sesión Orion requerida; conéctate en Configuración.",
) -> None:
    """Bloquea accesos RAG/chat hasta que el BFF tenga sesión Keycloak para ese tenant."""
    if not orion_auth.auth_required():
        return
    broker_base_url = broker_base_url.strip()
    tenant = tenant.strip()
    if not broker_base_url or not tenant:
        raise HTTPException(401, detail)
    _validate_broker_url(broker_base_url)
    if not orion_auth.status_logged_in(request, broker_base_url, tenant):
        raise HTTPException(401, detail)


@app.get("/api/rag/tenants")
async def rag_list_tenants():
    base = _rag_base_url()
    if not base:
        raise HTTPException(503, "RAG_BASE_URL / RAG_URL no configurado")
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{base}/tenants", headers=_rag_auth_headers())
        return r.json()


@app.post("/api/rag/tenants")
async def rag_create_tenant(body: dict):
    base = _rag_base_url()
    if not base:
        raise HTTPException(503, "RAG_BASE_URL / RAG_URL no configurado")
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.post(f"{base}/tenants", json=body, headers=_rag_auth_headers())
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        return r.json()


@app.delete("/api/rag/tenants/{tenant}")
async def rag_delete_tenant(tenant: str):
    base = _rag_base_url()
    if not base:
        raise HTTPException(503, "RAG_BASE_URL / RAG_URL no configurado")
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.delete(f"{base}/tenants/{tenant}", headers=_rag_auth_headers())
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        return r.json()


@app.get("/api/rag/documents")
async def rag_list_documents(request: Request, tenant: str = "", broker_base_url: str = "", orion_tenant: str = ""):
    base = _rag_base_url()
    if not base:
        raise HTTPException(503, "RAG_BASE_URL / RAG_URL no configurado")
    tenant = tenant.strip() or _rag_chroma_db()
    _require_authenticated_orion_session(request, broker_base_url, orion_tenant or tenant)
    enc = urllib.parse.quote(tenant, safe="")
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(f"{base}/tenants/{enc}/documents", headers=_rag_auth_headers())
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        return r.json()


@app.delete("/api/rag/documents/{filename}")
async def rag_delete_document(
    request: Request,
    filename: str,
    tenant: str = "",
    broker_base_url: str = "",
    orion_tenant: str = "",
    delete_file: bool = False,
):
    base = _rag_base_url()
    if not base:
        raise HTTPException(503, "RAG_BASE_URL / RAG_URL no configurado")
    tenant = tenant.strip() or _rag_chroma_db()
    _require_authenticated_orion_session(request, broker_base_url, orion_tenant or tenant)
    t_enc = urllib.parse.quote(tenant, safe="")
    f_enc = urllib.parse.quote(filename, safe="")
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.delete(
            f"{base}/tenants/{t_enc}/documents/{f_enc}",
            params={"delete_file": str(delete_file).lower()},
            headers=_rag_auth_headers(),
        )
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        return r.json()


@app.post("/api/rag/vectorize")
async def rag_vectorize(request: Request, tenant: str = "", broker_base_url: str = "", orion_tenant: str = ""):
    base = _rag_base_url()
    if not base:
        raise HTTPException(503, "RAG_BASE_URL / RAG_URL no configurado")
    tenant = tenant.strip() or _rag_chroma_db()
    _require_authenticated_orion_session(request, broker_base_url, orion_tenant or tenant)
    enc = urllib.parse.quote(tenant, safe="")
    async with httpx.AsyncClient(timeout=300.0) as c:
        r = await c.post(f"{base}/tenants/{enc}/vectorize", json={}, headers=_rag_auth_headers())
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        return r.json()


@app.delete("/api/rag/clear")
async def rag_clear_index(request: Request, tenant: str = "", broker_base_url: str = "", orion_tenant: str = ""):
    base = _rag_base_url()
    if not base:
        raise HTTPException(503, "RAG_BASE_URL / RAG_URL no configurado")
    tenant = tenant.strip() or _rag_chroma_db()
    _require_authenticated_orion_session(request, broker_base_url, orion_tenant or tenant)
    enc = urllib.parse.quote(tenant, safe="")
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.delete(f"{base}/tenants/{enc}/clear", headers=_rag_auth_headers())
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        return r.json()


@app.get("/api/rag/config")
async def rag_config():
    """
    Configuración pública del RAG que necesita el widget del frontend en runtime.
    No expone la URL del servicio ni la API key.
    """
    url = _rag_url()
    return {
        "enabled": bool(url),
        "max_mb": _rag_max_mb(),
        "allowed_extensions": sorted(RAG_ALLOWED_EXTENSIONS),
        "chroma_db": _rag_chroma_db(),
    }


@app.post("/api/rag/upload")
async def rag_upload(
    request: Request,
    file: UploadFile = File(...),
    tenant: str = "",
    broker_base_url: str = "",
    orion_tenant: str = "",
    collection: str = "documents",
):
    """
    Proxy de subida de documentos al servicio RAG externo.

    El navegador nunca habla directamente con el servicio RAG:
    - Acepta PDF, TXT y Markdown.
    - Valida tipo y tamaño.
    - Reenvía multipart/form-data al endpoint configurado en RAG_URL,
      incluyendo el tenant (ChromaDB) y la colección de destino.
    - Si RAG_API_KEY está definida la incluye como Bearer token.

    Parámetros query:
      tenant     → identifica la planta/espacio (= Fiware-Service del broker).
      collection → nombre de la colección dentro del tenant (default: documents).
    """
    rag_url = _rag_url()
    if not rag_url:
        raise HTTPException(503, "RAG_URL no está configurado en el servidor")
    if not _allow_url(rag_url):
        raise HTTPException(500, "RAG_URL debe ser http/https")
    tenant = tenant.strip() or _rag_chroma_db()
    _require_authenticated_orion_session(request, broker_base_url, orion_tenant or tenant)

    filename = (file.filename or "unnamed").strip()
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in RAG_ALLOWED_EXTENSIONS:
        raise HTTPException(
            415,
            f"Tipo de archivo no permitido ({ext or 'sin extensión'}). "
            f"Usa: {', '.join(sorted(RAG_ALLOWED_EXTENSIONS))}",
        )

    max_bytes = _rag_max_mb() * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(413, f"El archivo supera el límite de {_rag_max_mb()} MB")

    headers: dict[str, str] = {}
    api_key = _rag_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                rag_url,
                files={"file": (filename, content, file.content_type or "application/octet-stream")},
                data={
                    "tenant": tenant,
                    "collection": collection or "documents",
                    "chroma_db": _rag_chroma_db(),
                    "filename": filename,
                },
                headers=headers,
            )
            raw = r.json() if r.content else {}
            if r.status_code >= 400:
                return {
                    "ok": False,
                    "status": r.status_code,
                    "filename": filename,
                    "error": (raw.get("detail") if isinstance(raw, dict) else None) or r.text[:300],
                }
            return {
                "ok": True,
                "status": r.status_code,
                "filename": filename,
                "tenant": tenant,
                "collection": collection or "documents",
                "detail": raw,
            }
    except httpx.HTTPError as e:
        return {"ok": False, "status": 0, "filename": filename, "error": str(e)}


@app.post("/api/upload/model-package")
async def upload_model_package(file: UploadFile = File(...)):
    """
    Carga un paquete de modelo comprimido (.zip, .tar.gz, .tgz, .tar).
    Estructura estándar dentro del comprimido (la carpeta raíz puede tener cualquier nombre):

        schemas/          ← JSON Schema definitions  (*.json)
        context/          ← JSON-LD context file     (*.jsonld o *.json)
        descriptor.json   ← descriptor de relaciones (opcional)
        examples/         ← ejemplos de entidades    (*.json, opcional)

    Devuelve el mismo formato que se almacena en localStorage (ngsi_model),
    más un campo 'examples' con los payloads de ejemplo indexados por nombre de fichero.
    """
    filename = (file.filename or "").lower()
    content  = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail=f"El archivo supera el límite de {MAX_UPLOAD_BYTES // (1024*1024)} MB")

    # Detectar formato por extensión o por cabecera mágica
    try:
        if filename.endswith(".zip") or content[:2] == b"PK":
            members = _extract_zip(content)
        elif filename.endswith((".tar.gz", ".tgz", ".tar")) or content[:2] in (b"\x1f\x8b", b"us"):
            members = _extract_tar(content)
        else:
            # Intentar ZIP primero, luego TAR
            try:
                members = _extract_zip(content)
            except Exception:
                members = _extract_tar(content)
    except Exception as e:
        raise HTTPException(400, detail=f"No se pudo descomprimir el archivo: {e}")

    members    = _strip_root_folder(members)
    classified = _classify_members(members)

    if not classified["schemas"] and classified["context"] is None and classified["descriptor"] is None:
        raise HTTPException(422, detail=(
            "El paquete no contiene ficheros reconocibles. "
            "Asegúrate de que incluye las carpetas 'schemas/', 'context/' y/o el fichero 'descriptor.json'."
        ))

    return {
        "ok":        True,
        "schemas":   classified["schemas"],
        "context":   classified["context"],
        "descriptor":classified["descriptor"],
        "examples":  classified["examples"],
        "summary": {
            "schemas":    len(classified["schemas"]),
            "context":    classified["context"] is not None,
            "descriptor": classified["descriptor"] is not None,
            "examples":   len(classified["examples"]),
            "unrecognized": classified["unrecognized"],
        },
    }


# ---------- Validación JSON / Schema ----------

_schema_cache = {}


def _fetch_json_sync(uri: str):
    """Descarga un schema remoto para resolver $ref, con cache en memoria."""
    if uri in _schema_cache:
        return _schema_cache[uri]
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        r = client.get(uri)
        r.raise_for_status()
        data = r.json()
        _schema_cache[uri] = data
        return data


def _retrieve_schema_resource(uri: str) -> Resource:
    """Recursos remotos para $ref http(s), con la misma caché que _fetch_json_sync."""
    return Resource.from_contents(_fetch_json_sync(uri))


def _resource_from_schema_doc(schema: dict) -> Resource:
    try:
        return Resource.from_contents(schema)
    except CannotDetermineSpecification:
        return DRAFT202012.create_resource(schema)


def _build_validator(schema: dict):
    registry = Registry(retrieve=_retrieve_schema_resource)
    root = _resource_from_schema_doc(schema)
    uri = root.id() or ""
    registry = registry.with_resource(uri, root)
    return Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )


def _to_plain_for_schema(entity: dict):
    """
    Convierte una entidad NGSI-LD normalizada a formato "plano" para validar
    contra schemas de Smart Data Models (que suelen definir propiedades como string/number/etc).

    Tipos NGSI-LD manejados:
      Property    → extrae "value"
      Relationship → extrae "object"
      GeoProperty → extrae "value" (GeoJSON Point/Polygon/…)
    """
    if not isinstance(entity, dict):
        return entity
    out = {}
    for k, v in entity.items():
        if k in ("id", "type", "@context"):
            out[k] = v
            continue
        if isinstance(v, dict):
            ngsi_type = v.get("type")
            if ngsi_type == "Property":
                out[k] = v.get("value")
            elif ngsi_type == "Relationship":
                out[k] = v.get("object")
            elif ngsi_type == "GeoProperty":
                out[k] = v.get("value")  # extrae el GeoJSON (Point, Polygon…)
            else:
                out[k] = v
        else:
            out[k] = v
    return out


def _deref_schema_for_coercion(subschema, resolver, depth: int = 0):
    """
    Sigue cadenas de $ref hasta un objeto con más claves que solo la ref (p. ej. {"type":"array"}).
    `resolver` es un referencing.Resolver con el documento base adecuado para refs relativas.
    """
    if depth > 24 or not isinstance(subschema, dict):
        return subschema
    ref = subschema.get("$ref")
    if ref is not None and len(subschema) == 1:
        try:
            r = resolver.lookup(ref)
            return _deref_schema_for_coercion(r.contents, r.resolver, depth + 1)
        except Exception:
            return subschema
    return subschema


def _collect_merged_property_subschemas(schema_node: dict, resolver) -> dict:
    """
    Une todas las definiciones `properties` visibles en el schema (raíz, $ref, allOf/oneOf/anyOf).
    Las apariciones posteriores sobrescriben claves anteriores (convención típica JSON Schema / SDM).

    Para cada propiedad, desreferencia $ref en el contexto del resolver (p. ej. category → CategoryType
    con type: array en device-schema.json). Sin esto, quedaría {"$ref":"#/definitions/..."} y
    refs relativas (#/definitions/…) deben resolverse con el resolver evolucionado tras cada $ref.
    """
    merged = {}

    def visit(node, res):
        nonlocal merged
        if not isinstance(node, dict):
            return
        if "$ref" in node:
            try:
                r = res.lookup(node["$ref"])
                visit(r.contents, r.resolver)
            except Exception:
                pass
            return
        props = node.get("properties")
        if isinstance(props, dict):
            for pk, pv in props.items():
                merged[pk] = _deref_schema_for_coercion(pv, res)
        for key in ("allOf", "oneOf", "anyOf"):
            for part in node.get(key) or []:
                visit(part, res)

    visit(schema_node, resolver)
    return merged


def _subschema_expects_array(subschema: dict, resolver) -> bool:
    """True si el subschema (resolviendo $ref y combinadores) declara type array."""
    s = _deref_schema_for_coercion(subschema, resolver)
    if not isinstance(s, dict):
        return False
    t = s.get("type")
    if t == "array":
        return True
    if isinstance(t, list) and "array" in t:
        return True
    for key in ("allOf", "oneOf", "anyOf"):
        for part in s.get(key) or []:
            if isinstance(part, dict) and _subschema_expects_array(part, resolver):
                return True
    return False


def _coerce_plain_scalars_to_arrays_for_schema(payload_plain: dict, schema_doc: dict) -> dict:
    """
    Smart Data Models (y similares) modelan a veces propiedades como array en JSON Schema
    (p. ej. category, controlledProperty en Device) mientras que en NGSI-LD bastan Property
    con un único string en `value`. Tras _to_plain_for_schema queda escalar y jsonschema falla.

    Si el schema declara type: array para esa propiedad y el valor plano es escalar (no null),
    se envuelve en lista de un elemento. No modifica listas ni objetos.
    """
    if not isinstance(payload_plain, dict) or not isinstance(schema_doc, dict):
        return payload_plain
    try:
        registry = Registry(retrieve=_retrieve_schema_resource)
        root = _resource_from_schema_doc(schema_doc)
        resolver = registry.resolver_with_root(root)
        prop_defs = _collect_merged_property_subschemas(schema_doc, resolver)
    except Exception:
        return payload_plain
    out = dict(payload_plain)
    for key, subschema in prop_defs.items():
        if key in ("id", "type", "@context"):
            continue
        if key not in out:
            continue
        val = out[key]
        if val is None or isinstance(val, list):
            continue
        if isinstance(val, dict):
            continue
        try:
            if _subschema_expects_array(subschema, resolver):
                out[key] = [val]
        except Exception:
            continue
    return out


def _is_normalized_entity(entity: dict) -> bool:
    if not isinstance(entity, dict):
        return False
    for k, v in entity.items():
        if k in ("id", "type", "@context"):
            continue
        if isinstance(v, dict) and v.get("type") in ("Property", "Relationship"):
            return True
    return False


@app.post("/api/validate/entity")
async def validate_entity(body: ValidateEntityBody):
    """
    Valida una entidad completa contra su JSON Schema.
    Soporta schemas wrapper con $ref remoto (Smart Data Models).
    """
    try:
        validator = _build_validator(body.schema_doc)
        mode = (body.payload_mode or "auto").lower()
        if mode == "plain":
            payload_plain = body.payload
        elif mode == "normalized":
            payload_plain = _to_plain_for_schema(body.payload)
        else:
            payload_plain = _to_plain_for_schema(body.payload) if _is_normalized_entity(body.payload) else body.payload
        payload_plain = _coerce_plain_scalars_to_arrays_for_schema(payload_plain, body.schema_doc)
        errors = sorted(validator.iter_errors(payload_plain), key=lambda e: list(e.path))
        return {
            "valid": len(errors) == 0,
            "errors": [
                {
                    "path": "/" + "/".join([str(p) for p in err.path]) if err.path else "/",
                    "message": err.message,
                }
                for err in errors
            ],
        }
    except Exception as e:
        return {"valid": False, "errors": [{"path": "/", "message": f"Error validando schema: {e}"}]}


@app.post("/api/validate/attrs")
async def validate_attrs(body: ValidateAttrsBody):
    """
    Validación mínima NGSI-LD para PATCH attrs.
    - Debe ser objeto no vacío.
    - Cada atributo debe tener type: Property|Relationship.
    - Property requiere value.
    - Relationship requiere object.
    """
    payload = body.attrs_payload
    errors = []
    VALID_ATTR_TYPES = ("Property", "Relationship", "GeoProperty")
    if not isinstance(payload, dict) or len(payload) == 0:
        errors.append({"path": "/", "message": "El payload de attrs debe ser un objeto JSON no vacío"})
    else:
        for k, v in payload.items():
            if not isinstance(v, dict):
                errors.append({"path": f"/{k}", "message": "Cada atributo debe ser un objeto"})
                continue
            t = v.get("type")
            if t not in VALID_ATTR_TYPES:
                errors.append({"path": f"/{k}/type", "message": f"type debe ser Property, Relationship o GeoProperty"})
                continue
            if t == "Property" and "value" not in v:
                errors.append({"path": f"/{k}", "message": "Property requiere campo value"})
            if t == "GeoProperty" and "value" not in v:
                errors.append({"path": f"/{k}", "message": "GeoProperty requiere campo value (GeoJSON)"})
            if t == "Relationship" and "object" not in v:
                errors.append({"path": f"/{k}", "message": "Relationship requiere campo object"})
    return {"valid": len(errors) == 0, "errors": errors}


# ---------- Servir frontend React (build de producción) ----------
#
# En desarrollo usa `npm run dev` en /frontend (Vite en :5173 con proxy /api → :8000).
# En producción ejecuta primero `npm run build` en /frontend para generar frontend/dist/,
# luego arranca únicamente uvicorn: FastAPI sirve tanto la API como los estáticos.

if FRONTEND_DIST.exists():
    # Archivos estáticos del build de React (JS, CSS, imágenes…)
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    # Catch-all: cualquier ruta que no sea /api/* devuelve index.html
    # para que React Router maneje la navegación en cliente.
    @app.get("/{full_path:path}")
    def serve_react(full_path: str):
        # Si existe el archivo físico en dist, servirlo directamente (p. ej. favicon.ico)
        candidate = FRONTEND_DIST / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_DIST / "index.html"))
else:
    @app.get("/")
    def index():
        return {
            "message": (
                "Frontend no encontrado. "
                "Ejecuta 'npm run build' dentro de /frontend para generar el build de producción, "
                "o arranca Vite con 'npm run dev' para desarrollo."
            )
        }
