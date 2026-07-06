"""
Tests de integración para los endpoints de preparación de payloads de entidades.

  POST /api/entities/prepare-payload       — preparación de payload de creación
  POST /api/entities/prepare-attrs-payload — preparación de attrs para PATCH

No requieren Orion-LD real; validan la lógica de normalización del backend.
"""


# ══════════════════════════════════════════════════════════════════════════════
#  POST /api/entities/prepare-payload
# ══════════════════════════════════════════════════════════════════════════════

class TestPrepareEntityPayload:

    def test_returns_ok_true(self, client):
        r = client.post("/api/entities/prepare-payload", json={
            "type": "Machine",
            "payload": {"name": "Horno 1"},
        })
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_response_has_required_fields(self, client):
        r = client.post("/api/entities/prepare-payload", json={
            "type": "Machine",
            "payload": {"name": "Horno 1"},
        })
        data = r.json()
        assert "input_mode" in data
        assert "payload_for_validation" in data
        assert "payload_to_send" in data

    def test_type_injected_in_payload(self, client):
        """El campo 'type' del body se inyecta en el payload resultante."""
        r = client.post("/api/entities/prepare-payload", json={
            "type": "Building",
            "payload": {"category": "office"},
        })
        data = r.json()
        assert data["payload_to_send"]["type"] == "Building"
        assert data["payload_for_validation"]["type"] == "Building"

    def test_default_id_generated_when_missing(self, client):
        """Si el payload no tiene 'id', se genera uno con el patrón urn:ngsi-ld:{type}:001."""
        r = client.post("/api/entities/prepare-payload", json={
            "type": "Machine",
            "payload": {},
        })
        generated_id = r.json()["payload_to_send"].get("id", "")
        assert generated_id.startswith("urn:ngsi-ld:Machine:")

    def test_provided_id_is_preserved(self, client):
        """Si el payload ya tiene 'id', no se sobrescribe."""
        r = client.post("/api/entities/prepare-payload", json={
            "type": "Machine",
            "payload": {"id": "urn:ngsi-ld:Machine:custom-001"},
        })
        assert r.json()["payload_to_send"]["id"] == "urn:ngsi-ld:Machine:custom-001"

    def test_default_context_injected_when_missing(self, client):
        """Si el payload no tiene @context y se proporciona default_context, se inyecta."""
        ctx = ["https://example.org/context.jsonld"]
        r = client.post("/api/entities/prepare-payload", json={
            "type": "Machine",
            "payload": {"name": "test"},
            "default_context": ctx,
        })
        assert r.json()["payload_for_validation"].get("@context") == ctx

    def test_existing_context_not_overwritten(self, client):
        """Si el payload ya tiene @context, no se sustituye por default_context."""
        original_ctx = "https://original.org/context.jsonld"
        r = client.post("/api/entities/prepare-payload", json={
            "type": "Machine",
            "payload": {"name": "test", "@context": original_ctx},
            "default_context": ["https://different.org/context.jsonld"],
        })
        assert r.json()["payload_for_validation"]["@context"] == original_ctx

    def test_plain_input_mode_detected(self, client):
        """Payload con atributos planos (no NGSI-LD) → input_mode == 'plain'."""
        r = client.post("/api/entities/prepare-payload", json={
            "type": "Machine",
            "payload": {"name": "Horno 1", "temperature": 72.5},
        })
        assert r.json()["input_mode"] == "plain"

    def test_normalized_input_mode_detected(self, client):
        """Payload con atributos NGSI-LD normalizados → input_mode == 'normalized'."""
        r = client.post("/api/entities/prepare-payload", json={
            "type": "Machine",
            "payload": {
                "name": {"type": "Property", "value": "Horno 1"},
            },
        })
        assert r.json()["input_mode"] == "normalized"

    def test_plain_payload_normalized_in_payload_to_send(self, client):
        """En modo plain, payload_to_send debe tener atributos envueltos como NGSI-LD Property."""
        r = client.post("/api/entities/prepare-payload", json={
            "type": "Machine",
            "payload": {"name": "Horno 1", "temperature": 72.5},
        })
        payload_to_send = r.json()["payload_to_send"]
        assert isinstance(payload_to_send["name"], dict)
        assert payload_to_send["name"]["type"] == "Property"
        assert payload_to_send["name"]["value"] == "Horno 1"
        assert payload_to_send["temperature"]["value"] == 72.5

    def test_normalized_payload_unchanged_in_payload_to_send(self, client):
        """En modo normalized, payload_to_send es igual al payload_for_validation."""
        r = client.post("/api/entities/prepare-payload", json={
            "type": "Machine",
            "payload": {
                "name": {"type": "Property", "value": "Horno 1"},
            },
        })
        data = r.json()
        assert data["payload_to_send"]["name"] == {"type": "Property", "value": "Horno 1"}

    def test_missing_type_field_returns_422(self, client):
        """El campo 'type' es obligatorio."""
        r = client.post("/api/entities/prepare-payload", json={
            "payload": {"name": "sin tipo"},
        })
        assert r.status_code == 422

    def test_empty_payload_generates_minimal_entity(self, client):
        """Payload vacío debe generar una entidad mínima con id y type."""
        r = client.post("/api/entities/prepare-payload", json={
            "type": "Area",
            "payload": {},
        })
        data = r.json()
        assert data.get("ok") is True
        result = data["payload_to_send"]
        assert result["type"] == "Area"
        assert result.get("id", "").startswith("urn:ngsi-ld:Area:")

    def test_id_and_type_not_wrapped_as_properties(self, client):
        """Los campos 'id', 'type' y '@context' no deben ser envueltos en NGSI-LD Property."""
        r = client.post("/api/entities/prepare-payload", json={
            "type": "Machine",
            "payload": {"id": "urn:ngsi-ld:Machine:001", "name": "A"},
            "default_context": ["https://example.org/ctx"],
        })
        payload = r.json()["payload_to_send"]
        assert isinstance(payload["id"], str)
        assert isinstance(payload["type"], str)
        if "@context" in payload:
            assert not isinstance(payload["@context"], dict) or payload["@context"].get("type") != "Property"


# ══════════════════════════════════════════════════════════════════════════════
#  POST /api/entities/prepare-attrs-payload
# ══════════════════════════════════════════════════════════════════════════════

class TestPrepareAttrsPayload:

    def test_returns_ok_true(self, client):
        r = client.post("/api/entities/prepare-attrs-payload", json={
            "attrs_payload": {"name": "Horno 1"},
        })
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_response_has_attrs_payload_to_send(self, client):
        r = client.post("/api/entities/prepare-attrs-payload", json={
            "attrs_payload": {"name": "Horno 1"},
        })
        assert "attrs_payload_to_send" in r.json()

    def test_plain_string_wrapped_as_property(self, client):
        r = client.post("/api/entities/prepare-attrs-payload", json={
            "attrs_payload": {"name": "Horno 1"},
        })
        attr = r.json()["attrs_payload_to_send"]["name"]
        assert attr["type"] == "Property"
        assert attr["value"] == "Horno 1"

    def test_plain_number_wrapped_as_property(self, client):
        r = client.post("/api/entities/prepare-attrs-payload", json={
            "attrs_payload": {"temperature": 72.5},
        })
        attr = r.json()["attrs_payload_to_send"]["temperature"]
        assert attr["type"] == "Property"
        assert attr["value"] == 72.5

    def test_plain_boolean_wrapped_as_property(self, client):
        r = client.post("/api/entities/prepare-attrs-payload", json={
            "attrs_payload": {"online": True},
        })
        attr = r.json()["attrs_payload_to_send"]["online"]
        assert attr["type"] == "Property"
        assert attr["value"] is True

    def test_already_normalized_property_preserved(self, client):
        """Un atributo ya normalizado como Property se mantiene tal cual."""
        r = client.post("/api/entities/prepare-attrs-payload", json={
            "attrs_payload": {
                "name": {"type": "Property", "value": "Horno 1"},
            },
        })
        attr = r.json()["attrs_payload_to_send"]["name"]
        assert attr == {"type": "Property", "value": "Horno 1"}

    def test_already_normalized_relationship_preserved(self, client):
        """Un atributo ya normalizado como Relationship se mantiene tal cual."""
        r = client.post("/api/entities/prepare-attrs-payload", json={
            "attrs_payload": {
                "refArea": {"type": "Relationship", "object": "urn:ngsi-ld:Area:001"},
            },
        })
        attr = r.json()["attrs_payload_to_send"]["refArea"]
        assert attr == {"type": "Relationship", "object": "urn:ngsi-ld:Area:001"}

    def test_already_normalized_geo_property_preserved(self, client):
        """Un atributo GeoProperty se mantiene tal cual."""
        geo = {"type": "GeoProperty", "value": {"type": "Point", "coordinates": [-3.7, 40.4]}}
        r = client.post("/api/entities/prepare-attrs-payload", json={
            "attrs_payload": {"location": geo},
        })
        assert r.json()["attrs_payload_to_send"]["location"] == geo

    def test_mixed_plain_and_normalized_attrs(self, client):
        """Mezcla de atributos planos y normalizados procesados correctamente."""
        r = client.post("/api/entities/prepare-attrs-payload", json={
            "attrs_payload": {
                "name":     "Horno 1",                                              # plano
                "refArea":  {"type": "Relationship", "object": "urn:ngsi-ld:A:1"}, # ya normalizado
                "temp":     {"type": "Property", "value": 72.5},                   # ya normalizado
            },
        })
        result = r.json()["attrs_payload_to_send"]
        assert result["name"]["type"] == "Property"
        assert result["name"]["value"] == "Horno 1"
        assert result["refArea"]["type"] == "Relationship"
        assert result["temp"]["value"] == 72.5

    def test_multiple_plain_attrs_all_wrapped(self, client):
        r = client.post("/api/entities/prepare-attrs-payload", json={
            "attrs_payload": {
                "name":        "Edificio B",
                "floor":       3,
                "available":   False,
            },
        })
        result = r.json()["attrs_payload_to_send"]
        assert result["name"]["value"] == "Edificio B"
        assert result["floor"]["value"] == 3
        assert result["available"]["value"] is False

    def test_missing_attrs_payload_field_returns_422(self, client):
        """El campo attrs_payload es obligatorio."""
        r = client.post("/api/entities/prepare-attrs-payload", json={})
        assert r.status_code == 422

    def test_empty_attrs_payload_returns_ok(self, client):
        """Payload vacío es aceptado por el endpoint de preparación (validación posterior)."""
        r = client.post("/api/entities/prepare-attrs-payload", json={
            "attrs_payload": {},
        })
        assert r.status_code == 200
        assert r.json().get("ok") is True
        assert r.json()["attrs_payload_to_send"] == {}

    def test_list_value_wrapped_as_property(self, client):
        """Un atributo con valor lista se envuelve como Property."""
        r = client.post("/api/entities/prepare-attrs-payload", json={
            "attrs_payload": {"tags": ["a", "b", "c"]},
        })
        attr = r.json()["attrs_payload_to_send"]["tags"]
        assert attr["type"] == "Property"
        assert attr["value"] == ["a", "b", "c"]
