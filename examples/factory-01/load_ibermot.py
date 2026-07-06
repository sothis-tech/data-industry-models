#!/usr/bin/env python3
"""
load_factory.py — IBERMOT S.A. | Planta Fabricación y Ensamblado Valladolid
============================================================================
Ubicación esperada:
  07_inn_espacio_de_datos/examples/factory-01/load_factory.py

Carga 415 entidades NGSI-LD en Orion-LD representando una planta completa
de fabricación y ensamblado de vehículos eléctricos (SUV IBERMOT Atlante).

El script detecta automáticamente el contexto JSON-LD del proyecto en:
  ../../07INN_DATA_SPACE/context/industrial-oven-context.jsonld
Si no existe, utiliza el contexto NGSI-LD core estándar.

Uso:
  python3 load_ibermot.py
  python3 load_ibermot.py --broker http://localhost:1027 --tenant ibermot
  python3 load_ibermot.py --broker http://orion-ld:1027 --dry-run
  python3 load_ibermot.py --delete        # elimina todas las entidades
  python3 load_ibermot.py --list          # lista los IDs sin cargar
"""

import argparse
from pathlib import Path
import json
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone, timedelta
import random

# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(description="Cargador de fábrica IBERMOT → Orion-LD")
    p.add_argument("--broker",  default="http://localhost:1026", help="URL base del broker Orion-LD")
    p.add_argument("--tenant",  default="",  help="NGSILD-Tenant (vacío = default)")
    p.add_argument("--timeout", type=int, default=15)
    p.add_argument("--delay",   type=float, default=0.05, help="Pausa entre POSTs (segundos)")
    p.add_argument("--dry-run", action="store_true", help="Muestra entidades pero no las envía")
    p.add_argument("--delete",  action="store_true", help="Elimina todas las entidades del loader")
    p.add_argument("--list",    action="store_true", help="Lista todos los IDs que se cargarían")
    return p.parse_args()

ARGS = parse_args()
BROKER  = ARGS.broker.rstrip("/")
NGSI    = f"{BROKER}/ngsi-ld/v1"
# Resolución automática del contexto JSON-LD
# Si existe el contexto del proyecto (07INN_DATA_SPACE/context/), lo usa.
# En caso contrario, emplea el contexto NGSI-LD core estándar.
_SCRIPT_DIR    = Path(__file__).resolve().parent
_PROJECT_CTX   = _SCRIPT_DIR / ".." / ".." / "07INN_DATA_SPACE" / "context" / "ibermot-context.jsonld"
_CORE_CTX_URL  = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"

def _resolve_context():
    ctx_path = _PROJECT_CTX.resolve()
    if ctx_path.exists():
        import json as _json
        try:
            with open(ctx_path, encoding="utf-8") as _f:
                data = _json.load(_f)
                ctx = data.get("@context", data)
                print(f"  📄 Contexto: archivo local ({ctx_path.name})")
                return ctx
        except Exception as _e:
            print(f"  ⚠️  Error cargando contexto local ({_e}). Usando contexto core.")
    else:
        print(f"  📄 Contexto: NGSI-LD core estándar")
    return _CORE_CTX_URL

CONTEXT = _resolve_context()

def _headers():
    h = {"Content-Type": "application/ld+json", "Accept": "application/ld+json"}
    if ARGS.tenant:
        h["NGSILD-Tenant"] = ARGS.tenant
    return h

def _get_headers():
    h = {"Accept": "application/ld+json"}
    if ARGS.tenant:
        h["NGSILD-Tenant"] = ARGS.tenant
    return h

# ══════════════════════════════════════════════════════════════════════════════
# HTTP HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def post_entity(entity: dict) -> bool:
    if ARGS.dry_run:
        print(f"  [DRY] {entity['id']}")
        return True
    payload = {"@context": CONTEXT, **entity}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{NGSI}/entities", data=data, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=ARGS.timeout) as r:
            return r.status in (201, 204)
    except urllib.error.HTTPError as e:
        if e.code == 409:
            return patch_entity(entity)
        body = e.read().decode()
        print(f"  ❌ POST {entity['id']} → HTTP {e.code}: {body[:120]}")
        return False
    except Exception as ex:
        print(f"  ❌ {entity['id']}: {ex}")
        return False

def patch_entity(entity: dict) -> bool:
    eid = entity["id"]
    attrs = {k: v for k, v in entity.items() if k not in ("id", "type")}
    payload = {"@context": CONTEXT, **attrs}
    data = json.dumps(payload).encode()
    enc = urllib.parse.quote(eid, safe="")
    req = urllib.request.Request(f"{NGSI}/entities/{enc}/attrs", data=data, headers=_headers(), method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=ARGS.timeout) as r:
            return r.status in (200, 204)
    except Exception as e:
        print(f"  ❌ PATCH {eid}: {e}")
        return False

def delete_entity(eid: str) -> bool:
    enc = urllib.parse.quote(eid, safe="")
    req = urllib.request.Request(f"{NGSI}/entities/{enc}", headers=_get_headers(), method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=ARGS.timeout) as r:
            return r.status in (200, 204)
    except:
        return False

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS DE CONSTRUCCIÓN DE ENTIDADES
# ══════════════════════════════════════════════════════════════════════════════

def prop(val):    return {"type": "Property",     "value": val}
def rel(urn):     return {"type": "Relationship", "object": urn}
def geo(lon, lat):return {"type": "GeoProperty",  "value": {"type": "Point", "coordinates": [lon, lat]}}
def ts(val, obs=None):
    r = {"type": "Property", "value": val}
    if obs:
        r["observedAt"] = obs
    return r

BASE_LAT, BASE_LON = 41.6523, -4.7245

def jitter(lon, lat, scale=0.0003):
    import random
    return round(lon + random.uniform(-scale, scale), 6), round(lat + random.uniform(-scale, scale), 6)

def now_iso(offset_minutes=0):
    dt = datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

# ══════════════════════════════════════════════════════════════════════════════
# ─── 1. BUILDING ─────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

BUILDING_ID = "urn:ngsi-ld:Building:ibermot-planta-valladolid"

BUILDING = {
    "id": BUILDING_ID,
    "type": "Building",
    "name":        prop("IBERMOT S.A. — Planta de Fabricación y Ensamblado Valladolid"),
    "description": prop("Planta de fabricación y ensamblado del SUV eléctrico IBERMOT Atlante. "
                        "Capacidad: 240 000 vehículos/año. 5 naves de producción + zona de utilidades."),
    "category":    prop(["industrial", "manufacturingPlant"]),
    "address":     prop({
        "streetAddress":    "Polígono Industrial El Cabildo, Parcela 12-A",
        "addressLocality":  "Valladolid",
        "addressRegion":    "Castilla y León",
        "addressCountry":   "ES",
        "postalCode":       "47009"
    }),
    "location":    geo(BASE_LON, BASE_LAT),
    "occupier":    prop(["IBERMOT S.A."]),
    "floorsBelowGround": prop(0),
    "floorsAboveGround": prop(2),
    "openingHours": prop(["Mo-Fr 06:00-22:00", "Sa 06:00-14:00"]),
    "source":       prop("Sistema de Gestión de Activos IBERMOT"),
    "dataProvider": prop("https://data.ibermot.es"),
}

# ══════════════════════════════════════════════════════════════════════════════
# ─── 2. BUILDING SPACES (Naves) ──────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

SPACE_DEFS = [
    ("nave-estampacion",    "Nave 1 — Estampación y Conformado",
     "Prensas transfer y progresivas para estampación de piezas de carrocería. 4 líneas de prensas.",
     BASE_LON - 0.0010, BASE_LAT + 0.0005),
    ("nave-carroceria",     "Nave 2 — Taller de Carrocería (Body Shop)",
     "Soldadura, conformado y ensamblado de la estructura portante del vehículo. 42 robots de soldadura.",
     BASE_LON - 0.0005, BASE_LAT + 0.0003),
    ("nave-pintura",        "Nave 3 — Taller de Pintura (Paint Shop)",
     "Tratamiento superficial: cataforesis, imprimación, color y barniz. Hornos de curado a 180 °C.",
     BASE_LON + 0.0000, BASE_LAT + 0.0000),
    ("nave-motores",        "Nave 4 — Motores y Grupos Motopropulsores (Powertrain)",
     "Ensamblado de motores eléctricos, baterías de alta tensión y transmisiones.",
     BASE_LON + 0.0005, BASE_LAT - 0.0003),
    ("nave-montaje-final",  "Nave 5 — Montaje Final y Verificación (General Assembly)",
     "Ensamblado final del vehículo. 120 puestos de montaje. Pruebas de rodillos y verificación.",
     BASE_LON + 0.0010, BASE_LAT - 0.0005),
    ("zona-utilidades",     "Zona de Servicios Generales y Utilidades",
     "Compresores, generadores, HVAC, depuración de aguas y subestación eléctrica.",
     BASE_LON - 0.0008, BASE_LAT - 0.0008),
    ("zona-calidad",        "Centro de Control de Calidad y Laboratorio Metrológico",
     "Laboratorio de metrología, sala de medición 3D, ensayos no destructivos.",
     BASE_LON + 0.0012, BASE_LAT + 0.0006),
]

SPACES = []
for sid, sname, sdesc, slon, slat in SPACE_DEFS:
    SPACES.append({
        "id":          f"urn:ngsi-ld:BuildingSpace:{sid}",
        "type":        "BuildingSpace",
        "name":        prop(sname),
        "description": prop(sdesc),
        "buildingSpaceType": prop("factory-floor"),
        "isSpaceOf":   rel(BUILDING_ID),
        "location":    geo(slon, slat),
        "source":      prop("Sistema CAD Planta IBERMOT"),
        "dataProvider":prop("https://data.ibermot.es"),
    })

def space_id(s): return f"urn:ngsi-ld:BuildingSpace:{s}"

# ══════════════════════════════════════════════════════════════════════════════
# ─── 3. MACHINE MODELS ───────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

MODEL_DEFS = [
    ("fanuc-r2000ib-210f", "FANUC R-2000iB/210F", "FANUC Corporation",
     "Robot articulado de 6 ejes para soldadura por resistencia y MIG/MAG. Carga máx. 210 kg, alcance 2650 mm.",
     "R-2000iB/210F", "https://www.fanuc.eu/es/es/robots/robot-filter-page/r-2000-series/r-2000ib-210f"),
    ("kuka-kr210-r2700",   "KUKA KR 210 R2700-2", "KUKA Robotics",
     "Robot industrial de alta precisión para ensamblado y manipulación. Carga 210 kg, alcance 2700 mm.",
     "KR 210 R2700-2", "https://www.kuka.com/es-es/productos-servicios/sistemas-de-robots/robot-industrial/kr-quantec"),
    ("abb-irb5500",        "ABB IRB 5500-22", "ABB Robotics",
     "Robot de pintura de 6 ejes con muñeca hueca para aplicación electrostática. Radio de trabajo 3000 mm.",
     "IRB 5500-22", "https://new.abb.com/products/robotics/es/robots-industriales/irb-5500"),
    ("aida-dsf2000",       "AIDA DSF-2000 Transfer", "AIDA Engineering",
     "Prensa transfer servo-mecánica de 2000 toneladas para piezas de carrocería de gran formato.",
     "DSF-2000-6S-4000", "https://www.aida-global.com"),
    ("aida-dsf4000",       "AIDA DSF-4000 Transfer", "AIDA Engineering",
     "Prensa transfer servo-mecánica de 4000 toneladas para piezas estructurales. Automatización completa.",
     "DSF-4000-6S-4000", "https://www.aida-global.com"),
    ("durr-ecotherm",      "Dürr EcoTherm Oven", "Dürr Systems AG",
     "Horno de curado para pintura automotriz. Temperatura operación 180 °C. Longitud cadena 140 m.",
     "EcoTherm-EV-Series", "https://www.durr.com/es/productos/linea-de-pintura/secadores"),
    ("durr-ecopaint",      "Dürr EcoPaint XT Robot", "Dürr Systems AG",
     "Aplicador de pintura electrostático de alta eficiencia. Atomizador rotativo EcoBell3.",
     "EcoPaint XT", "https://www.durr.com/es/productos/tecnologia-de-aplicacion"),
    ("omron-ld250",        "OMRON LD-250 AGV", "OMRON Corporation",
     "Vehículo de guiado autónomo con navegación láser. Carga máx. 250 kg, velocidad 1,8 m/s.",
     "LD-250", "https://www.omron.com/es/es/products/category/robots/mobile-robots/ld-series"),
    ("avl-testbed",        "AVL APA 200/eDrive", "AVL List GmbH",
     "Banco de pruebas para motores eléctricos y de combustión. Par máx. 2000 N·m, 20 000 rpm.",
     "APA-200-E", "https://www.avl.com/testbed"),
    ("hofmann-geodyna",    "Hofmann geodyna 9900", "Snap-on Equipment",
     "Equilibradora de ruedas para neumáticos de coche y furgoneta. Velocidad 200 rpm, diámetro máx. 1050 mm.",
     "geodyna 9900", "https://www.hofmann-megaplan.de"),
    ("atlas-copco-ga110",  "Atlas Copco GA 110 VSD+", "Atlas Copco",
     "Compresor de tornillo rotativo de velocidad variable. Presión 7,5 bar, caudal 18,6 m³/min.",
     "GA 110 VSD+", "https://www.atlascopco.com/es-es/compressors"),
    ("cummins-c1500d5",    "Cummins C1500D5 Genset", "Cummins Inc.",
     "Grupo electrógeno de emergencia diésel. Potencia continua 1500 kVA, tensión 400 V / 50 Hz.",
     "C1500D5-F5", "https://www.cummins.com/generators"),
]

MODELS = []
for mid, mname, brand, mdesc, model_num, url in MODEL_DEFS:
    MODELS.append({
        "id":            f"urn:ngsi-ld:ManufacturingMachineModel:{mid}",
        "type":          "ManufacturingMachineModel",
        "name":          prop(mname),
        "description":   prop(mdesc),
        "brandName":     prop(brand),
        "modelName":     prop(model_num),
        "manufacturerName": prop(brand),
        "documentation": prop(url),
        "source":        prop("Catálogo técnico de proveedores"),
        "dataProvider":  prop("https://data.ibermot.es"),
    })

def model_id(m): return f"urn:ngsi-ld:ManufacturingMachineModel:{m}"

# ══════════════════════════════════════════════════════════════════════════════
# ─── 4. PERSONAS ─────────────────────────────────────────════════════════════
# ══════════════════════════════════════════════════════════════════════════════

PERSON_DEFS = [
    ("director-planta",       "Alejandro Fuentes García",   "Director de Planta",            "+34 983 210 001"),
    ("jefe-produccion",       "María Soledad Ortega Vega",  "Jefa de Producción",             "+34 983 210 010"),
    ("jefe-calidad",          "Roberto Salinas Pérez",      "Jefe de Calidad y Homologación", "+34 983 210 020"),
    ("jefe-mantenimiento",    "Carmen Blanco Nieto",        "Jefa de Mantenimiento",          "+34 983 210 030"),
    ("responsable-seguridad", "Fernando Lara Díaz",         "Responsable de PRL y Seguridad", "+34 983 210 040"),
    ("supervisor-carroceria", "Iván Morales Torres",        "Supervisor Nave Carrocería",     "+34 983 210 011"),
    ("supervisor-pintura",    "Ana Guerrero Luna",          "Supervisora Nave Pintura",       "+34 983 210 012"),
    ("supervisor-montaje",    "Javier Crespo Varela",       "Supervisor Montaje Final",       "+34 983 210 013"),
    ("tecnico-mant-001",      "Diego Serrano Alonso",       "Técnico de Mantenimiento",       "+34 983 210 031"),
    ("tecnico-mant-002",      "Laura Pinto Rubio",          "Técnica de Mantenimiento",       "+34 983 210 032"),
    ("operario-carroceria-001","Pablo Fuentes Méndez",      "Operario Carrocería Turno A",    "+34 983 210 050"),
    ("operario-pintura-001",  "Cristina Vega Aguado",       "Operaria Pintura Turno A",       "+34 983 210 051"),
    ("operario-motores-001",  "Sergio Naranjo Gil",         "Operario Motores Turno A",       "+34 983 210 052"),
    ("operario-montaje-001",  "Miriam Santos Prieto",       "Operaria Montaje Final Turno A", "+34 983 210 053"),
]

# Mapa persona → espacios donde trabaja (para las relaciones del grafo)
_PERSON_SPACES = {
    "director-planta":        [],                                          # toda la planta
    "jefe-produccion":        ["nave-estampacion","nave-carroceria",
                               "nave-motores","nave-montaje-final"],
    "jefe-calidad":           ["zona-calidad","nave-montaje-final"],
    "jefe-mantenimiento":     ["nave-carroceria","nave-pintura",
                               "zona-utilidades"],
    "responsable-seguridad":  ["nave-carroceria","nave-estampacion",
                               "nave-pintura","nave-motores",
                               "nave-montaje-final"],
    "supervisor-carroceria":  ["nave-carroceria"],
    "supervisor-pintura":     ["nave-pintura"],
    "supervisor-montaje":     ["nave-montaje-final"],
    "tecnico-mant-001":       ["nave-carroceria","nave-motores"],
    "tecnico-mant-002":       ["nave-pintura","nave-montaje-final"],
    "operario-carroceria-001":["nave-carroceria"],
    "operario-pintura-001":   ["nave-pintura"],
    "operario-motores-001":   ["nave-motores"],
    "operario-montaje-001":   ["nave-montaje-final"],
}

PERSONS = []
for pid, pname, role, phone in PERSON_DEFS:
    spaces = _PERSON_SPACES.get(pid, [])
    entity = {
        "id":          f"urn:ngsi-ld:Person:{pid}",
        "type":        "Person",
        "name":        prop(pname),
        "jobTitle":    prop(role),
        "telephone":   prop(phone),
        "worksFor":    prop("IBERMOT S.A."),
        "worksAt":     rel(BUILDING_ID),
        "source":      prop("RRHH IBERMOT S.A."),
        "dataProvider":prop("https://data.ibermot.es"),
    }
    if len(spaces) == 1:
        entity["locatedIn"] = rel(space_id(spaces[0]))
    elif len(spaces) > 1:
        entity["locatedIn"]     = rel(space_id(spaces[0]))
        entity["worksInSpaces"] = prop([space_id(s) for s in spaces])
    PERSONS.append(entity)

# ══════════════════════════════════════════════════════════════════════════════
# ─── 5. MÁQUINAS Y DISPOSITIVOS ─────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

# Cada máquina declara sus sensores/actuadores con:
#   suffix, name, controlledProperty, unitCode, unitText, value, value_min, value_max
# value = valor actual realista para la demo

MACHINE_CATALOG = [

    # ── NAVE ESTAMPACIÓN ──────────────────────────────────────────────────────
    {
        "id": "prensa-001", "model": "aida-dsf4000", "space": "nave-estampacion",
        "name": "Prensa Transfer AIDA DSF-4000 — Línea Lateral",
        "desc": "Prensa transfer servo-mecánica 4000 T para estampación de paneles laterales y techos.",
        "serial": "AIDA-DSF4K-2022-001", "status": "running", "power": 1200, "voltage": 400,
        "supplier": "AIDA Engineering Ltd.", "installed": "2022-03-10T00:00:00Z",
        "devices": [
            ("fuerza",         "Sensor Fuerza de Estampación",    "force",           "KN",  "kN",       3842, 1000, 4000),
            ("presion-hid",    "Presión Sistema Hidráulico",      "pressure",        "BAR", "bar",       198,  150,  220),
            ("temp-aceite",    "Temperatura Aceite Hidráulico",   "temperature",     "CEL", "°C",         47,   35,   65),
            ("vibracion",      "Vibración Estructura Prensa",     "vibration",       "G",   "g",          1.2,  0.1,   5),
            ("contador-golpes","Contador de Golpes",              "cycleCount",      "C62", "golpes",  184205,    0, 9999999),
            ("velocidad-ram",  "Velocidad Carrera de RAM",        "velocity",        "MPS", "mm/s",       320,  100,   500),
        ]
    },
    {
        "id": "prensa-002", "model": "aida-dsf2000", "space": "nave-estampacion",
        "name": "Prensa Progresiva AIDA DSF-2000 — Piezas Pequeñas",
        "desc": "Prensa progresiva 2000 T para bisagras, refuerzos, piezas de suspensión.",
        "serial": "AIDA-DSF2K-2021-003", "status": "running", "power": 650, "voltage": 400,
        "supplier": "AIDA Engineering Ltd.", "installed": "2021-09-15T00:00:00Z",
        "devices": [
            ("fuerza",         "Sensor Fuerza de Estampación",    "force",       "KN",  "kN",       1765, 500, 2000),
            ("presion-hid",    "Presión Sistema Hidráulico",      "pressure",    "BAR", "bar",        185, 140,  210),
            ("temp-aceite",    "Temperatura Aceite Hidráulico",   "temperature", "CEL", "°C",          43,  35,   65),
            ("vibracion",      "Vibración Estructura",            "vibration",   "G",   "g",           0.9,  0.1,  4),
            ("contador-golpes","Contador de Golpes",              "cycleCount",  "C62", "golpes",  271803,   0, 9999999),
        ]
    },

    # ── NAVE CARROCERÍA — 6 robots soldadura ──────────────────────────────────
    *[{
        "id": f"robot-soldadura-00{i}", "model": "fanuc-r2000ib-210f",
        "space": "nave-carroceria",
        "name": f"Robot Soldadura FANUC R-2000iB — Estación {i}",
        "desc": f"Robot de 6 ejes para soldadura MIG/MAG y por resistencia. Estación de carrocería {i}, sub-línea {'lateral' if i<=3 else 'estructura'}.",
        "serial": f"FANUC-R2K-2023-{i:03d}", "status": "running", "power": 18, "voltage": 400,
        "supplier": "FANUC Iberia S.L.", "installed": f"2023-{i:02d}-15T00:00:00Z",
        "devices": [
            ("corriente",      f"Corriente Motor Principal Est.{i}",  "electricCurrent", "AMP", "A",      18.4 + i*0.3, 0, 30),
            ("temp-motor",     f"Temperatura Motor Eje J1 Est.{i}",   "temperature",     "CEL", "°C",     62 + i*1.5,  20, 100),
            ("fuerza-sold",    f"Fuerza Electrodo Soldadura Est.{i}", "force",           "NEW", "N",      3850 - i*50, 2000, 5000),
            ("contador-sold",  f"Contador Soldaduras Est.{i}",        "cycleCount",      "C62", "soldaduras", 12400 + i*1000, 0, 9999999),
            ("humo-sold",      f"Sensor Humos Soldadura Est.{i}",     "smokeConcentration","PPM","ppm",    42 + i*2, 0, 200),
        ]
    } for i in range(1, 7)],

    {
        "id": "robot-sellado-001", "model": "kuka-kr210-r2700", "space": "nave-carroceria",
        "name": "Robot Sellado Carrocería KUKA KR210 — Masillas y Adhesivos",
        "desc": "Aplicación de masillas estructurales, adhesivos y sellantes antiruido en uniones de carrocería.",
        "serial": "KUKA-KR210-2023-007", "status": "running", "power": 14, "voltage": 400,
        "supplier": "KUKA Robotics Iberia S.A.", "installed": "2023-04-20T00:00:00Z",
        "devices": [
            ("presion-adh",   "Presión Sistema Adhesivo",          "pressure",    "BAR", "bar",      72.5, 40, 100),
            ("caudal-adh",    "Caudal de Adhesivo Aplicado",       "flow",        "MLM", "ml/min",  185.0, 50, 300),
            ("temp-adh",      "Temperatura Material Adhesivo",     "temperature", "CEL", "°C",       28.5, 15,  40),
            ("contador-ciclos","Ciclos Completados",               "cycleCount",  "C62", "ciclos",  89340,  0, 9999999),
        ]
    },

    *[{
        "id": f"agv-carroceria-00{i}", "model": "omron-ld250", "space": "nave-carroceria",
        "name": f"AGV OMRON LD-250 — Carrocería #{i}",
        "desc": f"Vehículo de guiado autónomo para transporte de carrocerías entre estaciones. Ruta {'A-B-C' if i==1 else 'C-D-E'}.",
        "serial": f"OMRON-LD250-2023-{10+i:03d}", "status": "running", "power": 2.4, "voltage": 48,
        "supplier": "OMRON Electronics Iberia S.A.", "installed": "2023-06-01T00:00:00Z",
        "devices": [
            ("bateria",        f"Nivel Batería AGV-CAR-{i:02d}",   "batteryLevel",  "P1",  "%",       78 - i*12, 0, 100),
            ("velocidad",      f"Velocidad AGV-CAR-{i:02d}",       "velocity",      "MPS", "m/s",      1.4 + i*0.1, 0, 1.8),
            ("carga",          f"Peso Carga AGV-CAR-{i:02d}",      "weight",        "KGM", "kg",       128 + i*15, 0, 250),
        ]
    } for i in range(1, 3)],

    # ── NAVE PINTURA ──────────────────────────────────────────────────────────
    {
        "id": "cabina-electroforesis-001", "model": "durr-ecopaint", "space": "nave-pintura",
        "name": "Dürr EcoPaint — Cataforesis (KTL) Línea Principal",
        "desc": "Baño de cataforesis catódica para imprimación anticorrosión de toda la carrocería. Volumen baño 280 m³.",
        "serial": "DURR-ECOP-2020-KTL01", "status": "running", "power": 380, "voltage": 400,
        "supplier": "Dürr Systems AG", "installed": "2020-11-01T00:00:00Z",
        "devices": [
            ("temp-bano",     "Temperatura del Baño KTL",          "temperature",   "CEL", "°C",      30.2, 28, 35),
            ("ph-bano",       "pH del Baño KTL",                   "pH",            "Q35", "pH",       5.8, 5.5, 6.2),
            ("conductividad", "Conductividad del Baño",            "conductivity",  "MSM", "mS/cm",   1050, 900, 1200),
            ("tension-ktl",   "Tensión Electroforesis",            "voltage",       "VLT", "V",        330, 300, 360),
            ("corriente-ktl", "Corriente Total Electroforesis",    "electricCurrent","AMP","A",        215, 150, 300),
            ("nivel-bano",    "Nivel de Baño KTL",                 "fillingLevel",  "P1",  "%",        87,  75, 100),
        ]
    },

    *[{
        "id": f"robot-pintura-00{i}", "model": "abb-irb5500", "space": "nave-pintura",
        "name": f"Robot Pintura ABB IRB 5500 — Estación {['Imprimación','Color A','Color B','Barniz'][i-1]}",
        "desc": f"Aplicación electrostática con atomizador rotativo EcoBell3. Zona de {'imprimación' if i==1 else 'acabado exterior'}.",
        "serial": f"ABB-IRB5500-2021-{i:03d}", "status": "running", "power": 8.5, "voltage": 400,
        "supplier": "ABB Asea Brown Boveri S.A.", "installed": "2021-05-10T00:00:00Z",
        "devices": [
            ("caudal-pintura", f"Caudal Pintura Robot P-{i:02d}",  "flow",          "MLM", "ml/min",  215 + i*10, 50, 400),
            ("presion-atom",   f"Presión Atomización P-{i:02d}",   "pressure",      "BAR", "bar",       1.8 + i*0.1, 0.5, 3),
            ("temp-pintura",   f"Temperatura Pintura P-{i:02d}",   "temperature",   "CEL", "°C",       23.5 + i*0.5, 18, 35),
            ("eficiencia-transf",f"Eficiencia Transferencia P-{i:02d}","efficiency", "P1",  "%",       88 - i*2, 70, 99),
        ]
    } for i in range(1, 5)],

    *[{
        "id": f"horno-curado-00{i}", "model": "durr-ecotherm", "space": "nave-pintura",
        "name": f"Dürr EcoTherm — Horno Curado {'Imprimación' if i==1 else 'Acabado'} #{i}",
        "desc": f"Horno de curado a 180 °C. Cadena transportadora {'imprimación' if i==1 else 'barniz/color'}. Longitud 140 m.",
        "serial": f"DURR-ECOTH-2020-{i:03d}", "status": "running", "power": 1800, "voltage": 400,
        "supplier": "Dürr Systems AG", "installed": "2020-11-15T00:00:00Z",
        "devices": [
            ("temp-z1",   f"Temperatura Zona 1 Horno H{i:02d}",   "temperature",   "CEL", "°C",      175, 160, 195),
            ("temp-z2",   f"Temperatura Zona 2 Horno H{i:02d}",   "temperature",   "CEL", "°C",      182, 160, 195),
            ("temp-z3",   f"Temperatura Zona 3 Horno H{i:02d}",   "temperature",   "CEL", "°C",      180, 160, 195),
            ("temp-z4",   f"Temperatura Zona 4 Enfriamiento H{i:02d}","temperature","CEL", "°C",      45,  20,  80),
            ("velocidad-cadena",f"Velocidad Cadena Horno H{i:02d}","velocity",      "MMS", "m/min",    4.2, 2,   8),
            ("consumo-gas", f"Consumo Gas Natural Horno H{i:02d}", "flow",          "M3M", "m³/h",   248,  100, 400),
        ]
    } for i in range(1, 3)],

    # ── NAVE MOTORES ──────────────────────────────────────────────────────────
    *[{
        "id": f"robot-montaje-motor-00{i}", "model": "kuka-kr210-r2700", "space": "nave-motores",
        "name": f"KUKA KR210 — Ensamblado Motor {'Eléctrico' if i==1 else 'y Transmisión'}",
        "desc": f"Manipulación y ensamblado de {'rotores y estatores' if i==1 else 'transmisiones y ejes'} del grupo motopropulsor.",
        "serial": f"KUKA-KR210-2022-{20+i:03d}", "status": "running", "power": 14, "voltage": 400,
        "supplier": "KUKA Robotics Iberia S.A.", "installed": "2022-06-20T00:00:00Z",
        "devices": [
            ("par-apriete",   f"Par de Apriete Robot M{i:02d}",    "torque",        "N.M", "N·m",     85 + i*5, 10, 200),
            ("posicion-eje",  f"Posición Eje Principal M{i:02d}",  "position",      "MMT", "mm",       0.04 + i*0.01, 0, 500),
            ("fuerza-ins",    f"Fuerza de Inserción M{i:02d}",     "force",         "NEW", "N",       1250 + i*100, 0, 3000),
            ("contador-ciclos",f"Ciclos de Montaje M{i:02d}",      "cycleCount",    "C62", "ciclos",  3420 + i*300, 0, 9999999),
        ]
    } for i in range(1, 3)],

    *[{
        "id": f"banco-pruebas-motor-00{i}", "model": "avl-testbed", "space": "nave-motores",
        "name": f"AVL APA 200/eDrive — Banco Pruebas Motor #{i}",
        "desc": f"Banco de ensayos para motores eléctricos de propulsión. Verificación de par, potencia y eficiencia.",
        "serial": f"AVL-APA200E-2022-{30+i:03d}", "status": "running", "power": 250, "voltage": 400,
        "supplier": "AVL List GmbH", "installed": "2022-08-01T00:00:00Z",
        "devices": [
            ("rpm",          f"Velocidad Motor Banco BM{i:02d}",   "rotationalSpeed","RPM", "rpm",     6420 + i*150, 0, 20000),
            ("par-motor",    f"Par Motor Banco BM{i:02d}",         "torque",        "N.M", "N·m",      315 + i*10, 0, 2000),
            ("temp-devanado", f"Temperatura Devanados BM{i:02d}",  "temperature",   "CEL", "°C",       78 + i*3, 20, 150),
            ("eficiencia",   f"Eficiencia Eléctrica BM{i:02d}",    "efficiency",    "P1",  "%",        94.2 + i*0.3, 80, 99),
            ("potencia-salida",f"Potencia Salida BM{i:02d}",       "power",         "KWT", "kW",       183 + i*5, 0, 300),
            ("vibracion",    f"Vibración Bancada BM{i:02d}",       "vibration",     "MMT", "mm/s",     1.8 + i*0.3, 0, 10),
            ("corriente-fase",f"Corriente de Fase BM{i:02d}",      "electricCurrent","AMP","A",        142 + i*8, 0, 300),
        ]
    } for i in range(1, 3)],

    {
        "id": "agv-motores-001", "model": "omron-ld250", "space": "nave-motores",
        "name": "AGV OMRON LD-250 — Motores #1",
        "desc": "Transporte autónomo de grupos motopropulsores entre banco de pruebas y línea de montaje.",
        "serial": "OMRON-LD250-2022-030", "status": "running", "power": 2.4, "voltage": 48,
        "supplier": "OMRON Electronics Iberia S.A.", "installed": "2022-07-15T00:00:00Z",
        "devices": [
            ("bateria",   "Nivel Batería AGV-MOT-01",   "batteryLevel",  "P1",  "%",      65, 0, 100),
            ("velocidad", "Velocidad AGV-MOT-01",       "velocity",      "MPS", "m/s",   1.2, 0, 1.8),
            ("carga",     "Peso Carga AGV-MOT-01",      "weight",        "KGM", "kg",    225, 0, 250),
        ]
    },

    # ── NAVE MONTAJE FINAL ────────────────────────────────────────────────────
    *[{
        "id": f"robot-montaje-final-00{i}", "model": "kuka-kr210-r2700",
        "space": "nave-montaje-final",
        "name": f"KUKA KR210 — Montaje Final Est. {['Puertas A','Puertas B','Tablero Instrumentos','Parachoques'][i-1]}",
        "desc": f"Ensamblado y apriete controlado de {'puertas' if i<=2 else 'elementos interiores y exteriores'} del vehículo.",
        "serial": f"KUKA-KR210-2023-{40+i:03d}", "status": "running", "power": 14, "voltage": 400,
        "supplier": "KUKA Robotics Iberia S.A.", "installed": "2023-01-10T00:00:00Z",
        "devices": [
            ("par-apriete",  f"Par Apriete Robot MF{i:02d}",    "torque",       "N.M", "N·m",    22 + i*3, 5, 80),
            ("posicion",     f"Posición Eje Z Robot MF{i:02d}", "position",     "MMT", "mm",      0.08 + i*0.01, 0, 500),
            ("fuerza",       f"Fuerza Inserción Robot MF{i:02d}","force",       "NEW", "N",      850 + i*50, 0, 2000),
            ("ciclos",       f"Ciclos Completados MF{i:02d}",   "cycleCount",   "C62", "ciclos", 4820 + i*400, 0, 9999999),
        ]
    } for i in range(1, 5)],

    *[{
        "id": f"agv-montaje-00{i}", "model": "omron-ld250", "space": "nave-montaje-final",
        "name": f"AGV OMRON LD-250 — Montaje Final #{i}",
        "desc": f"Transporte de carrocerías y subconjuntos entre puestos de la línea de montaje final. Ruta {i}.",
        "serial": f"OMRON-LD250-2023-{50+i:03d}", "status": "running" if i != 3 else "maintenance", "power": 2.4, "voltage": 48,
        "supplier": "OMRON Electronics Iberia S.A.", "installed": "2023-02-20T00:00:00Z",
        "devices": [
            ("bateria",   f"Nivel Batería AGV-MF-{i:02d}",  "batteryLevel",  "P1",  "%",      88 - i*10, 0, 100),
            ("velocidad", f"Velocidad AGV-MF-{i:02d}",      "velocity",      "MPS", "m/s",    1.6 - i*0.1, 0, 1.8),
            ("carga",     f"Peso Carga AGV-MF-{i:02d}",     "weight",        "KGM", "kg",     145 + i*20, 0, 250),
        ]
    } for i in range(1, 4)],

    {
        "id": "equilibrado-ruedas-001", "model": "hofmann-geodyna", "space": "nave-montaje-final",
        "name": "Hofmann geodyna 9900 — Equilibradora de Ruedas",
        "desc": "Control de equilibrado dinámico de ruedas. Integrada en línea de montaje final.",
        "serial": "HOFM-GD9900-2022-001", "status": "running", "power": 3.5, "voltage": 230,
        "supplier": "Snap-on Equipment Europe", "installed": "2022-03-01T00:00:00Z",
        "devices": [
            ("desequilibrio-est", "Desequilibrio Estático",      "vibration",     "GRM", "g",         6.4, 0, 50),
            ("desequilibrio-din", "Desequilibrio Dinámico",      "vibration",     "GRM", "g",         8.1, 0, 50),
            ("velocidad-rot",     "Velocidad Rotación Test",     "rotationalSpeed","RPM","rpm",       200, 0, 300),
            ("temp-rodamiento",   "Temperatura Rodamiento",      "temperature",   "CEL", "°C",        32, 15, 60),
            ("ruedas-ok",         "Ruedas OK Hoy",               "cycleCount",    "C62", "ruedas",   1842, 0, 9999999),
        ]
    },

    {
        "id": "banco-final-001", "model": "avl-testbed", "space": "nave-montaje-final",
        "name": "MAHA LPS 3000 — Banco de Pruebas Final Rodillos",
        "desc": "Verificación final del vehículo: frenos, alineación, emisiones y consumo. Prueba tipo-aprobación CE.",
        "serial": "MAHA-LPS3000-2021-001", "status": "running", "power": 90, "voltage": 400,
        "supplier": "MAHA Maschinenbau Haldenwang GmbH", "installed": "2021-10-05T00:00:00Z",
        "devices": [
            ("vel-max",       "Velocidad Máxima Alcanzada",      "velocity",      "KMH", "km/h",     183, 0, 300),
            ("efic-freno-ax1","Eficacia Frenos Eje Delantero",   "efficiency",    "P1",  "%",         94.5, 0, 100),
            ("efic-freno-ax2","Eficacia Frenos Eje Trasero",     "efficiency",    "P1",  "%",         93.2, 0, 100),
            ("emision-nox",   "Emisión NOx",                     "concentration", "PPM", "ppm",        2.4, 0, 50),
            ("consumo-kwh",   "Consumo Energético",              "power",         "KWT", "kWh/100km", 18.2, 0, 40),
        ]
    },

    # ── ZONA UTILIDADES ────────────────────────────────────────────────────────
    *[{
        "id": f"compresor-00{i}", "model": "atlas-copco-ga110", "space": "zona-utilidades",
        "name": f"Atlas Copco GA 110 VSD+ — Compresor {'Principal' if i==1 else 'Respaldo'}",
        "desc": f"Compresor tornillo rotativo velocidad variable. Alimenta red de aire comprimido de {'toda la planta' if i==1 else 'naves carrocería y pintura (backup)'}.",
        "serial": f"ATLCO-GA110VSD-2021-{i:03d}", "status": "running" if i==1 else "standby", "power": 110, "voltage": 400,
        "supplier": "Atlas Copco Compressors S.A.U.", "installed": "2021-05-20T00:00:00Z",
        "devices": [
            ("presion-salida", f"Presión Red Comprimido COM{i:02d}","pressure",     "BAR", "bar",      7.2 + i*0.1, 6.5, 8),
            ("temp-aire",      f"Temperatura Aire Comprimido COM{i:02d}","temperature","CEL","°C",     38 + i*2, 20, 70),
            ("caudal",         f"Caudal Producido COM{i:02d}",      "flow",          "M3M", "m³/min",  14.8 + i*0.5, 0, 18.6),
            ("horas",          f"Horas de Operación COM{i:02d}",    "time",          "HUR", "h",       18420 + i*1000, 0, 9999999),
            ("nivel-aceite",   f"Nivel Aceite Compresor COM{i:02d}","fillingLevel",  "P1",  "%",       82 - i*10, 20, 100),
        ]
    } for i in range(1, 3)],

    {
        "id": "generador-001", "model": "cummins-c1500d5", "space": "zona-utilidades",
        "name": "Cummins C1500D5 — Grupo Electrógeno Emergencia",
        "desc": "Generador diésel de emergencia 1500 kVA para suministro crítico en corte de red. Tiempo arranque < 10 s.",
        "serial": "CUMM-C1500D5-2019-001", "status": "standby", "power": 1200, "voltage": 400,
        "supplier": "Cummins Distribuidora Ibérica S.L.", "installed": "2019-06-10T00:00:00Z",
        "devices": [
            ("nivel-comb",  "Nivel Combustible Diésel",    "fillingLevel",  "P1",  "%",       68, 0, 100),
            ("potencia",    "Potencia Generada",           "power",         "KWT", "kW",       0, 0, 1200),
            ("temp-motor",  "Temperatura Motor Generador", "temperature",   "CEL", "°C",       32, 15, 110),
            ("horas",       "Horas Totales de Marcha",     "time",          "HUR", "h",       2140, 0, 99999),
            ("tension-sal", "Tensión de Salida",           "voltage",       "VLT", "V",       400, 0, 420),
        ]
    },

    {
        "id": "hvac-pintura-001", "model": "atlas-copco-ga110", "space": "nave-pintura",
        "name": "Carrier AquaForce 8500 — HVAC Nave Pintura",
        "desc": "Sistema HVAC con control preciso de temperatura y humedad para cabinas de pintura. Caudal 85 000 m³/h.",
        "serial": "CARR-AF8500-2020-001", "status": "running", "power": 320, "voltage": 400,
        "supplier": "Carrier Refrigeración España S.A.", "installed": "2020-08-01T00:00:00Z",
        "devices": [
            ("temp-nave",   "Temperatura Nave Pintura",    "temperature",   "CEL", "°C",       21.5, 18, 28),
            ("humedad",     "Humedad Relativa Nave Pintura","humidity",      "P1",  "%",        52.0, 40, 65),
            ("caudal-imp",  "Caudal de Impulsión",         "flow",          "M3H", "m³/h",  82400, 40000, 85000),
            ("co2-nave",    "CO2 Ambiental Nave Pintura",  "concentration", "PPM", "ppm",      582, 300, 1000),
            ("consumo-ene", "Consumo Energético HVAC",     "power",         "KWT", "kW",       248, 0, 400),
        ]
    },
]

# ══════════════════════════════════════════════════════════════════════════════
# ─── GENERAR ENTIDADES MÁQUINAS + DISPOSITIVOS + MEDICIONES ─────────────────
# ══════════════════════════════════════════════════════════════════════════════

MACHINES    = []
DEVICES     = []
MEASUREMENTS = []

for spec in MACHINE_CATALOG:
    mid   = spec["id"]
    space = space_id(spec["space"])
    lon, lat = jitter(BASE_LON, BASE_LAT)

    device_urns = [f"urn:ngsi-ld:Device:{mid}-{d[0]}" for d in spec["devices"]]

    machine = {
        "id":           f"urn:ngsi-ld:ManufacturingMachine:{mid}",
        "type":         "ManufacturingMachine",
        "name":         prop(spec["name"]),
        "description":  prop(spec["desc"]),
        "serialNumber": prop(spec["serial"]),
        "status":       prop(spec["status"]),
        "online":       prop(spec["status"] != "maintenance"),
        "power":        prop(spec["power"]),
        "voltage":      prop(spec["voltage"]),
        "machineModel": rel(model_id(spec["model"])),
        "building":     rel(BUILDING_ID),
        "locatedIn":    rel(space),
        "location":     geo(lon, lat),
        "installedAt":  prop(spec["installed"]),
        "supplierName": prop(spec["supplier"]),
        "componentes":  prop(device_urns),
        "source":       prop("SCADA IBERMOT — OPC-UA Bridge"),
        "dataProvider": prop("https://data.ibermot.es"),
    }
    MACHINES.append(machine)

    for d in spec["devices"]:
        suffix, dname, dprop, dunit, dunit_text, dval, vmin, vmax = d
        did = f"urn:ngsi-ld:Device:{mid}-{suffix}"
        dlon, dlat = jitter(lon, lat, 0.00005)

        device = {
            "id":           did,
            "type":         "Device",
            "name":         prop(dname),
            "description":  prop(f"Sensor/actuador '{dname}' perteneciente a {spec['name']}."),
            "controlledAsset": rel(f"urn:ngsi-ld:ManufacturingMachine:{mid}"),
            "controlledProperty": prop([dprop]),
            "deviceCategory":    prop(["sensor"]),
            "status":            prop("ok" if spec["status"] != "maintenance" else "maintenance"),
            "online":            prop(spec["status"] != "maintenance"),
            "unitCode":          prop(dunit),
            "unitText":          prop(dunit_text),
            "measurementType":   prop(["instantaneous"]),
            "location":          geo(dlon, dlat),
            "source":            prop("SCADA IBERMOT — MQTT Bridge"),
            "dataProvider":      prop("https://data.ibermot.es"),
        }
        DEVICES.append(device)

        meas_id = f"urn:ngsi-ld:DeviceMeasurement:{mid}-{suffix}-meas"
        measurement = {
            "id":                meas_id,
            "type":              "DeviceMeasurement",
            "device":            rel(did),
            "controlledProperty":prop(dprop),
            "numValue":          ts(dval, now_iso(random.randint(0, 10))),
            "measurementType":   prop("instantaneous"),
            "unitCode":          prop(dunit),
            "unitText":          prop(dunit_text),
            "minValue":          prop(vmin),
            "maxValue":          prop(vmax),
            "accuracy":          prop(0.5),
            "dateObserved":      prop(now_iso(random.randint(0, 10))),
            "location":          geo(dlon, dlat),
            "source":            prop("SCADA IBERMOT — MQTT Bridge"),
            "dataProvider":      prop("https://data.ibermot.es"),
        }
        MEASUREMENTS.append(measurement)

# ══════════════════════════════════════════════════════════════════════════════
# ─── 6. OPERACIONES ──────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

OP_DEFS = [
    ("op-estampacion-turno-a-001", "prensa-001", "operario-carroceria-001",
     "Estampación Paneles Laterales — Turno A", "running",
     {"programId": "EST-LAT-07", "productRef": "ATL-2024-PANEL-LAT-IZQ",
      "piezasTurno": 324, "cadencia": 12, "alertas": []}),
    ("op-estampacion-turno-a-002", "prensa-002", "operario-carroceria-001",
     "Estampación Piezas Estructurales — Turno A", "running",
     {"programId": "EST-EST-03", "productRef": "ATL-2024-REFUERZO-B",
      "piezasTurno": 518, "cadencia": 18, "alertas": []}),
    ("op-soldadura-carroceria-001", "robot-soldadura-001", "supervisor-carroceria",
     "Soldadura Lateral Izquierdo — Carrocería ATL-2024-09841", "running",
     {"programId": "SOL-LAT-IZQ-v4.2", "jig": "JIG-LAT-IZQ-3",
      "soldadurasOK": 248, "soldadurasNOK": 0, "alertas": []}),
    ("op-soldadura-carroceria-002", "robot-soldadura-003", "supervisor-carroceria",
     "Soldadura Piso y Túnel Central — Carrocería ATL-2024-09841", "finished",
     {"programId": "SOL-PISO-v3.1", "soldadurasOK": 186, "soldadurasNOK": 2,
      "alertas": ["Revisión junta SF-047 fuera de tolerancia — corregido"], "resultado": "ok"}),
    ("op-sellado-carroceria-001", "robot-sellado-001", "supervisor-carroceria",
     "Aplicación Masilla Estructural — Serie ATL-09830/09840", "running",
     {"programId": "SELL-EST-v2.0", "masilla": "Sika 260 i-Cure",
      "consumo_ml_por_vehiculo": 480, "vehiculos_procesados": 24}),
    ("op-ktl-linea-001", "cabina-electroforesis-001", "supervisor-pintura",
     "Cataforesis KTL — Lote 847 (40 carrocerías)", "running",
     {"lote": "KTL-2024-847", "vehiculosEnBano": 8, "cicloMin": 25,
      "temperaturaObjetivo": 30, "tensionObjetivo": 330}),
    ("op-pintura-color-001", "robot-pintura-002", "supervisor-pintura",
     "Aplicación Color Exterior — Azul Atlántico Metalizado (Lote 847)", "running",
     {"colorCode": "IBER-5028-ATL-MET", "colorName": "Azul Atlántico Metalizado",
      "viscosidadCP": 22, "capasAplicadas": 2, "vehiculosOK": 18}),
    ("op-curado-barniz-001", "horno-curado-002", "supervisor-pintura",
     "Curado Barniz Transparente — Lote 847", "running",
     {"temperaturaPico": 182, "tiempoEnHorno": 28, "velocidadCadena": 4.2,
      "vehiculosEnHorno": 6}),
    ("op-montaje-motor-001", "robot-montaje-motor-001", "operario-motores-001",
     "Ensamblado Motor Eléctrico — Serie MO-ATL-2024-4817", "running",
     {"motorRef": "ATL-EM-220kW-4WD", "par_Nm": 740, "potencia_kW": 220,
      "motoresMontados": 32, "erroresApriete": 0}),
    ("op-banco-motor-001", "banco-pruebas-motor-001", "tecnico-mant-001",
     "Ensayo Motor MO-ATL-2024-4801 — Verificación Rendimiento", "finished",
     {"motorId": "MO-ATL-2024-4801", "rpm_max_alcanzadas": 12840,
      "par_max_Nm": 724, "eficiencia_pct": 94.7, "resultado": "APTO",
      "alertas": []}),
    ("op-banco-motor-002", "banco-pruebas-motor-002", "tecnico-mant-002",
     "Ensayo Motor MO-ATL-2024-4802 — Verificación Rendimiento", "running",
     {"motorId": "MO-ATL-2024-4802", "rpm_actual": 6200,
      "par_actual_Nm": 318, "temperatura_devanados": 78.4}),
    ("op-montaje-final-001", "robot-montaje-final-001", "supervisor-montaje",
     "Montaje Puertas Delanteras — VIN ATL2024VA09841XXX", "running",
     {"vin": "ATL2024VA09841XXX", "modelo": "IBERMOT Atlante 4WD AWD",
      "puestosCompletados": 3, "aprieteOK": True, "alertas": []}),
    ("op-equilibrado-001", "equilibrado-ruedas-001", "operario-montaje-001",
     "Equilibrado Neumáticos — Turno A", "running",
     {"neumatico": "BRIDGESTONE Turanza ECO 235/55R19", "presionBar": 2.6,
      "ruedas_ok_hoy": 1842, "ruedas_nok_hoy": 3, "umbral_g_max": 10}),
    ("op-prueba-final-001", "banco-final-001", "supervisor-montaje",
     "Verificación Final Rodillos — VIN ATL2024VA09837XXX", "finished",
     {"vin": "ATL2024VA09837XXX", "frenos_ok": True, "emision_nox_ppm": 2.1,
      "consumo_kwh100km": 18.5, "alineacion_mm": 0.8, "resultado": "APTO"}),
    ("op-mantenimiento-agv-001", "agv-montaje-003", "tecnico-mant-001",
     "Mantenimiento Preventivo AGV-MF-03 — PM2000h", "running",
     {"tipoMantenimiento": "PM-2000h", "tareasPendientes": ["cambio batería", "calibración láser"],
      "horasRestantes": 2.5}),
]

OPERATIONS = []
for op_data in OP_DEFS:
    oid, machine_suffix, person_suffix, opname, opstatus, op_output = op_data
    start_offset = random.randint(30, 480)
    end_offset   = random.randint(0, 25) if opstatus == "finished" else None

    op = {
        "id":             f"urn:ngsi-ld:ManufacturingMachineOperation:{oid}",
        "type":           "ManufacturingMachineOperation",
        "name":           prop(opname),
        "machine":        rel(f"urn:ngsi-ld:ManufacturingMachine:{machine_suffix}"),
        "operator":       rel(f"urn:ngsi-ld:Person:{person_suffix}"),
        "operationType":  prop(["process"]),
        "status":         prop(opstatus),
        "result":         prop("ok" if opstatus == "finished" else ""),
        "plannedStartAt": prop(now_iso(start_offset + 60)),
        "plannedEndAt":   prop(now_iso(60)),
        "startedAt":      prop(now_iso(start_offset)),
        "endedAt":        prop(now_iso(end_offset) if end_offset is not None else ""),
        "operationOutput":prop(op_output),
        "source":         prop("MES IBERMOT — SAP PP"),
        "dataProvider":   prop("https://data.ibermot.es"),
    }
    OPERATIONS.append(op)

# ══════════════════════════════════════════════════════════════════════════════
# RESUMEN DE ENTIDADES
# ══════════════════════════════════════════════════════════════════════════════

ALL_ENTITIES = (
    [BUILDING]
    + SPACES
    + MODELS
    + PERSONS
    + MACHINES
    + DEVICES
    + MEASUREMENTS
    + OPERATIONS
)

ALL_IDS = [e["id"] for e in ALL_ENTITIES]

def print_summary():
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║       IBERMOT S.A. — Planta Fabricación Valladolid          ║
║       SUV Eléctrico IBERMOT Atlante                         ║
╠══════════════════════════════════════════════════════════════╣
║  Broker   : {BROKER:<48}║
║  Tenant   : {(ARGS.tenant or 'default (sin tenant)'):<48}║
╠══════════════════════════════════════════════════════════════╣
║  Building             :   {len([BUILDING]):<5}                              ║
║  BuildingSpaces       :   {len(SPACES):<5}                              ║
║  ManufacturingMachineModels: {len(MODELS):<5}                              ║
║  Persons              :   {len(PERSONS):<5}                              ║
║  ManufacturingMachines:   {len(MACHINES):<5}                              ║
║  Devices              :   {len(DEVICES):<5}                              ║
║  DeviceMeasurements   :   {len(MEASUREMENTS):<5}                              ║
║  Operations           :   {len(OPERATIONS):<5}                              ║
╠══════════════════════════════════════════════════════════════╣
║  TOTAL ENTIDADES      :   {len(ALL_ENTITIES):<5}                              ║
╚══════════════════════════════════════════════════════════════╝
""")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main_load():
    print_summary()
    if ARGS.dry_run:
        print("  [DRY-RUN] No se enviará ninguna entidad al broker.\n")

    batches = [
        ("Building",                    [BUILDING]),
        ("BuildingSpaces",              SPACES),
        ("ManufacturingMachineModels",  MODELS),
        ("Persons",                     PERSONS),
        ("ManufacturingMachines",       MACHINES),
        ("Devices",                     DEVICES),
        ("DeviceMeasurements",          MEASUREMENTS),
        ("ManufacturingMachineOperations", OPERATIONS),
    ]

    total_ok = total_err = 0
    for batch_name, entities in batches:
        print(f"\n▶  {batch_name} ({len(entities)})")
        ok = err = 0
        for e in entities:
            if post_entity(e):
                ok += 1
                sys.stdout.write(".")
            else:
                err += 1
                sys.stdout.write("✗")
            sys.stdout.flush()
            if ARGS.delay > 0:
                time.sleep(ARGS.delay)
        print(f"  → {ok} OK  /  {err} errores")
        total_ok += ok; total_err += err

    print(f"""
{'═'*60}
  CARGA COMPLETADA
  OK : {total_ok}
  ERR: {total_err}
  TOTAL: {total_ok + total_err}
{'═'*60}
""")

def main_delete():
    print_summary()
    print(f"⚠️  Eliminando {len(ALL_IDS)} entidades de {BROKER}...")
    ok = err = 0
    for eid in ALL_IDS:
        if delete_entity(eid):
            ok += 1
            sys.stdout.write(".")
        else:
            err += 1
        sys.stdout.flush()
    print(f"\n  Eliminadas: {ok}  /  No encontradas o error: {err}")

def main_list():
    print_summary()
    print("  IDs que se cargarian en Orion:\n")
    for i, eid in enumerate(ALL_IDS, 1):
        print(f"  {i:4d}.  {eid}")
    print(f"\n  Total: {len(ALL_IDS)} entidades")

if __name__ == "__main__":
    if ARGS.delete:
        main_delete()
    elif ARGS.list:
        main_list()
    else:
        main_load()