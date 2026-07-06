"""
Tests unitarios de las funciones auxiliares internas del backend.

Estas funciones no son endpoints HTTP; se importan directamente de main.py
y se prueban de forma aislada (sin cliente HTTP), lo que los hace muy rápidos.

Funciones cubiertas:
  - _to_plain_for_schema   : conversión de entidad NGSI-LD normalizada a plana
  - _is_normalized_entity  : detección de entidades normalizadas
  - _validate_broker_url   : validación de URLs de broker
  - _safe_member_name      : limpieza de nombres de ficheros en archivos comprimidos
  - _strip_root_folder     : eliminación de la carpeta raíz común en paquetes
  - _classify_members      : clasificación de ficheros del paquete en schemas/context/etc.
"""
import pytest
from fastapi import HTTPException

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import (
    _to_plain_for_schema,
    _is_normalized_entity,
    _validate_broker_url,
    _safe_member_name,
    _strip_root_folder,
    _classify_members,
    _build_orion_instance_graph,
    _entity_view_from_raw,
    _build_schema_graph_data,
    _build_schema_type_view,
    _detect_entity_input_mode,
    _normalize_entity_for_orion,
    _normalize_attrs_payload,
)


# ══════════════════════════════════════════════════════════════════════════════
#  _to_plain_for_schema
# ══════════════════════════════════════════════════════════════════════════════

class TestToPlainForSchema:

    def test_property_extracts_value(self):
        """Property → extrae el campo 'value'."""
        entity = {
            "id": "urn:ngsi-ld:Test:001",
            "type": "Test",
            "name": {"type": "Property", "value": "Horno A"},
        }
        result = _to_plain_for_schema(entity)
        assert result["name"] == "Horno A"

    def test_property_numeric_value(self):
        """Property con valor numérico → extrae el número."""
        entity = {
            "id": "urn:ngsi-ld:Test:001",
            "type": "Test",
            "temperature": {"type": "Property", "value": 72.5},
        }
        result = _to_plain_for_schema(entity)
        assert result["temperature"] == 72.5

    def test_property_boolean_value(self):
        """Property con valor booleano → extrae el booleano."""
        entity = {"id": "x", "type": "T", "online": {"type": "Property", "value": True}}
        result = _to_plain_for_schema(entity)
        assert result["online"] is True

    def test_relationship_extracts_object(self):
        """Relationship → extrae el campo 'object' (el URN)."""
        entity = {
            "id": "urn:ngsi-ld:Op:001",
            "type": "Op",
            "machine": {"type": "Relationship", "object": "urn:ngsi-ld:Machine:001"},
        }
        result = _to_plain_for_schema(entity)
        assert result["machine"] == "urn:ngsi-ld:Machine:001"

    def test_geo_property_extracts_geojson(self):
        """GeoProperty → extrae el GeoJSON (value), no el objeto NGSI-LD completo."""
        geojson = {"type": "Point", "coordinates": [-3.7038, 40.4168]}
        entity = {
            "id": "urn:ngsi-ld:Machine:001",
            "type": "Machine",
            "location": {"type": "GeoProperty", "value": geojson},
        }
        result = _to_plain_for_schema(entity)
        assert result["location"] == geojson
        assert result["location"]["type"] == "Point"

    def test_id_type_context_preserved_unchanged(self):
        """id, type y @context se copian sin transformación."""
        entity = {
            "id": "urn:ngsi-ld:Test:001",
            "type": "Test",
            "@context": "http://example.org/context",
        }
        result = _to_plain_for_schema(entity)
        assert result["id"] == entity["id"]
        assert result["type"] == entity["type"]
        assert result["@context"] == entity["@context"]

    def test_plain_attribute_unchanged(self):
        """Atributo que ya es plano (no es dict NGSI-LD) se copia sin cambios."""
        entity = {"id": "x", "type": "T", "name": "valor_plano"}
        result = _to_plain_for_schema(entity)
        assert result["name"] == "valor_plano"

    def test_unknown_ngsi_type_preserved_as_dict(self):
        """Atributo con type desconocido se preserva como dict."""
        entity = {"id": "x", "type": "T", "attr": {"type": "Unknown", "value": 1}}
        result = _to_plain_for_schema(entity)
        assert isinstance(result["attr"], dict)

    def test_non_dict_input_returned_unchanged(self):
        """Si el input no es dict, se devuelve tal cual."""
        assert _to_plain_for_schema("no es un dict") == "no es un dict"
        assert _to_plain_for_schema(None) is None
        assert _to_plain_for_schema(42) == 42


# ══════════════════════════════════════════════════════════════════════════════
#  _is_normalized_entity
# ══════════════════════════════════════════════════════════════════════════════

class TestIsNormalizedEntity:

    def test_entity_with_property_is_normalized(self):
        entity = {
            "id": "urn:ngsi-ld:X:1",
            "type": "X",
            "name": {"type": "Property", "value": "test"},
        }
        assert _is_normalized_entity(entity) is True

    def test_entity_with_relationship_is_normalized(self):
        entity = {
            "id": "urn:ngsi-ld:X:1",
            "type": "X",
            "ref": {"type": "Relationship", "object": "urn:ngsi-ld:Y:1"},
        }
        assert _is_normalized_entity(entity) is True

    def test_plain_entity_not_normalized(self):
        entity = {"id": "urn:ngsi-ld:X:1", "type": "X", "name": "plano"}
        assert _is_normalized_entity(entity) is False

    def test_only_id_type_context_not_normalized(self):
        """Una entidad con solo id/type/@context no se considera normalizada."""
        entity = {"id": "urn:ngsi-ld:X:1", "type": "X", "@context": "http://ctx"}
        assert _is_normalized_entity(entity) is False

    def test_non_dict_input_returns_false(self):
        assert _is_normalized_entity("not a dict") is False
        assert _is_normalized_entity(None) is False


# ══════════════════════════════════════════════════════════════════════════════
#  _validate_broker_url
# ══════════════════════════════════════════════════════════════════════════════

class TestValidateBrokerUrl:

    def test_valid_http_url_does_not_raise(self):
        """Una URL http válida no debe lanzar excepción."""
        _validate_broker_url("http://localhost:1026")  # no raise

    def test_valid_https_url_does_not_raise(self):
        _validate_broker_url("https://broker.example.com:1026")  # no raise

    def test_empty_string_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            _validate_broker_url("")
        assert exc.value.status_code == 400

    def test_whitespace_only_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            _validate_broker_url("   ")
        assert exc.value.status_code == 400

    def test_file_scheme_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            _validate_broker_url("file:///etc/passwd")
        assert exc.value.status_code == 400

    def test_ftp_scheme_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            _validate_broker_url("ftp://evil.com")
        assert exc.value.status_code == 400

    def test_javascript_scheme_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            _validate_broker_url("javascript://xss")
        assert exc.value.status_code == 400

    def test_link_local_ipv4_raises_400(self):
        """169.254.x.x es una dirección link-local usada por servicios de metadatos cloud."""
        with pytest.raises(HTTPException) as exc:
            _validate_broker_url("http://169.254.169.254/latest/meta-data")
        assert exc.value.status_code == 400

    def test_link_local_ipv4_any_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            _validate_broker_url("http://169.254.0.1")
        assert exc.value.status_code == 400

    def test_localhost_is_valid(self):
        """localhost debe ser aceptado (Orion típicamente corre en localhost)."""
        _validate_broker_url("http://localhost:1026")  # no raise

    def test_127_0_0_1_is_valid(self):
        """127.0.0.1 debe ser aceptado."""
        _validate_broker_url("http://127.0.0.1:1026")  # no raise


# ══════════════════════════════════════════════════════════════════════════════
#  _safe_member_name
# ══════════════════════════════════════════════════════════════════════════════

class TestSafeMemberName:

    def test_normal_path_unchanged(self):
        assert _safe_member_name("schemas/Building.json") == "schemas/Building.json"

    def test_path_traversal_returns_none(self):
        """../etc/passwd es path traversal → la función devuelve None (rechazar)."""
        result = _safe_member_name("../../../etc/passwd")
        assert result is None

    def test_absolute_path_stripped(self):
        """/etc/passwd → se elimina la barra inicial, no devuelve ruta absoluta."""
        result = _safe_member_name("/etc/passwd")
        assert result is not None
        assert not result.startswith("/")

    def test_mixed_traversal_returns_none(self):
        """Traversal embebido en la ruta → devuelve None."""
        result = _safe_member_name("schemas/../../etc/passwd")
        assert result is None

    def test_empty_string_returns_empty(self):
        assert _safe_member_name("") == ""


# ══════════════════════════════════════════════════════════════════════════════
#  _strip_root_folder
# ══════════════════════════════════════════════════════════════════════════════

class TestStripRootFolder:

    def test_single_root_folder_stripped(self):
        """Carpeta raíz común única es eliminada."""
        members = {
            "mi-modelo/schemas/Building.json": b"{}",
            "mi-modelo/context/ctx.jsonld": b"{}",
            "mi-modelo/descriptor.json": b"{}",
        }
        result = _strip_root_folder(members)
        assert "schemas/Building.json" in result
        assert "context/ctx.jsonld" in result
        assert "descriptor.json" in result
        assert not any(k.startswith("mi-modelo/") for k in result)

    def test_no_common_root_preserved(self):
        """Si no hay carpeta raíz común, los paths se mantienen."""
        members = {
            "schemas/Building.json": b"{}",
            "context/ctx.jsonld": b"{}",
        }
        result = _strip_root_folder(members)
        assert "schemas/Building.json" in result
        assert "context/ctx.jsonld" in result

    def test_multiple_root_folders_not_stripped(self):
        """Si hay múltiples carpetas raíz, no se elimina ninguna."""
        members = {
            "carpeta-a/schemas/Building.json": b"{}",
            "carpeta-b/context/ctx.jsonld": b"{}",
        }
        result = _strip_root_folder(members)
        assert "carpeta-a/schemas/Building.json" in result
        assert "carpeta-b/context/ctx.jsonld" in result

    def test_empty_members_returns_empty(self):
        assert _strip_root_folder({}) == {}


# ══════════════════════════════════════════════════════════════════════════════
#  _classify_members
# ══════════════════════════════════════════════════════════════════════════════

class TestClassifyMembers:

    SCHEMA_JSON = b'{"$schema":"https://json-schema.org/draft/2020-12/schema","title":"T","type":"object"}'
    CONTEXT_JSON = b'{"@context":{"T":"https://example.org/T"}}'
    DESCRIPTOR_JSON = b'{"relationships":[]}'
    EXAMPLE_JSON = b'{"id":"urn:ngsi-ld:T:001","type":"T"}'

    def test_schema_files_classified(self):
        members = {"schemas/T.json": self.SCHEMA_JSON}
        result = _classify_members(members)
        assert len(result["schemas"]) == 1
        assert result["context"] is None

    def test_context_file_classified(self):
        members = {"context/context.jsonld": self.CONTEXT_JSON}
        result = _classify_members(members)
        assert result["context"] is not None
        assert len(result["schemas"]) == 0

    def test_descriptor_classified(self):
        members = {"descriptor.json": self.DESCRIPTOR_JSON}
        result = _classify_members(members)
        assert result["descriptor"] is not None

    def test_example_subfolder_structure(self):
        """examples/Tipo/example.json → clave es el nombre del subdirectorio."""
        members = {"examples/Building/example.json": self.EXAMPLE_JSON}
        result = _classify_members(members)
        assert "Building" in result["examples"]

    def test_example_flat_structure(self):
        """examples/Building.json → clave es Building."""
        members = {"examples/Building.json": self.EXAMPLE_JSON}
        result = _classify_members(members)
        assert "Building" in result["examples"]

    def test_first_context_wins(self):
        """Si hay dos ficheros de contexto, solo se guarda el primero."""
        ctx2 = b'{"@context":{"Other":"https://example.org/Other"}}'
        members = {
            "context/ctx1.jsonld": self.CONTEXT_JSON,
            "context/ctx2.jsonld": ctx2,
        }
        result = _classify_members(members)
        assert result["context"] is not None
        # Solo debe haber un contexto
        assert "@context" in result["context"]

    def test_invalid_json_added_to_unrecognized(self):
        """Fichero .json con JSON inválido se añade a unrecognized, no a schemas."""
        members = {"schemas/broken.json": b"{ esto no es json }}}"}
        result = _classify_members(members)
        assert len(result["schemas"]) == 0
        assert len(result["unrecognized"]) == 1

    def test_non_json_files_ignored(self):
        """Ficheros .txt y otros formatos no reconocidos se ignoran."""
        members = {
            "schemas/readme.txt": b"hello",
            "context/image.png": b"\x89PNG",
        }
        result = _classify_members(members)
        assert len(result["schemas"]) == 0
        assert result["context"] is None
        assert len(result["unrecognized"]) == 0  # no son JSON, simplemente se ignoran

    def test_complete_package_classified(self):
        """Un paquete completo clasifica correctamente todos los elementos."""
        members = {
            "schemas/T.json": self.SCHEMA_JSON,
            "context/ctx.jsonld": self.CONTEXT_JSON,
            "descriptor.json": self.DESCRIPTOR_JSON,
            "examples/T/example.json": self.EXAMPLE_JSON,
        }
        result = _classify_members(members)
        assert len(result["schemas"]) == 1
        assert result["context"] is not None
        assert result["descriptor"] is not None
        assert "T" in result["examples"]


class TestBuildOrionInstanceGraph:

    def test_build_graph_marks_implicit_and_explicit_relationships(self):
        entities = [
            {
                "id": "urn:ngsi-ld:Machine:001",
                "type": "Machine",
                "locatedIn": {"type": "Relationship", "object": "urn:ngsi-ld:Area:001"},
                "operator": {"type": "Property", "value": "urn:ngsi-ld:Person:001"},
            }
        ]
        relationships = [
            {
                "from": "Machine",
                "to": "Area",
                "property": "https://example.org/locatedIn",
                "implicit": False,
            }
        ]
        graph = _build_orion_instance_graph(entities, relationships)
        links = graph["links"]
        assert len(graph["nodes"]) == 3
        assert len(links) == 2
        located = next(l for l in links if l["property"] == "locatedIn")
        operator = next(l for l in links if l["property"] == "operator")
        assert located["implicit"] is False
        assert operator["implicit"] is True


class TestEntityViewFromRaw:

    def test_builds_enriched_attrs_for_panel(self):
        entity = {
            "id": "urn:ngsi-ld:Machine:001",
            "type": "Machine",
            "https://schema.org/name": {"type": "Property", "value": "Horno 1"},
            "https://example.org/locatedIn": {"type": "Relationship", "object": "urn:ngsi-ld:Area:001"},
        }
        view = _entity_view_from_raw(entity)
        assert view["id"] == "urn:ngsi-ld:Machine:001"
        assert len(view["attrs"]) == 2
        name_attr = next(a for a in view["attrs"] if a["short"] == "name")
        assert name_attr["typeTag"] == "Property"
        assert "Horno 1" in name_attr["value"]


class TestBuildSchemaGraphData:

    def test_builds_schema_graph_with_metrics(self):
        types = ["Machine", "Area"]
        relationships = [
            {"from": "Machine", "to": "Area", "property": "locatedIn", "implicit": False},
            {"from": "Unknown", "to": "Area", "property": "ignored", "implicit": False},
        ]
        graph = _build_schema_graph_data(types, relationships)
        assert len(graph["nodes"]) == 2
        assert len(graph["links"]) == 1
        assert graph["metrics"]["out_degree"]["Machine"] == 1
        assert graph["metrics"]["in_degree"]["Area"] == 1


class TestBuildSchemaTypeView:

    def test_builds_from_and_to_relationship_lists(self):
        relationships = [
            {"from": "Machine", "to": "Area", "property": "https://example.org/locatedIn", "implicit": False},
            {"from": "Plant", "to": "Machine", "property": "https://example.org/hasMachine", "implicit": True},
        ]
        view = _build_schema_type_view("Machine", relationships)
        assert view["type_id"] == "Machine"
        assert len(view["from_rels"]) == 1
        assert len(view["to_rels"]) == 1
        assert view["from_rels"][0]["property_short"] == "locatedIn"


class TestPrepareEntityPayloadHelpers:

    def test_detect_entity_input_mode_plain_vs_normalized(self):
        plain = {"id": "urn:ngsi-ld:T:1", "type": "T", "name": "A"}
        normalized = {"id": "urn:ngsi-ld:T:1", "type": "T", "name": {"type": "Property", "value": "A"}}
        assert _detect_entity_input_mode(plain) == "plain"
        assert _detect_entity_input_mode(normalized) == "normalized"

    def test_normalize_entity_for_orion_wraps_plain_attrs(self):
        payload = {"id": "urn:ngsi-ld:T:1", "type": "T", "name": "A", "count": 2}
        norm = _normalize_entity_for_orion(payload)
        assert norm["name"]["type"] == "Property"
        assert norm["name"]["value"] == "A"
        assert norm["count"]["value"] == 2

    def test_normalize_attrs_payload_wraps_plain_values(self):
        attrs = {"name": "A", "temperature": 21}
        norm = _normalize_attrs_payload(attrs)
        assert norm["name"]["type"] == "Property"
        assert norm["temperature"]["value"] == 21
