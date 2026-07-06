"""
Tests del endpoint de subida de paquetes de modelo (/api/upload/model-package).

Verifican que:
- Un ZIP válido con la estructura completa se procesa bien.
- Estructuras parciales (solo schemas, solo contexto, etc.) se manejan correctamente.
- Los ejemplos se indexan correctamente (subcarpeta y estructura plana).
- Múltiples ejemplos del mismo tipo: solo se guarda el primero.
- Ficheros no reconocibles o con JSON inválido se ignoran sin romper la carga.
- Path traversal en nombres de entrada es ignorado de forma segura.
- Límites de tamaño y número de ficheros son respetados.
"""
import io
import json
import zipfile
import pytest


def make_zip(files: dict[str, str]) -> bytes:
    """Crea un ZIP en memoria con los ficheros indicados {nombre: contenido}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


SAMPLE_SCHEMA = json.dumps({
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Building",
    "type": "object",
    "properties": {"id": {"type": "string"}, "type": {"type": "string"}},
})

SAMPLE_SCHEMA_DEVICE = json.dumps({
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Device",
    "type": "object",
    "properties": {"id": {"type": "string"}, "type": {"type": "string"}},
})

SAMPLE_CONTEXT = json.dumps({
    "@context": {
        "Building": "https://example.org/Building",
        "name": "https://schema.org/name",
    }
})

SAMPLE_DESCRIPTOR = json.dumps({
    "relationships": [
        {"sourceType": "Building", "property": "hasPart", "targetType": "Device"}
    ]
})

SAMPLE_EXAMPLE_BUILDING = json.dumps({
    "id": "urn:ngsi-ld:Building:001",
    "type": "Building",
    "name": {"type": "Property", "value": "Edificio A"},
})

SAMPLE_EXAMPLE_BUILDING_2 = json.dumps({
    "id": "urn:ngsi-ld:Building:002",
    "type": "Building",
    "name": {"type": "Property", "value": "Edificio B"},
})

SAMPLE_EXAMPLE_DEVICE = json.dumps({
    "id": "urn:ngsi-ld:Device:001",
    "type": "Device",
    "name": {"type": "Property", "value": "Sensor 1"},
})


class TestUploadStructureComplete:

    def test_valid_zip_with_all_sections(self, client):
        """ZIP con schemas/, context/, descriptor.json y examples/ se procesa correctamente."""
        content = make_zip({
            "mi-modelo/schemas/Building.json": SAMPLE_SCHEMA,
            "mi-modelo/context/context.jsonld": SAMPLE_CONTEXT,
            "mi-modelo/descriptor.json": SAMPLE_DESCRIPTOR,
            "mi-modelo/examples/Building/example.json": SAMPLE_EXAMPLE_BUILDING,
        })
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("modelo.zip", io.BytesIO(content), "application/zip")},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["schemas"]) == 1
        assert data["context"] is not None
        assert data["descriptor"] is not None
        assert "Building" in data["examples"]
        s = data["summary"]
        assert s["schemas"] == 1
        assert s["context"] is True
        assert s["descriptor"] is True
        assert s["examples"] == 1

    def test_zip_multiple_schemas(self, client):
        """ZIP con varios schemas los incluye todos."""
        content = make_zip({
            "paquete/schemas/Building.json": SAMPLE_SCHEMA,
            "paquete/schemas/Device.json": SAMPLE_SCHEMA_DEVICE,
        })
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("multi.zip", io.BytesIO(content), "application/zip")},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["schemas"]) == 2
        assert data["summary"]["schemas"] == 2


class TestUploadPartialStructures:

    def test_zip_schemas_only(self, client):
        """ZIP con solo schemas/ responde 200 y devuelve schemas."""
        content = make_zip({"paquete/schemas/Building.json": SAMPLE_SCHEMA})
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("schemas.zip", io.BytesIO(content), "application/zip")},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["schemas"]) == 1
        assert data["context"] is None
        assert data["descriptor"] is None

    def test_zip_context_only(self, client):
        """ZIP con solo context/ responde 200 y devuelve contexto."""
        content = make_zip({"paquete/context/context.jsonld": SAMPLE_CONTEXT})
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("ctx.zip", io.BytesIO(content), "application/zip")},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["context"] is not None
        assert len(data["schemas"]) == 0

    def test_zip_descriptor_only(self, client):
        """ZIP con solo descriptor.json responde 200."""
        content = make_zip({"paquete/descriptor.json": SAMPLE_DESCRIPTOR})
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("desc.zip", io.BytesIO(content), "application/zip")},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["descriptor"] is not None
        assert len(data["schemas"]) == 0
        assert data["context"] is None

    def test_zip_examples_only_returns_422(self, client):
        """ZIP con solo examples/ (sin schemas, context ni descriptor) devuelve 422."""
        content = make_zip({
            "paquete/examples/Building/example.json": SAMPLE_EXAMPLE_BUILDING,
        })
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("ex.zip", io.BytesIO(content), "application/zip")},
        )
        assert r.status_code == 422

    def test_zip_without_root_folder_flat(self, client):
        """ZIP con estructura plana (sin carpeta raíz) es manejado correctamente."""
        content = make_zip({
            "schemas/Building.json": SAMPLE_SCHEMA,
            "context/context.jsonld": SAMPLE_CONTEXT,
        })
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("flat.zip", io.BytesIO(content), "application/zip")},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["schemas"]) == 1
        assert data["context"] is not None


class TestUploadExamples:

    def test_examples_subfolder_structure(self, client):
        """Estructura examples/Tipo/example.json indexa por nombre de carpeta."""
        content = make_zip({
            "paquete/schemas/Building.json": SAMPLE_SCHEMA,
            "paquete/examples/Building/example.json": SAMPLE_EXAMPLE_BUILDING,
            "paquete/examples/Device/device.json": SAMPLE_EXAMPLE_DEVICE,
        })
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("ex.zip", io.BytesIO(content), "application/zip")},
        )
        assert r.status_code == 200
        data = r.json()
        assert "Building" in data["examples"]
        assert "Device" in data["examples"]
        assert data["examples"]["Building"]["id"] == "urn:ngsi-ld:Building:001"
        assert data["summary"]["examples"] == 2

    def test_examples_flat_structure(self, client):
        """Estructura examples/Building.json (plana) indexa por nombre de fichero sin extensión."""
        content = make_zip({
            "paquete/schemas/Building.json": SAMPLE_SCHEMA,
            "paquete/examples/Building.json": SAMPLE_EXAMPLE_BUILDING,
        })
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("flat_ex.zip", io.BytesIO(content), "application/zip")},
        )
        assert r.status_code == 200
        data = r.json()
        assert "Building" in data["examples"]

    def test_first_example_wins_for_same_type(self, client):
        """Si hay múltiples ejemplos para el mismo tipo, se guarda solo el primero."""
        content = make_zip({
            "paquete/schemas/Building.json": SAMPLE_SCHEMA,
            "paquete/examples/Building/example1.json": SAMPLE_EXAMPLE_BUILDING,
            "paquete/examples/Building/example2.json": SAMPLE_EXAMPLE_BUILDING_2,
        })
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("dup_ex.zip", io.BytesIO(content), "application/zip")},
        )
        assert r.status_code == 200
        data = r.json()
        assert "Building" in data["examples"]
        # Solo debe haber 1 ejemplo para Building
        assert data["summary"]["examples"] == 1

    def test_multiple_types_each_with_multiple_examples(self, client):
        """Múltiples tipos cada uno con varios ejemplos → un ejemplo por tipo."""
        content = make_zip({
            "paquete/schemas/Building.json": SAMPLE_SCHEMA,
            "paquete/examples/Building/ex1.json": SAMPLE_EXAMPLE_BUILDING,
            "paquete/examples/Building/ex2.json": SAMPLE_EXAMPLE_BUILDING_2,
            "paquete/examples/Device/ex1.json": SAMPLE_EXAMPLE_DEVICE,
        })
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("multi_ex.zip", io.BytesIO(content), "application/zip")},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["summary"]["examples"] == 2


class TestUploadSecurity:

    def test_path_traversal_in_zip_is_ignored(self, client):
        """Entradas con .. en el nombre son ignoradas; el ZIP válido sigue procesándose."""
        content = make_zip({
            "paquete/schemas/Building.json": SAMPLE_SCHEMA,
            "../../../etc/passwd": "root:x:0:0:root:/root:/bin/bash",
        })
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("traversal.zip", io.BytesIO(content), "application/zip")},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["schemas"]) == 1
        unrecognized = data.get("summary", {}).get("unrecognized", [])
        assert not any("etc/passwd" in u for u in unrecognized)

    def test_too_many_files_returns_400(self, client):
        """ZIP con más de MAX_ZIP_MEMBERS (200) ficheros devuelve 400."""
        files = {f"schemas/schema_{i}.json": SAMPLE_SCHEMA for i in range(201)}
        content = make_zip(files)
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("big.zip", io.BytesIO(content), "application/zip")},
        )
        assert r.status_code == 400


class TestUploadErrors:

    def test_empty_zip_returns_422(self, client):
        """ZIP sin ficheros reconocibles devuelve 422."""
        content = make_zip({"random/file.txt": "hello"})
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("empty.zip", io.BytesIO(content), "application/zip")},
        )
        assert r.status_code == 422

    def test_not_a_zip_returns_400(self, client):
        """Archivo que no es ZIP ni TAR devuelve 400."""
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("archivo.txt", io.BytesIO(b"esto no es un zip"), "text/plain")},
        )
        assert r.status_code == 400

    def test_invalid_json_in_schema_is_ignored(self, client):
        """Un fichero .json con JSON inválido en schemas/ se ignora sin romper la carga."""
        content = make_zip({
            "paquete/schemas/valid.json": SAMPLE_SCHEMA,
            "paquete/schemas/broken.json": "{ esto no es json }}}",
        })
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("broken.zip", io.BytesIO(content), "application/zip")},
        )
        assert r.status_code == 200
        data = r.json()
        # Solo debe contener el schema válido
        assert len(data["schemas"]) == 1

    def test_zip_returns_ok_true(self, client):
        """La respuesta de un ZIP válido siempre incluye ok=true."""
        content = make_zip({"paquete/schemas/Building.json": SAMPLE_SCHEMA})
        r = client.post(
            "/api/upload/model-package",
            files={"file": ("ok.zip", io.BytesIO(content), "application/zip")},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
