#!/usr/bin/env python3
"""
Carga las 3 entidades que fallaron con key-values (Building, ManufacturingMachine, Operation)
usando formato NGSI-LD normalizado compatible con Orion-LD 1.10.0

Ejecutar desde: ~/proyectos/proyectos/07INN_DATA_SPACE
  python3 /ruta/a/post_fixed_entities.py
"""
import json
import urllib.request
import urllib.error
from pathlib import Path

BROKER = "http://localhost:1026"
NGSI = f"{BROKER}/ngsi-ld/v1"

# Contexto del proyecto (script vive en data_space/scripts/)
CONTEXT_FILE = Path(__file__).resolve().parent.parent / "context" / "industrial-oven-context.jsonld"

# Entidades corregidas (formato normalizado NGSI-LD)
ENTITIES = [
    {
        "id": "urn:ngsi-ld:Building:edificio-001",
        "type": "Building",
        "name":         {"type": "Property", "value": "Nave de procesado - Planta 1"},
        "category":     {"type": "Property", "value": ["industrial"]},
        "address":      {"type": "Property", "value": {
            "addressLocality": "Madrid",
            "addressCountry": "ES",
            "streetAddress": "Polígono Industrial, Nave 2"
        }},
        "location":     {"type": "GeoProperty", "value": {"type": "Point", "coordinates": [-3.7038, 40.4168]}},
        "dataProvider": {"type": "Property", "value": "https://provider.example.com"},
        "source":       {"type": "Property", "value": "Gestión de instalaciones"},
    },
    {
        "id": "urn:ngsi-ld:ManufacturingMachine:horno-001",
        "type": "ManufacturingMachine",
        "name":         {"type": "Property", "value": "Horno E-Therm Línea 1"},
        "description":  {"type": "Property", "value": "Cámara de ahumado y cocción E-Therm instalada en línea 1."},
        "serialNumber": {"type": "Property", "value": "ET-2024-001"},
        "status":       {"type": "Property", "value": "running"},
        "online":       {"type": "Property", "value": True},
        "power":        {"type": "Property", "value": 45},
        "voltage":      {"type": "Property", "value": 400},
        "machineModel": {"type": "Relationship", "object": "urn:ngsi-ld:ManufacturingMachineModel:e-therm-001"},
        "building":     {"type": "Relationship", "object": "urn:ngsi-ld:Building:edificio-001"},
        "location":     {"type": "GeoProperty", "value": {"type": "Point", "coordinates": [-3.7038, 40.4168]}},
        "address":      {"type": "Property", "value": {
            "addressLocality": "Madrid", "addressCountry": "ES", "streetAddress": "Nave 2, Planta 1"
        }},
        "installedAt":  {"type": "Property", "value": "2024-01-15T00:00:00Z"},
        "supplierName": {"type": "Property", "value": "Emerson Technik"},
        # hasPart está definido en el contexto como "@type":"@id" (Relationship).
        # Orion-LD 1.x no soporta Relationship con valor array directamente.
        # Se almacena como "componentes" (nombre alternativo sin mapeo @id en contexto).
        "componentes": {"type": "Property", "value": [
            "urn:ngsi-ld:Device:tc-001", "urn:ngsi-ld:Device:burner-001",
            "urn:ngsi-ld:Device:fan-circulation-001", "urn:ngsi-ld:Device:fan-extraction-001",
            "urn:ngsi-ld:Device:smoke-generator-001", "urn:ngsi-ld:Device:probe-product-temp",
            "urn:ngsi-ld:Device:probe-room-1", "urn:ngsi-ld:Device:probe-room-2",
            "urn:ngsi-ld:Device:probe-room-3", "urn:ngsi-ld:Device:probe-room-4",
            "urn:ngsi-ld:Device:probe-smoke-generator", "urn:ngsi-ld:Device:probe-humidity",
        ]},
        "dataProvider": {"type": "Property", "value": "https://provider.example.com"},
        "source":       {"type": "Property", "value": "Sistema SCADA línea 1"},
    },
    {
        "id": "urn:ngsi-ld:ManufacturingMachineOperation:op-001",
        "type": "ManufacturingMachineOperation",
        "machine":        {"type": "Relationship", "object": "urn:ngsi-ld:ManufacturingMachine:horno-001"},
        "operationType":  {"type": "Property", "value": ["process"]},
        "status":         {"type": "Property", "value": "finished"},
        "result":         {"type": "Property", "value": "ok"},
        "plannedStartAt": {"type": "Property", "value": "2024-02-10T08:00:00Z"},
        "plannedEndAt":   {"type": "Property", "value": "2024-02-10T14:00:00Z"},
        "startedAt":      {"type": "Property", "value": "2024-02-10T08:05:00Z"},
        "endedAt":        {"type": "Property", "value": "2024-02-10T13:58:00Z"},
        "operator":       {"type": "Relationship", "object": "urn:ngsi-ld:Person:operador-001"},
        "operationOutput":{"type": "Property", "value": {
            "programName": "Programa 15", "programId": "15",
            "temperatureSetPoint": 72, "temperatureMin": 68, "temperatureMax": 75,
            "humiditySetPoint": 65, "humidityMin": 60, "humidityMax": 70,
            "controlMode": "ProductTemperature", "rhControl": True,
            "processSteps": ["smoking", "cooking", "drying"],
            "durationMinutes": 353, "alarms": []
        }},
        "dataProvider":   {"type": "Property", "value": "https://provider.example.com"},
        "source":         {"type": "Property", "value": "Touch-Control TC"},
    },
]


def load_context():
    if CONTEXT_FILE.exists():
        with open(CONTEXT_FILE) as f:
            return json.load(f)["@context"]
    return "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"


def post_entity(entity: dict, context) -> bool:
    payload = {"@context": context, **entity}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{NGSI}/entities",
        data=data,
        headers={"Content-Type": "application/ld+json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"  ✅ Creada: {entity['id']}  (HTTP {resp.status})")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 409:
            print(f"  ⚠️  Ya existe (409): {entity['id']} — actualizando...")
            return patch_entity(entity, context)
        print(f"  ❌ HTTP {e.code}: {body}")
        return False
    except Exception as ex:
        print(f"  ❌ Error: {ex}")
        return False


def patch_entity(entity: dict, context) -> bool:
    """Si ya existe, hace PATCH con los atributos."""
    eid = entity["id"]
    attrs = {k: v for k, v in entity.items() if k not in ("id", "type")}
    payload = {"@context": context, **attrs}
    data = json.dumps(payload).encode("utf-8")
    import urllib.parse
    encoded = urllib.parse.quote(eid, safe="")
    req = urllib.request.Request(
        f"{NGSI}/entities/{encoded}/attrs",
        data=data,
        headers={"Content-Type": "application/ld+json"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"  ✅ Actualizada: {eid}  (HTTP {resp.status})")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  ❌ PATCH HTTP {e.code}: {body}")
        return False


def main():
    print("=" * 55)
    print("  Cargando entidades corregidas → Orion-LD 1.10.0")
    print(f"  Broker: {BROKER}")
    print("=" * 55)

    context = load_context()
    print(f"  Contexto: {'archivo local' if CONTEXT_FILE.exists() else 'core NGSI-LD'}\n")

    ok = sum(post_entity(e, context) for e in ENTITIES)
    print(f"\n{'=' * 55}")
    print(f"  Resultado: {ok}/{len(ENTITIES)} entidades cargadas")
    print("=" * 55)

    if ok == len(ENTITIES):
        print("\n🎉 Listo. Ahora pregunta al agente:")
        print("   '¿qué temperatura hay en el horno?'")
        print("   '¿qué hay en Orion?'")
        print("   'estado del horno'")


if __name__ == "__main__":
    main()