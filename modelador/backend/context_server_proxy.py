"""Proxy HTTP hacia el Context Server multi-tenant (data_space/context_server)."""
from __future__ import annotations

import os
import urllib.parse
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/context-server", tags=["context-server"])


def context_server_url() -> str:
    return (os.environ.get("CONTEXT_SERVER_URL") or "").strip().rstrip("/")


def context_server_public_base() -> str:
    """URL canónica alcanzable desde la red Docker (Orion / IoT Agent / simulador)."""
    return (
        (os.environ.get("CONTEXT_SERVER_PUBLIC_URL") or "").strip().rstrip("/")
        or "http://context-server:8090"
    )


def require_context_server() -> str:
    base = context_server_url()
    if not base:
        raise HTTPException(503, "CONTEXT_SERVER_URL no configurado")
    return base


def stable_context_url(tenant: str) -> str:
    enc = urllib.parse.quote(tenant.strip(), safe="")
    return f"{context_server_public_base()}/tenants/{enc}/context.jsonld"


async def persist_model_to_context_server(
    tenant: str,
    model: dict[str, Any],
) -> None:
    """Guarda el modelo en el espacio del tenant. Lanza HTTPException si falla."""
    base = require_context_server()
    enc = urllib.parse.quote(tenant, safe="")
    try:
        async with httpx.AsyncClient(timeout=60.0) as c:
            r = await c.put(f"{base}/tenants/{enc}/model", json=model)
            if r.status_code >= 400:
                raise HTTPException(
                    502,
                    f"El servidor de contexto rechazó el modelo ({r.status_code}): {r.text[:300]}",
                )
    except httpx.HTTPError as e:
        raise HTTPException(502, f"No se pudo contactar con el servidor de contexto: {e}")


@router.get("/config")
async def context_server_config():
    """Indica al frontend si el servidor de contexto está disponible y su URL pública."""
    return {
        "enabled": bool(context_server_url()),
        "publicBaseUrl": context_server_public_base(),
    }


@router.post("/tenants")
async def context_server_create_tenant(body: dict):
    """Alta del espacio de un tenant en el servidor de contexto (idempotente)."""
    base = require_context_server()
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.post(f"{base}/tenants", json=body)
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        return r.json()


@router.delete("/tenants/{tenant}")
async def context_server_delete_tenant(tenant: str):
    """Baja del tenant: elimina su carpeta completa en el servidor de contexto."""
    base = require_context_server()
    enc = urllib.parse.quote(tenant, safe="")
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.delete(f"{base}/tenants/{enc}")
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        return r.json()


@router.get("/tenants/{tenant}/model")
async def context_server_get_model(tenant: str):
    base = require_context_server()
    enc = urllib.parse.quote(tenant, safe="")
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(f"{base}/tenants/{enc}/model")
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        return r.json()


@router.put("/tenants/{tenant}/model")
async def context_server_put_model(tenant: str, body: dict):
    base = require_context_server()
    enc = urllib.parse.quote(tenant, safe="")
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.put(f"{base}/tenants/{enc}/model", json=body)
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        return r.json()


@router.delete("/tenants/{tenant}/model")
async def context_server_delete_model(tenant: str):
    base = require_context_server()
    enc = urllib.parse.quote(tenant, safe="")
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.delete(f"{base}/tenants/{enc}/model")
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        return r.json()
