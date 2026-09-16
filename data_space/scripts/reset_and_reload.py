#!/usr/bin/env python3
"""
Limpieza completa y recarga del modelo de datos E-Therm en Orion-LD.
Borra TODAS las entidades existentes y recarga desde los archivos
originales del proyecto usando el contexto correcto.

Ejecutar desde la raíz de data_space:
  python3 scripts/reset_and_reload.py
"""
import json, urllib.request, urllib.error, urllib.parse, sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
BROKER = "http://localhost:1026"
NGSI   = f"{BROKER}/ngsi-ld/v1"

# Contexto original del proyecto
CONTEXT_FILE = _ROOT / "context" / "industrial-oven-context.jsonld"

GREEN, RED, YELLOW, NC = "\033[92m", "\033[91m", "\033[93m", "\033[0m"

# ─── HTTP helper ─────────────────────────────────────────────────────────────

def http(method, path, body=None, params=None):
    url = f"{NGSI}{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    data = json.dumps(body).encode() if body else None
    headers = {"Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/ld+json"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:    return e.code, json.loads(raw)
        except: return e.code, raw
    except Exception as ex:
        return 0, str(ex)

# ─── Cargar contexto ─────────────────────────────────────────────────────────

def load_context():
    if not CONTEXT_FILE.exists():
        print(f"{RED}❌ No se encuentra: {CONTEXT_FILE}{NC}")
        print("   Ejecuta este script desde la carpeta 07INN_DATA_SPACE")
        sys.exit(1)
    with open(CONTEXT_FILE) as f:
        return json.load(f)["@context"]

# ─── Borrar todas las entidades ──────────────────────────────────────────────

def delete_all():
    """Obtiene todos los IDs y los borra uno a uno."""
    print(f"\n{YELLOW}── Paso 1: Borrando todas las entidades ─────────────{NC}")

    # Obtener todos los tipos conocidos (URI larga y nombre corto)
    all_ids = set()

    # Obtener por tipos con URI larga (los que se cargaron con contexto externo)
    uri_types = [
        "https://smartdatamodels.org/dataModel.Device/DeviceMeasurement",
        "https://smartdatamodels.org/dataModel.Device/Device",
        "https://smartdatamodels.org/dataModel.ManufacturingMachine/ManufacturingMachineModel",
        "https://schema.org/Person",
    ]
    # Tipos con nombre corto (los que se cargaron sin contexto)
    short_types = [
        "ManufacturingMachine",
        "ManufacturingMachineOperation",
        "Building",
        "DeviceMeasurement",
        "Device",
        "Person",
        "ManufacturingMachineModel",
        "TemperatureSensor",
        "WorkOrder",
    ]

    for t in uri_types + short_types:
        s, b = http("GET", "/entities", params={"type": t, "limit": 100, "options": "keyValues"})
        if s == 200 and isinstance(b, list):
            for e in b:
                all_ids.add(e["id"])

    # También intentar con local=true para pillar lo que quede
    s, b = http("GET", "/entities", params={"local": "true", "limit": 100, "options": "keyValues"})
    if s == 200 and isinstance(b, list):
        for e in b:
            all_ids.add(e["id"])

    if not all_ids:
        print(f"  {YELLOW}ℹ️  No se encontraron entidades que borrar{NC}")
        return 0

    deleted = 0
    for eid in all_ids:
        enc = urllib.parse.quote(eid, safe="")
        s, _ = http("DELETE", f"/entities/{enc}")
        if s in (204, 404):
            print(f"  🗑️  {eid.split(':')[-1]}")
            deleted += 1
        else:
            print(f"  {RED}❌ No se pudo borrar {eid}: HTTP {s}{NC}")

    print(f"\n  {GREEN}✅ {deleted} entidades eliminadas{NC}")
    return deleted

# ─── Cargar entidad ──────────────────────────────────────────────────────────

def post_entity(filepath: Path, context) -> bool:
    """Carga una entidad desde su archivo JSON original con el contexto del proyecto."""
    try:
        with open(filepath) as f:
            entity = json.load(f)
    except Exception as e:
        print(f"  {RED}❌ Error leyendo {filepath}: {e}{NC}")
        return False

    # Añadir el contexto del proyecto al payload
    payload = {"@context": context, **entity}

    eid = entity.get("id", "?")
    etype = entity.get("type", "?")

    s, b = http("POST", "/entities", body=payload)

    if s == 201:
        print(f"  {GREEN}✅ {eid.split(':')[-1]} ({etype}){NC}")
        return True
    elif s == 409:
        print(f"  {YELLOW}⚠️  Ya existe: {eid.split(':')[-1]} (debería haberse borrado){NC}")
        return False
    else:
        detail = b.get("detail", b) if isinstance(b, dict) else str(b)[:100]
        print(f"  {RED}❌ {eid.split(':')[-1]} → HTTP {s}: {detail}{NC}")
        return False

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  Reset y recarga del modelo E-Therm → Orion-LD")
    print(f"  Broker: {BROKER}")
    print("=" * 55)

    # Verificar broker
    s, b = http("GET".replace("GET", "GET"), "/entities", params={"local": "true", "limit": 1})
    try:
        ver_req = urllib.request.Request(f"{BROKER}/version")
        with urllib.request.urlopen(ver_req, timeout=5) as r:
            ver = json.loads(r.read().decode()).get("orionld version", "?")
            print(f"  Broker: Orion-LD {ver} ✅")
    except:
        print(f"  {RED}❌ Broker no disponible{NC}")
        sys.exit(1)

    context = load_context()
    print(f"  Contexto: {CONTEXT_FILE} ✅")

    # Paso 1: borrar todo
    delete_all()

    # Paso 2: cargar en orden correcto (respetando dependencias)
    print(f"\n{YELLOW}── Paso 2: Cargando entidades originales ────────────{NC}")

    # Orden: independientes primero, luego los que referencian a otros
    load_order = [
        # Catálogo y lugares
        ("examples/ManufacturingMachineModel/example.json", "ManufacturingMachineModel"),
        ("examples/Building/example.json",                  "Building"),
        ("examples/Person/example.json",                    "Person"),
    ]

    # Todos los Device
    device_dir = _ROOT / "examples" / "Device"
    if device_dir.exists():
        for f in sorted(device_dir.glob("*.json")):
            load_order.append((str(f.relative_to(_ROOT)), "Device"))

    # Máquina (referencia modelo + devices)
    load_order.append(("examples/ManufacturingMachine/example.json", "ManufacturingMachine"))

    # Operación
    load_order.append(("examples/ManufacturingMachineOperation/example.json", "ManufacturingMachineOperation"))

    # Mediciones
    meas_dir = _ROOT / "examples" / "DeviceMeasurement"
    if meas_dir.exists():
        for f in sorted(meas_dir.glob("*.json")):
            load_order.append((str(f.relative_to(_ROOT)), "DeviceMeasurement"))

    ok = 0
    fail = 0
    for filepath, label in load_order:
        p = _ROOT / filepath
        if not p.exists():
            print(f"  {YELLOW}⚠️  No encontrado: {filepath}{NC}")
            fail += 1
            continue
        if post_entity(p, context):
            ok += 1
        else:
            fail += 1

    # Paso 3: verificar
    print(f"\n{YELLOW}── Paso 3: Verificación ──────────────────────────────{NC}")
    
    # Con el contexto del proyecto, Orion debería responder a nombres cortos
    # si se envía el header Link correcto. Verificamos con URI larga (siempre funciona).
    checks = [
        ("https://smartdatamodels.org/dataModel.Device/DeviceMeasurement", "DeviceMeasurement"),
        ("https://smartdatamodels.org/dataModel.Device/Device",            "Device"),
        ("https://smartdatamodels.org/dataModel.ManufacturingMachine/ManufacturingMachine", "ManufacturingMachine"),
        ("https://smartdatamodels.org/dataModel.ManufacturingMachine/ManufacturingMachineOperation", "ManufacturingMachineOperation"),
    ]
    for uri_type, label in checks:
        s, b = http("GET", "/entities", params={"type": uri_type, "options": "keyValues", "limit": 20})
        count = len(b) if isinstance(b, list) else 0
        icon = f"{GREEN}✅{NC}" if count > 0 else f"{RED}❌{NC}"
        print(f"  {icon} {label}: {count} entidades")

    print(f"\n{'=' * 55}")
    print(f"  Resultado: {ok} OK  |  {fail} errores")
    print("=" * 55)

    if fail == 0:
        print(f"\n{GREEN}🎉 Modelo cargado correctamente con contexto original.{NC}")
        print("   Reinicia el agente y prueba:")
        print("   '¿qué temperatura hay en el horno?'")
    else:
        print(f"\n{YELLOW}⚠️  Algunos archivos fallaron. Revisa los errores arriba.{NC}")
        print("   Los archivos con 'address' o 'operationOutput' como objeto")
        print("   pueden necesitar el formato normalizado (post_fixed_entities.py).")

if __name__ == "__main__":
    main()
