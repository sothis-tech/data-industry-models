"""
Tests del proxy de conectividad y validación básica de URLs.

Estos tests NO requieren Orion-LD; verifican que el backend responde
correctamente cuando el broker no existe o la URL es inválida.
"""
import pytest


class TestHealthEndpoint:
    """GET /api/health — siempre devuelve 200 con campo ok."""

    def test_returns_200_even_when_broker_unreachable(self, client):
        """El endpoint de salud NUNCA debe devolver 5xx; ok=false si el broker no responde."""
        r = client.get("/api/health", params={"broker_base_url": "http://localhost:9999"})
        assert r.status_code == 200
        data = r.json()
        assert "ok" in data
        assert data["ok"] is False

    def test_missing_broker_url_returns_error(self, client):
        """Sin broker_base_url debe devolver un error de validación (422)."""
        r = client.get("/api/health")
        assert r.status_code == 422

    def test_invalid_scheme_rejected(self, client):
        """Esquemas distintos de http/https no crashean el endpoint de salud."""
        r = client.get("/api/health", params={"broker_base_url": "ftp://localhost:1026"})
        assert r.status_code in (200, 400, 422)

    def test_response_contains_ok_field(self, client):
        """La respuesta siempre debe incluir el campo 'ok'."""
        r = client.get("/api/health", params={"broker_base_url": "http://localhost:9999"})
        assert r.status_code == 200
        assert "ok" in r.json()


class TestProxyPostValidation:
    """POST /api/proxy/entities — validación de broker_base_url."""

    def test_empty_broker_url_returns_400(self, client):
        r = client.post("/api/proxy/entities", json={"id": "test", "type": "Test"})
        assert r.status_code == 400

    def test_invalid_scheme_returns_400(self, client):
        r = client.post(
            "/api/proxy/entities",
            json={"id": "test", "type": "Test"},
            params={"broker_base_url": "file:///etc/passwd"},
        )
        assert r.status_code == 400

    def test_link_local_ip_returns_400(self, client):
        r = client.post(
            "/api/proxy/entities",
            json={"id": "test", "type": "Test"},
            params={"broker_base_url": "http://169.254.169.254/latest/meta-data"},
        )
        assert r.status_code == 400

    def test_localhost_valid_url_not_rejected_by_validation(self, client, monkeypatch):
        """localhost es válido; el error será de red, no de validación."""
        monkeypatch.setenv("ORION_AUTH_REQUIRED", "false")
        r = client.post(
            "/api/proxy/entities",
            json={"id": "urn:ngsi-ld:Test:001", "type": "Test"},
            params={"broker_base_url": "http://localhost:9999"},
        )
        # Debe responder 200 con status:0/error de red, NO 400 de validación de URL
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == 0
        assert "error" in data

    def test_unreachable_broker_returns_200_with_error(self, client):
        """Broker inaccesible → el proxy responde 200 con error en el body, nunca 5xx."""
        r = client.post(
            "/api/proxy/entities",
            json={"id": "urn:ngsi-ld:Test:001", "type": "Test"},
            params={"broker_base_url": "http://localhost:9999"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "error" in data or data.get("status") == 0


class TestProxyPatchValidation:
    """PATCH /api/proxy/entities/{id}/attrs — validación de broker_base_url."""

    def test_empty_broker_url_returns_400(self, client):
        r = client.patch(
            "/api/proxy/entities/urn:ngsi-ld:Test:001/attrs",
            json={"name": {"type": "Property", "value": "test"}},
        )
        assert r.status_code == 400

    def test_invalid_scheme_returns_400(self, client):
        r = client.patch(
            "/api/proxy/entities/urn:ngsi-ld:Test:001/attrs",
            json={"name": {"type": "Property", "value": "test"}},
            params={"broker_base_url": "ftp://malicious"},
        )
        assert r.status_code == 400

    def test_link_local_ip_returns_400(self, client):
        r = client.patch(
            "/api/proxy/entities/urn:ngsi-ld:Test:001/attrs",
            json={"name": {"type": "Property", "value": "test"}},
            params={"broker_base_url": "http://169.254.169.254"},
        )
        assert r.status_code == 400

    def test_unreachable_broker_returns_200_with_error(self, client):
        r = client.patch(
            "/api/proxy/entities/urn:ngsi-ld:Test:001/attrs",
            json={"name": {"type": "Property", "value": "test"}},
            params={"broker_base_url": "http://localhost:9999"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == 0 or "error" in data


class TestProxyDeleteValidation:
    """DELETE /api/proxy/entities/{id} — validación de broker_base_url."""

    def test_missing_broker_url_returns_422(self, client):
        """broker_base_url es requerido en DELETE → 422 si falta."""
        r = client.delete("/api/proxy/entities/urn:ngsi-ld:Test:001")
        assert r.status_code == 422

    def test_invalid_scheme_returns_400(self, client):
        r = client.delete(
            "/api/proxy/entities/urn:ngsi-ld:Test:001",
            params={"broker_base_url": "file:///etc/passwd"},
        )
        assert r.status_code == 400

    def test_link_local_ip_returns_400(self, client):
        r = client.delete(
            "/api/proxy/entities/urn:ngsi-ld:Test:001",
            params={"broker_base_url": "http://169.254.169.254"},
        )
        assert r.status_code == 400

    def test_unreachable_broker_returns_200_with_error(self, client):
        """Broker inaccesible → respuesta 200 con error de red."""
        r = client.delete(
            "/api/proxy/entities/urn:ngsi-ld:Test:001",
            params={"broker_base_url": "http://localhost:9999"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == 0 or "error" in data


class TestProxyDeleteEntityAttrValidation:
    """DELETE /api/proxy/entities/{id}/attr — validación de broker_base_url."""

    def test_missing_broker_url_returns_422(self, client):
        r = client.delete(
            "/api/proxy/entities/urn:ngsi-ld:Test:001/attr",
            params={"attr_name": "name"},
        )
        assert r.status_code == 422

    def test_invalid_scheme_returns_400(self, client):
        r = client.delete(
            "/api/proxy/entities/urn:ngsi-ld:Test:001/attr",
            params={"broker_base_url": "file:///etc/passwd", "attr_name": "name"},
        )
        assert r.status_code == 400

    def test_unreachable_broker_returns_200_with_error(self, client):
        r = client.delete(
            "/api/proxy/entities/urn:ngsi-ld:Test:001/attr",
            params={"broker_base_url": "http://localhost:9999", "attr_name": "name"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == 0 or "error" in data


class TestProxyGetEntitiesValidation:
    """GET /api/proxy/entities — validación de broker_base_url."""

    def test_missing_broker_url_returns_422(self, client):
        r = client.get("/api/proxy/entities")
        assert r.status_code == 422

    def test_invalid_scheme_returns_400(self, client):
        r = client.get(
            "/api/proxy/entities",
            params={"broker_base_url": "javascript://xss"},
        )
        assert r.status_code == 400

    def test_link_local_ip_returns_400(self, client):
        r = client.get(
            "/api/proxy/entities",
            params={"broker_base_url": "http://169.254.169.254"},
        )
        assert r.status_code == 400

    def test_unreachable_broker_returns_200_with_error(self, client):
        r = client.get(
            "/api/proxy/entities",
            params={"broker_base_url": "http://localhost:9999"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == 0 or "error" in data


class TestProxyGetEntityByIdValidation:
    """GET /api/proxy/entities/{id} — validación de broker_base_url."""

    def test_missing_broker_url_returns_422(self, client):
        r = client.get("/api/proxy/entities/urn:ngsi-ld:Test:001")
        assert r.status_code == 422

    def test_invalid_scheme_returns_400(self, client):
        r = client.get(
            "/api/proxy/entities/urn:ngsi-ld:Test:001",
            params={"broker_base_url": "file:///etc/hosts"},
        )
        assert r.status_code == 400

    def test_link_local_ip_returns_400(self, client):
        r = client.get(
            "/api/proxy/entities/urn:ngsi-ld:Test:001",
            params={"broker_base_url": "http://169.254.169.254"},
        )
        assert r.status_code == 400

    def test_unreachable_broker_returns_200_with_error(self, client):
        r = client.get(
            "/api/proxy/entities/urn:ngsi-ld:Test:001",
            params={"broker_base_url": "http://localhost:9999"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == 0 or "error" in data


class TestProxyGetSubscriptionsValidation:
    """GET /api/proxy/subscriptions — validación de broker_base_url."""

    def test_missing_broker_url_returns_422(self, client):
        r = client.get("/api/proxy/subscriptions")
        assert r.status_code == 422

    def test_invalid_scheme_returns_400(self, client):
        r = client.get(
            "/api/proxy/subscriptions",
            params={"broker_base_url": "javascript://xss"},
        )
        assert r.status_code == 400

    def test_unreachable_broker_returns_200_with_error(self, client):
        r = client.get(
            "/api/proxy/subscriptions",
            params={"broker_base_url": "http://localhost:9999"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == 0 or "error" in data
        assert isinstance(data.get("body"), list)


class TestProxyDeleteSubscriptionsValidation:
    """DELETE /api/proxy/subscriptions/{id} — validación de broker_base_url."""

    def test_missing_broker_url_returns_422(self, client):
        r = client.delete("/api/proxy/subscriptions/urn:ngsi-ld:Subscription:1")
        assert r.status_code == 422

    def test_invalid_scheme_returns_400(self, client):
        r = client.delete(
            "/api/proxy/subscriptions/urn:ngsi-ld:Subscription:1",
            params={"broker_base_url": "javascript://xss"},
        )
        assert r.status_code == 400

    def test_unreachable_broker_returns_200_with_error(self, client):
        r = client.delete(
            "/api/proxy/subscriptions/urn:ngsi-ld:Subscription:1",
            params={"broker_base_url": "http://localhost:9999"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == 0 or "error" in data


class TestEntityViewValidation:
    """GET /api/entities/{id}/view — validación y tolerancia a broker caído."""

    def test_missing_broker_url_returns_422(self, client):
        r = client.get("/api/entities/urn:ngsi-ld:Test:001/view")
        assert r.status_code == 422

    def test_invalid_scheme_returns_400(self, client):
        r = client.get(
            "/api/entities/urn:ngsi-ld:Test:001/view",
            params={"broker_base_url": "file:///etc/hosts"},
        )
        assert r.status_code == 400

    def test_unreachable_broker_returns_200_with_error(self, client):
        r = client.get(
            "/api/entities/urn:ngsi-ld:Test:001/view",
            params={"broker_base_url": "http://localhost:9999"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == 0 or data.get("error") is not None


class TestSchemaGraphBuild:
    """POST /api/graph/schema/build."""

    def test_build_schema_graph_returns_ok(self, client):
        r = client.post(
            "/api/graph/schema/build",
            json={
                "types": ["Machine", "Area"],
                "relationships": [{"from": "Machine", "to": "Area", "property": "locatedIn", "implicit": False}],
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert isinstance(data.get("nodes"), list)
        assert isinstance(data.get("links"), list)


class TestSchemaTypeViewBuild:
    """POST /api/graph/schema/type-view."""

    def test_build_schema_type_view_returns_ok(self, client):
        r = client.post(
            "/api/graph/schema/type-view",
            json={
                "type_id": "Machine",
                "relationships": [{"from": "Machine", "to": "Area", "property": "locatedIn", "implicit": False}],
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert data.get("view", {}).get("type_id") == "Machine"


class TestPrepareEntityPayload:
    """POST /api/entities/prepare-payload."""

    def test_prepare_entity_payload_returns_normalized_payload(self, client):
        r = client.post(
            "/api/entities/prepare-payload",
            json={
                "type": "Machine",
                "default_context": ["https://example.org/context.jsonld"],
                "payload": {"name": "Horno 1"},
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert data.get("input_mode") == "plain"
        prepared = data.get("payload_to_send") or {}
        assert prepared.get("type") == "Machine"
        assert prepared.get("id", "").startswith("urn:ngsi-ld:Machine:")
        assert isinstance(prepared.get("name"), dict)


class TestPrepareAttrsPayload:
    """POST /api/entities/prepare-attrs-payload."""

    def test_prepare_attrs_payload_wraps_plain_values(self, client):
        r = client.post(
            "/api/entities/prepare-attrs-payload",
            json={"attrs_payload": {"name": "Horno 1", "temperature": 23}},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        attrs = data.get("attrs_payload_to_send") or {}
        assert attrs.get("name", {}).get("type") == "Property"
        assert attrs.get("temperature", {}).get("value") == 23
