"""
Tests unitarios de orion_auth.py.

Cubre:
  - _extract_jwt_sub : decodificación del claim 'sub' del JWT sin verificar firma.
  - get_session_user_id : recuperación del user_id desde la sesión activa del BFF.
"""
import base64
import json
import sys
import os
import time

import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import orion_auth
from orion_auth import _extract_jwt_sub, get_session_user_id, _bucket_from_token


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _make_jwt(payload: dict) -> str:
    """Construye un JWT mínimo (sin firma real) con el payload dado."""
    header = base64.urlsafe_b64encode(b'{"alg":"RS256","typ":"JWT"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{body}.fakesignature"


def _make_request_with_session(sid: str) -> MagicMock:
    """Simula un objeto Request de FastAPI con la cookie de sesión ya fijada."""
    req = MagicMock()
    req.cookies = {orion_auth.COOKIE_NAME: sid}
    return req


# ══════════════════════════════════════════════════════════════════════════════
#  _extract_jwt_sub
# ══════════════════════════════════════════════════════════════════════════════

class TestExtractJwtSub:

    def test_extrae_sub_de_jwt_valido(self):
        token = _make_jwt({"sub": "user-abc-123", "exp": 9999999999})
        assert _extract_jwt_sub(token) == "user-abc-123"

    def test_sub_numerico_se_convierte_a_string(self):
        token = _make_jwt({"sub": 42})
        assert _extract_jwt_sub(token) == "42"

    def test_jwt_sin_sub_devuelve_unknown(self):
        token = _make_jwt({"preferred_username": "alice", "exp": 9999999999})
        assert _extract_jwt_sub(token) == "unknown"

    def test_sub_vacio_devuelve_unknown(self):
        token = _make_jwt({"sub": ""})
        assert _extract_jwt_sub(token) == "unknown"

    def test_sub_none_devuelve_unknown(self):
        token = _make_jwt({"sub": None})
        assert _extract_jwt_sub(token) == "unknown"

    def test_string_no_jwt_devuelve_unknown(self):
        assert _extract_jwt_sub("esto-no-es-un-jwt") == "unknown"

    def test_string_vacio_devuelve_unknown(self):
        assert _extract_jwt_sub("") == "unknown"

    def test_jwt_con_padding_variable(self):
        """El payload Base64 puede tener longitudes que requieran 0, 1 o 2 chars de padding."""
        for sub in ["a", "ab", "abc", "abcd", "abcde"]:
            token = _make_jwt({"sub": sub})
            assert _extract_jwt_sub(token) == sub

    def test_payload_base64_malformado_devuelve_unknown(self):
        assert _extract_jwt_sub("header.!!!invalido!!!.sig") == "unknown"

    def test_jwt_solo_dos_partes_devuelve_unknown(self):
        assert _extract_jwt_sub("header.payload") == "unknown"


# ══════════════════════════════════════════════════════════════════════════════
#  _bucket_from_token guarda user_id
# ══════════════════════════════════════════════════════════════════════════════

class TestBucketFromToken:

    def test_bucket_incluye_user_id_del_sub(self):
        token = _make_jwt({"sub": "keycloak-user-99", "exp": 9999999999})
        data = {
            "access_token": token,
            "refresh_token": "rt",
            "token_type": "Bearer",
            "expires_in": 300,
            "refresh_expires_in": 1800,
        }
        bucket = _bucket_from_token(data)
        assert bucket["user_id"] == "keycloak-user-99"

    def test_bucket_user_id_unknown_si_token_sin_sub(self):
        token = _make_jwt({"preferred_username": "alice"})
        data = {
            "access_token": token,
            "refresh_token": "rt",
            "token_type": "Bearer",
            "expires_in": 300,
            "refresh_expires_in": 1800,
        }
        bucket = _bucket_from_token(data)
        assert bucket["user_id"] == "unknown"


# ══════════════════════════════════════════════════════════════════════════════
#  get_session_user_id
# ══════════════════════════════════════════════════════════════════════════════

class TestGetSessionUserId:

    def setup_method(self):
        """Limpia el diccionario de sesiones antes de cada test."""
        orion_auth._sessions.clear()

    def _seed_session(self, sid: str, broker_url: str, tenant: str, sub: str) -> None:
        """Inserta una sesión activa en el store interno de orion_auth."""
        token = _make_jwt({"sub": sub, "exp": time.time() + 3600})
        key = orion_auth.broker_key(broker_url, tenant)
        orion_auth._sessions[sid] = {
            "by_broker": {
                key: {
                    "access_token": token,
                    "refresh_token": "rt",
                    "token_type": "Bearer",
                    "expires_at": time.time() + 300,
                    "refresh_expires_at": time.time() + 1800,
                    "user_id": sub,
                }
            }
        }

    def test_devuelve_sub_de_sesion_activa(self):
        self._seed_session("sid-1", "http://kong:8000", "tenant-a", "alice-sub")
        req = _make_request_with_session("sid-1")
        result = get_session_user_id(req, "http://kong:8000", "tenant-a")
        assert result == "alice-sub"

    def test_devuelve_unknown_sin_sesion(self):
        req = _make_request_with_session("sid-inexistente")
        result = get_session_user_id(req, "http://kong:8000", "tenant-a")
        assert result == "unknown"

    def test_devuelve_unknown_sin_cookie(self):
        req = MagicMock()
        req.cookies = {}
        result = get_session_user_id(req, "http://kong:8000", "tenant-a")
        assert result == "unknown"

    def test_devuelve_unknown_si_tenant_no_coincide(self):
        self._seed_session("sid-2", "http://kong:8000", "tenant-a", "bob-sub")
        req = _make_request_with_session("sid-2")
        result = get_session_user_id(req, "http://kong:8000", "tenant-b")
        assert result == "unknown"

    def test_devuelve_unknown_si_broker_no_coincide(self):
        self._seed_session("sid-3", "http://kong:8000", "tenant-a", "carol-sub")
        req = _make_request_with_session("sid-3")
        result = get_session_user_id(req, "http://other-kong:8000", "tenant-a")
        assert result == "unknown"

    def test_sesiones_distintas_no_se_mezclan(self):
        self._seed_session("sid-alice", "http://kong:8000", "t1", "alice-sub")
        self._seed_session("sid-bob",   "http://kong:8000", "t1", "bob-sub")

        assert get_session_user_id(
            _make_request_with_session("sid-alice"), "http://kong:8000", "t1"
        ) == "alice-sub"
        assert get_session_user_id(
            _make_request_with_session("sid-bob"), "http://kong:8000", "t1"
        ) == "bob-sub"
