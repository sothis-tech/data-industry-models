"""
Tests del endpoint /api/chat/text.

Cubre:
  - Bloqueo con 401 cuando ORION_AUTH_REQUIRED=true y no hay sesión.
  - Propagación del user_id real (sub del JWT) al agente LLM cuando hay sesión activa.
  - Fallback a 'unknown' cuando la sesión no tiene user_id (sesiones creadas antes del cambio).
  - Mensaje vacío devuelve 400.
  - CHAT_LLM_URL no configurado devuelve 503.
"""
import base64
import json
import sys
import os
import time
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import orion_auth
from main import app
from fastapi.testclient import TestClient


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.sig"


def _seed_session(sid: str, broker_url: str, tenant: str, sub: str) -> None:
    key = orion_auth.broker_key(broker_url, tenant)
    orion_auth._sessions[sid] = {
        "by_broker": {
            key: {
                "access_token": _make_jwt({"sub": sub, "exp": time.time() + 3600}),
                "refresh_token": "rt",
                "token_type": "Bearer",
                "expires_at": time.time() + 300,
                "refresh_expires_at": time.time() + 1800,
                "user_id": sub,
            }
        }
    }


BROKER = "http://kong:8000"
TENANT = "test-tenant"
COOKIE = orion_auth.COOKIE_NAME


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestChatTextAuth:

    def setup_method(self):
        orion_auth._sessions.clear()

    def test_sin_sesion_devuelve_401(self):
        with TestClient(app) as client:
            r = client.post(
                "/api/chat/text",
                json={"message": "Hola", "broker_base_url": BROKER, "tenant": TENANT},
            )
        assert r.status_code == 401

    def test_mensaje_vacio_devuelve_400(self):
        with TestClient(app) as client:
            r = client.post(
                "/api/chat/text",
                json={"message": "   ", "broker_base_url": BROKER, "tenant": TENANT},
            )
        assert r.status_code == 400

    def test_sin_llm_url_devuelve_503(self, monkeypatch):
        _seed_session("sid-llm", BROKER, TENANT, "user-x")
        monkeypatch.delenv("CHAT_LLM_URL", raising=False)
        monkeypatch.delenv("LLM_AGENT_URL", raising=False)
        with TestClient(app) as client:
            r = client.post(
                "/api/chat/text",
                json={"message": "Hola", "broker_base_url": BROKER, "tenant": TENANT},
                cookies={COOKIE: "sid-llm"},
            )
        assert r.status_code == 503


class TestChatTextUserIdPropagation:
    """Verifica que el user_id real del JWT llega al agente LLM."""

    def setup_method(self):
        orion_auth._sessions.clear()

    def _run_chat(self, sub: str, monkeypatch) -> dict:
        """Envía un mensaje de chat con sesión activa y captura el payload enviado al LLM."""
        _seed_session("sid-prop", BROKER, TENANT, sub)
        monkeypatch.setenv("CHAT_LLM_URL", "http://fake-llm/chat")

        captured = {}

        async def fake_post(self_client, url, *, json=None, headers=None):
            captured["payload"] = json
            resp = MagicMock()
            resp.status_code = 200
            resp.content = b'{"response": {"text": "ok", "speech": "ok", "data": {}}}'
            resp.json = lambda: {"response": {"text": "ok", "speech": "ok", "data": {}}}
            return resp

        with patch("httpx.AsyncClient.post", fake_post):
            with TestClient(app) as client:
                client.post(
                    "/api/chat/text",
                    json={"message": "Hola", "broker_base_url": BROKER, "tenant": TENANT},
                    cookies={COOKIE: "sid-prop"},
                )
        return captured.get("payload", {})

    def test_user_id_real_se_propaga_al_llm(self, monkeypatch):
        payload = self._run_chat("keycloak-sub-abc", monkeypatch)
        assert payload.get("user_id") == "keycloak-sub-abc"

    def test_user_id_no_es_unknown_cuando_hay_sesion(self, monkeypatch):
        payload = self._run_chat("real-user-sub", monkeypatch)
        assert payload.get("user_id") != "unknown"

    def test_fallback_unknown_si_bucket_sin_user_id(self, monkeypatch):
        """Sesión creada antes del cambio (sin campo user_id en el bucket)."""
        key = orion_auth.broker_key(BROKER, TENANT)
        orion_auth._sessions["sid-old"] = {
            "by_broker": {
                key: {
                    "access_token": _make_jwt({"sub": "old-user"}),
                    "refresh_token": "rt",
                    "token_type": "Bearer",
                    "expires_at": time.time() + 300,
                    "refresh_expires_at": time.time() + 1800,
                    # sin 'user_id' — sesión anterior al cambio
                }
            }
        }
        monkeypatch.setenv("CHAT_LLM_URL", "http://fake-llm/chat")

        captured = {}

        async def fake_post(self_client, url, *, json=None, headers=None):
            captured["payload"] = json
            resp = MagicMock()
            resp.status_code = 200
            resp.content = b'{"response": {"text": "ok", "speech": "ok", "data": {}}}'
            resp.json = lambda: {"response": {"text": "ok", "speech": "ok", "data": {}}}
            return resp

        with patch("httpx.AsyncClient.post", fake_post):
            with TestClient(app) as client:
                client.post(
                    "/api/chat/text",
                    json={"message": "Hola", "broker_base_url": BROKER, "tenant": TENANT},
                    cookies={COOKIE: "sid-old"},
                )

        assert captured.get("payload", {}).get("user_id") == "unknown"
