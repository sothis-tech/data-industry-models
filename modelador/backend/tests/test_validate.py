"""
Tests del endpoint de validación de entidades (/api/validate/entity y /api/validate/attrs).

Verifican que el backend acepta payloads válidos, rechaza payloads inválidos,
maneja correctamente schemas con campos required, convierte entidades normalizadas
y valida todos los tipos de atributos NGSI-LD (Property, Relationship, GeoProperty).
"""
import pytest


SCHEMA_PERSON = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Person",
    "type": "object",
    "properties": {
        "id":   {"type": "string"},
        "type": {"type": "string"},
        "name": {"type": "string"},
    },
    "required": ["id", "type", "name"],
}

SCHEMA_BUILDING = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Building",
    "type": "object",
    "properties": {
        "id":       {"type": "string"},
        "type":     {"type": "string"},
        "category": {"type": "string"},
        "address":  {"type": "string"},
    },
    "required": ["id", "type", "category", "address"],
}

SCHEMA_MACHINE = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ManufacturingMachine",
    "type": "object",
    "properties": {
        "id":       {"type": "string"},
        "type":     {"type": "string"},
        "name":     {"type": "string"},
        "location": {
            "type": "object",
            "properties": {
                "type":        {"type": "string"},
                "coordinates": {"type": "array"},
            },
        },
    },
    "required": ["id", "type"],
}

# Modelo genérico: propiedades declaradas como array en schema, típico en modelos sectoriales
# cuando NGSI-LD lleva un único string en Property.value.
SCHEMA_TAGS_AND_KIND = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "GenericThing",
    "type": "object",
    "properties": {
        "id":   {"type": "string"},
        "type": {"type": "string"},
        "name": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "kind": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["id", "type", "tags", "kind"],
}


class TestValidateEntity:

    def test_valid_payload_passes(self, client):
        """Un payload que cumple el schema debe pasar la validación."""
        r = client.post("/api/validate/entity", json={
            "payload": {"id": "urn:ngsi-ld:Person:001", "type": "Person", "name": "Ana"},
            "schema_doc": SCHEMA_PERSON,
            "payload_mode": "plain",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_missing_required_field_fails(self, client):
        """Falta un campo required → validación debe fallar con mensaje claro."""
        r = client.post("/api/validate/entity", json={
            "payload": {"id": "urn:ngsi-ld:Person:001", "type": "Person"},  # sin 'name'
            "schema_doc": SCHEMA_PERSON,
            "payload_mode": "plain",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        messages = " ".join(e.get("message", "") for e in data["errors"])
        assert "name" in messages.lower()

    def test_multiple_missing_required_fields(self, client):
        """Múltiples campos required faltantes → todos deben reportarse."""
        r = client.post("/api/validate/entity", json={
            "payload": {"id": "urn:ngsi-ld:Building:001", "type": "Building"},
            "schema_doc": SCHEMA_BUILDING,
            "payload_mode": "plain",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        messages = " ".join(e.get("message", "") for e in data["errors"])
        assert "category" in messages.lower() or "address" in messages.lower()

    def test_normalized_payload_mode(self, client):
        """En modo normalized, los valores van envueltos en {type, value}."""
        r = client.post("/api/validate/entity", json={
            "payload": {
                "id": "urn:ngsi-ld:Person:001",
                "type": "Person",
                "name": {"type": "Property", "value": "Ana"},
            },
            "schema_doc": SCHEMA_PERSON,
            "payload_mode": "normalized",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True

    def test_normalized_relationship_extracted_for_validation(self, client):
        """En modo normalized, un Relationship extrae 'object' para validar."""
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Op",
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "type": {"type": "string"},
                "machine": {"type": "string"},  # el schema espera string (el URN)
            },
            "required": ["id", "type", "machine"],
        }
        r = client.post("/api/validate/entity", json={
            "payload": {
                "id": "urn:ngsi-ld:Op:001",
                "type": "Op",
                "machine": {"type": "Relationship", "object": "urn:ngsi-ld:Machine:001"},
            },
            "schema_doc": schema,
            "payload_mode": "normalized",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True

    def test_normalized_geo_property_extracted_for_validation(self, client):
        """En modo normalized, GeoProperty extrae 'value' (el GeoJSON) para validar."""
        r = client.post("/api/validate/entity", json={
            "payload": {
                "id": "urn:ngsi-ld:ManufacturingMachine:001",
                "type": "ManufacturingMachine",
                "location": {
                    "type": "GeoProperty",
                    "value": {"type": "Point", "coordinates": [-3.7038, 40.4168]},
                },
            },
            "schema_doc": SCHEMA_MACHINE,
            "payload_mode": "normalized",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True

    def test_auto_mode_detects_normalized_entity(self, client):
        """En modo auto, el backend detecta entidades normalizadas y las convierte."""
        r = client.post("/api/validate/entity", json={
            "payload": {
                "id": "urn:ngsi-ld:Person:001",
                "type": "Person",
                "name": {"type": "Property", "value": "Ana"},
            },
            "schema_doc": SCHEMA_PERSON,
            "payload_mode": "auto",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True

    def test_auto_mode_accepts_plain_entity(self, client):
        """En modo auto, entidades planas se validan directamente sin conversión."""
        r = client.post("/api/validate/entity", json={
            "payload": {"id": "urn:ngsi-ld:Person:001", "type": "Person", "name": "Ana"},
            "schema_doc": SCHEMA_PERSON,
            "payload_mode": "auto",
        })
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_scalar_coerced_to_array_when_schema_expects_array_normalized(self, client):
        """Property con value escalar + schema type array → se envuelve en lista para validar."""
        r = client.post("/api/validate/entity", json={
            "payload": {
                "id": "urn:ngsi-ld:GenericThing:001",
                "type": "GenericThing",
                "name": {"type": "Property", "value": "X"},
                "tags": {"type": "Property", "value": "alpha"},
                "kind": {"type": "Property", "value": "beta"},
            },
            "schema_doc": SCHEMA_TAGS_AND_KIND,
            "payload_mode": "auto",
        })
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_scalar_coerced_to_array_when_schema_expects_array_plain(self, client):
        """Payload plano con escalares donde el schema pide array → válido tras coerción."""
        r = client.post("/api/validate/entity", json={
            "payload": {
                "id": "urn:ngsi-ld:GenericThing:001",
                "type": "GenericThing",
                "tags": "alpha",
                "kind": "beta",
            },
            "schema_doc": SCHEMA_TAGS_AND_KIND,
            "payload_mode": "plain",
        })
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_allof_merged_properties_used_for_array_coercion(self, client):
        """Properties solo dentro de allOf se consideran para la coerción array ← escalar."""
        schema_wrapped = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "allOf": [
                {
                    "type": "object",
                    "properties": {
                        "id":   {"type": "string"},
                        "type": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["id", "type", "tags"],
                },
            ],
        }
        r = client.post("/api/validate/entity", json={
            "payload": {
                "id": "urn:ngsi-ld:Thing:1",
                "type": "Thing",
                "tags": {"type": "Property", "value": "single"},
            },
            "schema_doc": schema_wrapped,
            "payload_mode": "auto",
        })
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_array_coercion_with_nested_ref_to_definitions(self, client):
        """
        Patrón Smart Data Models: propiedad usa $ref a #/definitions/X donde X es type array.
        La coerción debe resolver la ref en el documento correcto (no solo el schema raíz).
        """
        schema_nested = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://example.org/schemas/device-bundle.json",
            "type": "object",
            "allOf": [
                {
                    "$ref": "https://example.org/schemas/device-bundle.json#/definitions/Commons",
                },
            ],
            "definitions": {
                "ListOfText": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "Commons": {
                    "type": "object",
                    "properties": {
                        "id":   {"type": "string"},
                        "type": {"type": "string"},
                        "tags": {
                            "$ref": "#/definitions/ListOfText",
                        },
                    },
                    "required": ["id", "type", "tags"],
                },
            },
        }
        r = client.post("/api/validate/entity", json={
            "payload": {
                "id": "urn:ngsi-ld:Device:1",
                "type": "Device",
                "tags": {"type": "Property", "value": "one"},
            },
            "schema_doc": schema_nested,
            "payload_mode": "auto",
        })
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_missing_schema_returns_error(self, client):
        """Sin schema_doc, el endpoint debe devolver un error claro."""
        r = client.post("/api/validate/entity", json={
            "payload": {"id": "test", "type": "Test"},
            "payload_mode": "plain",
        })
        assert r.status_code in (200, 422)

    def test_extra_fields_do_not_cause_failure_by_default(self, client):
        """Campos extra no definidos en el schema no deben causar fallo (additionalProperties no restringido)."""
        r = client.post("/api/validate/entity", json={
            "payload": {
                "id": "urn:ngsi-ld:Person:001",
                "type": "Person",
                "name": "Ana",
                "unknownField": "extra",
            },
            "schema_doc": SCHEMA_PERSON,
            "payload_mode": "plain",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True

    def test_response_always_has_valid_and_errors_fields(self, client):
        """La respuesta siempre debe tener 'valid' (bool) y 'errors' (list)."""
        r = client.post("/api/validate/entity", json={
            "payload": {"id": "urn:ngsi-ld:Person:001", "type": "Person", "name": "Ana"},
            "schema_doc": SCHEMA_PERSON,
            "payload_mode": "plain",
        })
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data.get("valid"), bool)
        assert isinstance(data.get("errors"), list)


class TestValidateAttrs:

    def test_valid_normalized_attrs(self, client):
        """Atributos NGSI-LD normalizados deben pasar la validación de attrs."""
        r = client.post("/api/validate/attrs", json={
            "attrs_payload": {
                "name":        {"type": "Property",     "value": "Edificio A"},
                "temperature": {"type": "Property",     "value": 22.5},
                "refDevice":   {"type": "Relationship", "object": "urn:ngsi-ld:Device:001"},
            }
        })
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_invalid_attr_type(self, client):
        """Un atributo con type desconocido debe fallar."""
        r = client.post("/api/validate/attrs", json={
            "attrs_payload": {
                "name": {"type": "WrongType", "value": "test"},
            }
        })
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert any("WrongType" in e.get("message", "") or "Property" in e.get("message", "")
                   for e in data["errors"])

    def test_property_missing_value_fails(self, client):
        """Property sin campo value debe fallar."""
        r = client.post("/api/validate/attrs", json={
            "attrs_payload": {
                "name": {"type": "Property"},  # sin 'value'
            }
        })
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert any("value" in e.get("message", "").lower() for e in data["errors"])

    def test_relationship_missing_object_fails(self, client):
        """Relationship sin campo object debe fallar."""
        r = client.post("/api/validate/attrs", json={
            "attrs_payload": {
                "refDevice": {"type": "Relationship"},  # sin 'object'
            }
        })
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert any("object" in e.get("message", "").lower() for e in data["errors"])

    def test_relationship_with_object_passes(self, client):
        """Relationship con campo object es válido."""
        r = client.post("/api/validate/attrs", json={
            "attrs_payload": {
                "refDevice": {"type": "Relationship", "object": "urn:ngsi-ld:Device:001"},
            }
        })
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_geo_property_valid(self, client):
        """GeoProperty con value GeoJSON Point es válido."""
        r = client.post("/api/validate/attrs", json={
            "attrs_payload": {
                "location": {
                    "type": "GeoProperty",
                    "value": {"type": "Point", "coordinates": [-3.7038, 40.4168]},
                }
            }
        })
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_geo_property_without_value_fails(self, client):
        """GeoProperty sin campo value debe fallar."""
        r = client.post("/api/validate/attrs", json={
            "attrs_payload": {
                "location": {"type": "GeoProperty"}
            }
        })
        assert r.status_code == 200
        assert r.json()["valid"] is False

    def test_attr_not_an_object_fails(self, client):
        """Un atributo que no es objeto (es string) debe fallar."""
        r = client.post("/api/validate/attrs", json={
            "attrs_payload": {
                "name": "valor_plano_sin_envolver",
            }
        })
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert any("objeto" in e.get("message", "").lower() for e in data["errors"])

    def test_empty_attrs_rejected(self, client):
        """{} vacío es inválido: no tiene sentido enviar un PATCH sin atributos."""
        r = client.post("/api/validate/attrs", json={"attrs_payload": {}})
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_mixed_valid_and_invalid_attrs(self, client):
        """Si hay un atributo inválido entre varios válidos, el resultado es invalid."""
        r = client.post("/api/validate/attrs", json={
            "attrs_payload": {
                "name":    {"type": "Property",  "value": "ok"},
                "broken":  {"type": "Property"},             # sin value
                "rel":     {"type": "Relationship", "object": "urn:ngsi-ld:X:1"},
            }
        })
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        # Solo debe reportar el atributo inválido
        assert len(data["errors"]) == 1
        assert data["errors"][0]["path"] == "/broken"

    def test_multiple_invalid_attrs_all_reported(self, client):
        """Varios atributos inválidos → todos se reportan."""
        r = client.post("/api/validate/attrs", json={
            "attrs_payload": {
                "a": {"type": "Property"},      # sin value
                "b": {"type": "Relationship"},  # sin object
            }
        })
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert len(data["errors"]) == 2
