"""
Autenticación Orion/Kong con Keycloak.

El navegador solo mantiene una cookie opaca. El BFF intercambia credenciales por
tokens OIDC, refresca el access token cuando caduca y añade Authorization Bearer
a las peticiones proxy hacia Kong.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import time
from typing import Any

import httpx
from fastapi import HTTPException, Request, Response

log = logging.getLogger("modelador.orion_auth")

COOKIE_NAME = "orion_session"
REFRESH_SKEW_SECONDS = 20.0

_sessions: dict[str, dict[str, Any]] = {}


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def auth_required() -> bool:
    return _bool_env("ORION_AUTH_REQUIRED", True)


def _realm() -> str:
    return (os.environ.get("ORION_KEYCLOAK_REALM") or "fiware").strip().strip("/")


def _client_id() -> str:
    return (os.environ.get("ORION_KEYCLOAK_CLIENT_ID") or "orion-client").strip()


def _client_secret() -> str:
    return (os.environ.get("ORION_KEYCLOAK_CLIENT_SECRET") or "").strip()


def _timeout() -> float:
    try:
        return max(1.0, float(os.environ.get("ORION_AUTH_TIMEOUT_SECONDS", "10")))
    except ValueError:
        return 10.0


def broker_key(broker_base_url: str, tenant: str) -> str:
    return f"{broker_base_url.rstrip('/')}\n{tenant or ''}"


def token_url(broker_base_url: str) -> str:
    override = (os.environ.get("ORION_KEYCLOAK_TOKEN_URL") or "").strip()
    if override:
        return override
    return f"{broker_base_url.rstrip('/')}/realms/{_realm()}/protocol/openid-connect/token"


def logout_url(broker_base_url: str) -> str:
    override = (os.environ.get("ORION_KEYCLOAK_LOGOUT_URL") or "").strip()
    if override:
        return override
    return f"{broker_base_url.rstrip('/')}/realms/{_realm()}/protocol/openid-connect/logout"


def _token_payload(extra: dict[str, str]) -> dict[str, str]:
    secret = _client_secret()
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="ORION_KEYCLOAK_CLIENT_SECRET no está configurado",
        )
    payload = {
        "client_id": _client_id(),
        "client_secret": secret,
        **extra,
    }
    return payload


async def request_password_token(
    broker_base_url: str,
    username: str,
    password: str,
) -> dict[str, Any]:
    payload = _token_payload({
        "grant_type": "password",
        "username": username,
        "password": password,
    })
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        try:
            r = await client.post(
                token_url(broker_base_url),
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    "No se pudo conectar con Kong/Keycloak. "
                    "Si el modelador corre en Docker Compose, usa la URL interna de Kong "
                    "(por ejemplo http://kong:8000) o configura una URL accesible desde el contenedor."
                ),
            ) from exc
    if r.status_code >= 400:
        raise HTTPException(
            status_code=401,
            detail=r.text[:300] if r.text else "No se pudo obtener token de Keycloak",
        )
    data = r.json()
    if not data.get("access_token") or not data.get("refresh_token"):
        raise HTTPException(401, "Respuesta de Keycloak sin access_token/refresh_token")
    return data


async def refresh_token(broker_base_url: str, refresh_token_value: str) -> dict[str, Any]:
    payload = _token_payload({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token_value,
    })
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        try:
            r = await client.post(
                token_url(broker_base_url),
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail="No se pudo conectar con Kong/Keycloak para refrescar el token.",
            ) from exc
    if r.status_code >= 400:
        raise HTTPException(
            status_code=401,
            detail=r.text[:300] if r.text else "No se pudo refrescar token de Keycloak",
        )
    data = r.json()
    if not data.get("access_token") or not data.get("refresh_token"):
        raise HTTPException(401, "Respuesta de refresh sin access_token/refresh_token")
    return data


def _extract_jwt_sub(access_token: str) -> str:
    """Extrae el claim 'sub' del payload JWT sin verificar la firma.

    El token ya fue validado por Kong antes de llegar aquí, por lo que
    la decodificación sin verificación es segura en este contexto.
    Devuelve 'unknown' ante cualquier error de formato.
    """
    try:
        parts = access_token.split(".")
        if len(parts) < 2:
            return "unknown"
        padding = 4 - len(parts[1]) % 4
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * padding))
        return str(payload.get("sub") or "unknown")
    except Exception:
        return "unknown"


def _expires_at(seconds: Any) -> float:
    try:
        return time.time() + max(0.0, float(seconds))
    except (TypeError, ValueError):
        return time.time()


def _bucket_from_token(data: dict[str, Any]) -> dict[str, Any]:
    token_type = str(data.get("token_type") or "Bearer")
    access_token = str(data["access_token"])
    return {
        "access_token": access_token,
        "refresh_token": str(data["refresh_token"]),
        "token_type": token_type,
        "expires_at": _expires_at(data.get("expires_in")),
        "refresh_expires_at": _expires_at(data.get("refresh_expires_in")),
        "user_id": _extract_jwt_sub(access_token),
    }


def _ensure_session_sid(sid: str | None) -> str:
    if sid and sid in _sessions:
        return sid
    new_sid = secrets.token_urlsafe(32)
    _sessions[new_sid] = {"by_broker": {}}
    return new_sid


async def login_set_cookie(
    request: Request,
    response: Response,
    broker_base_url: str,
    tenant: str,
    username: str,
    password: str,
) -> None:
    data = await request_password_token(broker_base_url, username.strip(), password)
    sid = _ensure_session_sid(request.cookies.get(COOKIE_NAME))
    _sessions[sid]["by_broker"][broker_key(broker_base_url, tenant)] = _bucket_from_token(data)
    response.set_cookie(
        key=COOKIE_NAME,
        value=sid,
        httponly=True,
        samesite="lax",
        max_age=int(float(data.get("refresh_expires_in") or 1800)),
        path="/",
    )
    log.info("orion_keycloak_login_ok", extra={"tenant": tenant[:64]})


async def logout(
    response: Response,
    request: Request,
    broker_base_url: str = "",
    tenant: str = "",
) -> None:
    sid = request.cookies.get(COOKIE_NAME)
    if not sid or sid not in _sessions:
        response.delete_cookie(COOKIE_NAME, path="/")
        return

    keys = [broker_key(broker_base_url, tenant)] if broker_base_url else list(_sessions[sid]["by_broker"].keys())
    for key in keys:
        bucket = _sessions[sid]["by_broker"].pop(key, None)
        if not bucket:
            continue
        try:
            await _keycloak_logout(broker_base_url or key.split("\n", 1)[0], bucket["refresh_token"])
        except Exception as exc:
            log.warning("orion_keycloak_logout_failed: %s", exc)

    if not _sessions[sid]["by_broker"]:
        del _sessions[sid]
        response.delete_cookie(COOKIE_NAME, path="/")


async def _keycloak_logout(broker_base_url: str, refresh_token_value: str) -> None:
    payload = _token_payload({"refresh_token": refresh_token_value})
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        await client.post(
            logout_url(broker_base_url),
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )


def status_logged_in(request: Request, broker_base_url: str, tenant: str) -> bool:
    sid = request.cookies.get(COOKIE_NAME)
    if not sid or sid not in _sessions:
        return False
    bucket = _sessions[sid]["by_broker"].get(broker_key(broker_base_url, tenant))
    return bool(bucket and time.time() < float(bucket["refresh_expires_at"]))


def get_session_user_id(request: Request, broker_base_url: str, tenant: str) -> str:
    """Devuelve el user_id (claim 'sub' del JWT) de la sesión activa, o 'unknown'."""
    sid = request.cookies.get(COOKIE_NAME)
    bucket = _sessions.get(sid or "", {}).get("by_broker", {}).get(broker_key(broker_base_url, tenant))
    if not bucket:
        return "unknown"
    return str(bucket.get("user_id") or "unknown")


async def apply_session_authorization(
    request: Request,
    headers: dict[str, str],
    broker_base_url: str,
    tenant: str,
) -> tuple[dict[str, str], str | None]:
    sid = request.cookies.get(COOKIE_NAME)
    key = broker_key(broker_base_url, tenant)
    bucket = _sessions.get(sid or "", {}).get("by_broker", {}).get(key)
    if not bucket:
        return (headers, "orion_auth_required") if auth_required() else (headers, None)

    now = time.time()
    if now >= float(bucket["refresh_expires_at"]):
        _sessions.get(sid or "", {}).get("by_broker", {}).pop(key, None)
        return (headers, "orion_token_expired") if auth_required() else (headers, None)

    if now >= float(bucket["expires_at"]) - REFRESH_SKEW_SECONDS:
        try:
            data = await refresh_token(broker_base_url, str(bucket["refresh_token"]))
            bucket.update(_bucket_from_token(data))
        except HTTPException:
            _sessions.get(sid or "", {}).get("by_broker", {}).pop(key, None)
            return (headers, "orion_token_expired") if auth_required() else (headers, None)

    out = dict(headers)
    out["Authorization"] = f"{bucket.get('token_type') or 'Bearer'} {bucket['access_token']}"
    return out, None

