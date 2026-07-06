#!/usr/bin/env python3
"""
load_metapan.py — METAPAN S.A. | Centro de Producción de Baguettes y Barras Congeladas
========================================================================================
Ubicación esperada:
  07_inn_espacio_de_datos/examples/factory-02/load_metapan.py

Genera ~363 entidades NGSI-LD representando una planta industrial de fabricación
de baguettes y barras de pan congelado. Gama única especializada: baguette clásica,
barra rústica y barra de cereales.

Proceso: Almacén harinas → Amasado → Pre-fermentación → Formado → Fermentación
         final → Cocción (hornos túnel + rotativos) → Congelación IQF → Envasado

Uso:
  python3 load_metapan.py
  python3 load_metapan.py --broker http://localhost:1027 --tenant metapan
  python3 load_metapan.py --dry-run
  python3 load_metapan.py --delete
  python3 load_metapan.py --list
"""

import argparse, json, sys, time, random
import urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── CLI ───────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="Cargador de fábrica METAPAN → Orion-LD")
    p.add_argument("--broker",  default="http://localhost:1026")
    p.add_argument("--tenant",  default="")
    p.add_argument("--timeout", type=int,   default=15)
    p.add_argument("--delay",   type=float, default=0.05)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--delete",  action="store_true")
    p.add_argument("--list",    action="store_true")
    return p.parse_args()

ARGS = parse_args()
BROKER  = ARGS.broker.rstrip("/")
NGSI    = f"{BROKER}/ngsi-ld/v1"

# Detección automática del contexto del proyecto
_SCRIPT_DIR  = Path(__file__).resolve().parent
_PROJECT_CTX = _SCRIPT_DIR / ".." / ".." / "07INN_DATA_SPACE" / "context" / "metapan-context.jsonld"
_CORE_URL    = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"

def _resolve_context():
    ctx_path = _PROJECT_CTX.resolve()
    if ctx_path.exists():
        try:
            with open(ctx_path, encoding="utf-8") as f:
                data = json.load(f)
                ctx = data.get("@context", data)
                print(f"  Contexto: archivo local ({ctx_path.name})")
                return ctx
        except Exception as e:
            print(f"  Contexto: error leyendo local ({e}). Usando core.")
    else:
        print(f"  Contexto: NGSI-LD core estandar")
    return _CORE_URL

CONTEXT = _resolve_context()

def _headers():
    h = {"Content-Type": "application/ld+json", "Accept": "application/ld+json"}
    if ARGS.tenant: h["NGSILD-Tenant"] = ARGS.tenant
    return h

def _get_headers():
    h = {"Accept": "application/ld+json"}
    if ARGS.tenant: h["NGSILD-Tenant"] = ARGS.tenant
    return h

# ── HTTP ──────────────────────────────────────────────────────────────────────
def post_entity(e):
    if ARGS.dry_run: print(f"  [DRY] {e['id']}"); return True
    payload = {"@context": CONTEXT, **e}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{NGSI}/entities", data=data, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=ARGS.timeout) as r:
            return r.status in (201, 204)
    except urllib.error.HTTPError as e:
        if e.code == 409: return patch_entity(e)
        print(f"  ERR POST {e['id']}: HTTP {e.code}")
        return False
    except Exception as ex:
        print(f"  ERR {e['id']}: {ex}"); return False

def patch_entity(entity):
    eid   = entity["id"]
    attrs = {k: v for k, v in entity.items() if k not in ("id", "type")}
    data  = json.dumps({"@context": CONTEXT, **attrs}).encode()
    enc   = urllib.parse.quote(eid, safe="")
    req   = urllib.request.Request(f"{NGSI}/entities/{enc}/attrs", data=data, headers=_headers(), method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=ARGS.timeout) as r: return r.status in (200, 204)
    except: return False

def delete_entity(eid):
    enc = urllib.parse.quote(eid, safe="")
    req = urllib.request.Request(f"{NGSI}/entities/{enc}", headers=_get_headers(), method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=ARGS.timeout) as r: return r.status in (200, 204)
    except: return False

# ── Constructores NGSI-LD ─────────────────────────────────────────────────────
def prop(v):      return {"type": "Property",     "value": v}
def rel(u):       return {"type": "Relationship", "object": u}
def geo(lon, lat):return {"type": "GeoProperty",  "value": {"type": "Point", "coordinates": [lon, lat]}}
def ts(v, obs=None):
    r = {"type": "Property", "value": v}
    if obs: r["observedAt"] = obs
    return r

BASE_LAT, BASE_LON = 37.3576, -5.9676   # Pol. Industrial Carretera Málaga, Sevilla

def jitter(lon, lat, s=0.0003):
    return round(lon + random.uniform(-s, s), 6), round(lat + random.uniform(-s, s), 6)

def now_iso(offset_minutes=0):
    dt = datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

# ══════════════════════════════════════════════════════════════════════════════
# 1. BUILDING
# ══════════════════════════════════════════════════════════════════════════════
BUILDING_ID = "urn:ngsi-ld:Building:metapan-centro-produccion-sevilla"

BUILDING = {
    "id":   BUILDING_ID,
    "type": "Building",
    "name":        prop("METAPAN S.A. — Centro de Producción de Baguettes y Barras Congeladas"),
    "description": prop(
        "Planta industrial de fabricación de baguettes y barras de pan congelado. "
        "Línea única especializada: baguette clásica, barra rústica y barra de cereales. "
        "Capacidad: 18 000 kg/turno. Certificación ISO 22000:2018 y IFS Food v8."),
    "category":    prop(["industrial", "foodProcessing"]),
    "address":     prop({
        "streetAddress":   "Polígono Industrial Carretera Málaga, Parcela 7-B",
        "addressLocality": "Sevilla",
        "addressRegion":   "Andalucía",
        "addressCountry":  "ES",
        "postalCode":      "41007"
    }),
    "location":     geo(BASE_LON, BASE_LAT),
    "occupier":     prop(["METAPAN S.A."]),
    "openingHours": prop(["Mo-Sa 05:00-23:00"]),
    "source":       prop("Sistema de Gestión METAPAN"),
    "dataProvider": prop("https://data.metapan.es"),
}

# ══════════════════════════════════════════════════════════════════════════════
# 2. BUILDING SPACES
# ══════════════════════════════════════════════════════════════════════════════
SPACE_DEFS = [
    ("almacen-harinas",
     "Almacén de Harinas y Materias Primas",
     "Almacenamiento de harina de trigo en silos verticales (4 × 25 t), levadura, sal, "
     "mejorant es y semillas. Temperatura controlada 15–18 °C. Acceso restringido APPCC.",
     BASE_LON - 0.0012, BASE_LAT + 0.0006),
    ("sala-amasado",
     "Sala de Amasado y Dosificación",
     "4 amasadoras espirales Diosna SP 240 D. Dosificación automática de ingredientes "
     "mediante básculas checkweigher. Temperatura sala 18–22 °C.",
     BASE_LON - 0.0007, BASE_LAT + 0.0004),
    ("camara-pre-fermentacion",
     "Cámara de Pre-fermentación y Reposo (Retarder-Prover)",
     "Cámara de bloqueo y retardo de fermentación Mondial Forni CR-240. "
     "Temperatura: 2–6 °C (retardo) / 27–32 °C (activación). Humedad: 75–85 %.",
     BASE_LON - 0.0003, BASE_LAT + 0.0003),
    ("sala-formado",
     "Sala de División, Laminado y Formado de Barras",
     "3 divisoras volumétricas WP RotoSplit E y 2 formadoras-bagueteras Rondo DP 800. "
     "Temperatura sala 18–20 °C para controlar fermentación durante el formado.",
     BASE_LON + 0.0001, BASE_LAT + 0.0001),
    ("camara-fermentacion-final",
     "Cámara de Fermentación Final y Greñado",
     "2 cámaras de fermentación final Mondial Forni TF-200 con control preciso de "
     "temperatura (27–32 °C) y humedad (75–85 %). Capacidad: 800 barras/cámara.",
     BASE_LON + 0.0004, BASE_LAT - 0.0001),
    ("sala-hornos",
     "Sala de Hornos de Cocción — Línea Baguette",
     "3 hornos de túnel Revent 725 TS para cocción continua de baguettes y barras. "
     "2 hornos rotativos Miwe Aeromat 8.16 para barras rústicas y de cereales. "
     "Inyección de vapor. Temperatura de trabajo: 220–260 °C.",
     BASE_LON + 0.0008, BASE_LAT - 0.0003),
    ("tunel-congelacion",
     "Túnel de Congelación IQF y Almacén Frigorífico",
     "2 túneles de congelación IQF JBT GYRoCOMPACT M. Temperatura aire: -38 °C. "
     "Tiempo de congelación baguette: 12–15 min. Almacén frigorífico -22 °C (1200 m²).",
     BASE_LON + 0.0011, BASE_LAT - 0.0006),
    ("sala-envasado",
     "Sala de Envasado, Etiquetado y Expedición",
     "2 líneas de envasado termoformado Ulma TFS 200 RD. Checkweighers + detectores "
     "de metales Marel Semira en cada línea. Temperatura sala ≤ 12 °C.",
     BASE_LON + 0.0007, BASE_LAT - 0.0009),
    ("laboratorio-calidad",
     "Laboratorio de Calidad y Control APPCC",
     "Análisis microbiológicos, fisicoquímicos y organolépticos. Control de puntos "
     "críticos (PCCs) según plan APPCC. Archivo de trazabilidad por lote.",
     BASE_LON - 0.0009, BASE_LAT - 0.0005),
]

SPACES = []
for sid, sname, sdesc, slon, slat in SPACE_DEFS:
    SPACES.append({
        "id":                f"urn:ngsi-ld:BuildingSpace:{sid}",
        "type":              "BuildingSpace",
        "name":              prop(sname),
        "description":       prop(sdesc),
        "buildingSpaceType": prop("production-floor"),
        "isSpaceOf":         rel(BUILDING_ID),
        "location":          geo(slon, slat),
        "source":            prop("Plano CAD METAPAN v4.2"),
        "dataProvider":      prop("https://data.metapan.es"),
    })

def space_id(s): return f"urn:ngsi-ld:BuildingSpace:{s}"

# ══════════════════════════════════════════════════════════════════════════════
# 3. MACHINE MODELS
# ══════════════════════════════════════════════════════════════════════════════
MODEL_DEFS = [
    ("diosna-sp240d",
     "Diosna SP 240 D", "Diosna Perner & Sons GmbH",
     "Amasadora espiral de alta velocidad para masas de baguette. Capacidad 240 kg/amasada. "
     "Bol fijo. Velocidad lenta 100 rpm / rápida 200 rpm. Control de temperatura de masa.",
     "SP 240 D", "https://www.diosna.com/en/products/mixers/spiral-mixers"),
    ("wp-rotosplit-e",
     "WP RotoSplit E", "WP Bakery Group",
     "Divisora volumétrica de alta precisión para piezas de 200–600 g. "
     "Cadencia hasta 3600 piezas/h. Variación de peso ± 1 %. Limpieza CIP.",
     "RotoSplit E-600", "https://www.wp-bakerygroup.com"),
    ("rondo-dp800",
     "Rondo DP 800", "Rondo Burgdorf AG",
     "Laminadora-formadora-baguetera automática. Longitud baguette 25–65 cm. "
     "Producción hasta 5000 piezas/h. Ajuste sin herramientas.",
     "DP 800/5000", "https://www.rondo-online.com"),
    ("mondial-forni-cr240",
     "Mondial Forni CR 240", "Mondial Forni S.r.l.",
     "Cámara retarder-prover automática para bloques de masa. Capacidad 240 bandejas. "
     "Ciclo retardo: 2–6 °C / Activación: 27–32 °C / Humedad: 75–85 %.",
     "CR 240 Basic", "https://www.mondialforni.it"),
    ("mondial-forni-tf200",
     "Mondial Forni TF 200", "Mondial Forni S.r.l.",
     "Cámara de fermentación final con control independiente de temperatura y humedad. "
     "Capacidad 200 bandejas (800 barras). Temperatura 27–35 °C, humedad 70–90 %.",
     "TF 200 Pro", "https://www.mondialforni.it"),
    ("revent-725ts",
     "Revent 725 TS", "Revent International AB",
     "Horno de túnel de cocción continua de doble cinta. Longitud útil 12 m. "
     "Producción hasta 1800 baguettes/h por cinta. Inyección de vapor. "
     "Temperatura máx. 300 °C. 5 zonas de control independiente.",
     "725 TS Double-Band", "https://www.revent.com"),
    ("miwe-aeromat-816",
     "Miwe Aeromat 8.16", "Michael Wenz GmbH (MIWE)",
     "Horno rotativo de convección forzada para barras rústicas y de cereales. "
     "8 niveles, 16 bandejas 60×80 cm. Inyección de vapor. Temperatura máx. 280 °C.",
     "Aeromat 8.16 TS", "https://www.miwe.de"),
    ("jbt-gyrocompact-m",
     "JBT GYRoCOMPACT M", "John Bean Technologies (JBT)",
     "Túnel de congelación IQF de cinta helicoidal. Temperatura de trabajo -38 °C. "
     "Capacidad 1200 kg/h. Congelación individual de baguettes en 12–15 min.",
     "GYRoCOMPACT M-160", "https://www.jbtfoodtech.com"),
    ("ulma-tfs200rd",
     "Ulma TFS 200 RD", "Ulma Packaging S. Coop.",
     "Envasadora termoformado para baguettes congeladas. Formato film inferior/superior. "
     "Velocidad hasta 30 ciclos/min. ATM (atmósfera modificada). Impresión integrada.",
     "TFS 200 RD", "https://www.ulmapackaging.com"),
    ("marel-semira",
     "Marel Semira", "Marel hf.",
     "Checkweigher + detector de metales en línea. Precisión ± 1 g. "
     "Velocidad hasta 200 productos/min. Detección Fe 1.5 mm / SUS 2.0 mm / NFe 2.0 mm.",
     "Semira 2000", "https://www.marel.com"),
    ("cimbria-silo25",
     "Cimbria Silo Vertical 25T", "Cimbria A/S",
     "Silo metálico galvanizado para almacenamiento de harina. Capacidad 25 t. "
     "Sonda de nivel ultrasónica. Extracción por tornillo sinfín motorizado.",
     "SV-25000-GA", "https://www.cimbria.com"),
    ("atlas-copco-ga75",
     "Atlas Copco GA 75 VSD+", "Atlas Copco",
     "Compresor de tornillo rotativo de velocidad variable. Presión 7.5 bar, "
     "caudal 12.2 m³/min. Alimenta red de aire para actuadores y limpieza CIP.",
     "GA 75 VSD+", "https://www.atlascopco.com"),
]

MODELS = []
for mid, mname, brand, mdesc, model_num, url in MODEL_DEFS:
    MODELS.append({
        "id":               f"urn:ngsi-ld:ManufacturingMachineModel:{mid}",
        "type":             "ManufacturingMachineModel",
        "name":             prop(mname),
        "description":      prop(mdesc),
        "brandName":        prop(brand),
        "modelName":        prop(model_num),
        "manufacturerName": prop(brand),
        "documentation":    prop(url),
        "source":           prop("Catálogo técnico de proveedores METAPAN"),
        "dataProvider":     prop("https://data.metapan.es"),
    })

def model_id(m): return f"urn:ngsi-ld:ManufacturingMachineModel:{m}"

# ══════════════════════════════════════════════════════════════════════════════
# 4. PERSONAS
# ══════════════════════════════════════════════════════════════════════════════
PERSON_DEFS = [
    ("directora-planta",       "Lucía Romero Morales",       "Directora de Planta",                   "+34 954 300 001"),
    ("jefe-produccion",        "Andrés Navarro Castillo",    "Jefe de Producción",                    "+34 954 300 010"),
    ("jefe-calidad",           "Marta Delgado Ruiz",         "Jefa de Calidad e Inocuidad (ISO 22000)","+34 954 300 020"),
    ("jefe-mantenimiento",     "Pablo Herrera Vega",         "Jefe de Mantenimiento",                 "+34 954 300 030"),
    ("responsable-higiene",    "Elena Fuentes Toro",         "Responsable Higiene y Limpieza CIP",    "+34 954 300 040"),
    ("supervisor-amasado",     "Carlos Jiménez Blanco",      "Supervisor Sala Amasado",               "+34 954 300 011"),
    ("supervisor-hornos",      "Rosa Serrano Leal",          "Supervisora Sala Hornos",               "+34 954 300 012"),
    ("supervisor-congelacion", "Miguel Ángel Reyes Cano",   "Supervisor Congelación y Envasado",     "+34 954 300 013"),
    ("tecnico-mant-001",       "Antonio Campos Prieto",      "Técnico de Mantenimiento",              "+34 954 300 031"),
    ("tecnico-mant-002",       "Beatriz Molina Soto",        "Técnica de Mantenimiento",              "+34 954 300 032"),
    ("operario-hornos-001",    "Francisco Domínguez Torres", "Oficial Hornos Turno A",               "+34 954 300 050"),
    ("operario-envasado-001",  "Silvia Guerrero Pérez",      "Operaria Envasado Turno A",             "+34 954 300 051"),
]

# Mapa persona → espacios donde trabaja (para las relaciones del grafo)
_PERSON_SPACES = {
    "directora-planta":       [],                                          # toda la planta
    "jefe-produccion":        ["sala-amasado","sala-formado",
                               "camara-fermentacion-final","sala-hornos"],
    "jefe-calidad":           ["laboratorio-calidad","sala-envasado"],
    "jefe-mantenimiento":     ["sala-hornos","tunel-congelacion",
                               "almacen-harinas"],
    "responsable-higiene":    ["sala-amasado","sala-hornos",
                               "sala-envasado","tunel-congelacion"],
    "supervisor-amasado":     ["sala-amasado","camara-pre-fermentacion",
                               "sala-formado"],
    "supervisor-hornos":      ["camara-fermentacion-final","sala-hornos"],
    "supervisor-congelacion": ["tunel-congelacion","sala-envasado"],
    "tecnico-mant-001":       ["sala-hornos","tunel-congelacion"],
    "tecnico-mant-002":       ["sala-amasado","sala-formado","sala-envasado"],
    "operario-hornos-001":    ["sala-hornos"],
    "operario-envasado-001":  ["sala-envasado"],
}

PERSONS = []
for pid, pname, role, phone in PERSON_DEFS:
    spaces = _PERSON_SPACES.get(pid, [])
    entity = {
        "id":           f"urn:ngsi-ld:Person:{pid}",
        "type":         "Person",
        "name":         prop(pname),
        "jobTitle":     prop(role),
        "telephone":    prop(phone),
        "worksFor":     prop("METAPAN S.A."),
        "worksAt":      rel(BUILDING_ID),
        "source":       prop("RRHH METAPAN S.A."),
        "dataProvider": prop("https://data.metapan.es"),
    }
    # Añadir relaciones con los espacios donde trabaja
    if len(spaces) == 1:
        entity["locatedIn"] = rel(space_id(spaces[0]))
    elif len(spaces) > 1:
        # NGSI-LD permite múltiples instancias de un atributo usando datasetId,
        # pero para compatibilidad máxima usamos la primera como relación principal
        # y las adicionales como propiedad de lista
        entity["locatedIn"]       = rel(space_id(spaces[0]))
        entity["worksInSpaces"]   = prop([space_id(s) for s in spaces])
    PERSONS.append(entity)

# ══════════════════════════════════════════════════════════════════════════════
# 5. MÁQUINAS Y DISPOSITIVOS
# ══════════════════════════════════════════════════════════════════════════════
# Formato dispositivo: (suffix, name, controlledProperty, unitCode, unitText, value, vmin, vmax)

MACHINE_CATALOG = [

    # ── SILOS DE HARINA (4 unidades) ─────────────────────────────────────────
    *[{
        "id": f"silo-harina-00{i}", "model": "cimbria-silo25",
        "space": "almacen-harinas",
        "name": f"Silo de Harina Cimbria #{i} — {'Harina T65 Baguette' if i<=2 else 'Harina T80 Integral/Cereales'}",
        "desc": f"Silo vertical 25 t de harina {'de trigo T65 para baguette clásica' if i<=2 else 'de trigo integral T80 y mezcla de cereales'}. Extracción por tornillo sinfín.",
        "serial": f"CIMB-SV25-2022-{i:03d}", "status": "running", "power": 2.2, "voltage": 400,
        "supplier": "Cimbria Ibérica S.L.", "installed": f"2022-04-{10+i:02d}T00:00:00Z",
        "devices": [
            ("nivel",      f"Nivel Harina Silo {i:02d}",           "fillingLevel",   "P1",  "%",      72 - i*8,   5,  100),
            ("temp-silo",  f"Temperatura Interior Silo {i:02d}",   "temperature",    "CEL", "°C",     16.5 + i*0.3, 12, 22),
            ("humedad",    f"Humedad Relativa Silo {i:02d}",       "humidity",       "P1",  "%",      62 - i*2,  55,   70),
        ]
    } for i in range(1, 5)],

    # ── AMASADORAS DIOSNA (4 unidades) ───────────────────────────────────────
    *[{
        "id": f"amasadora-00{i}", "model": "diosna-sp240d",
        "space": "sala-amasado",
        "name": f"Amasadora Espiral Diosna SP 240 D — Línea {i}",
        "desc": f"Amasado de masa de baguette. Fórmula {'estándar T65 con levadura fresca' if i<=2 else 'T80 con levadura + masa madre'}. Capacidad 240 kg/amasada.",
        "serial": f"DIOSN-SP240-2021-{i:03d}", "status": "running", "power": 22, "voltage": 400,
        "supplier": "Diosna Ibérica S.A.U.", "installed": f"2021-09-{i:02d}T00:00:00Z",
        "devices": [
            ("temp-masa",     f"Temperatura Masa Amasadora A{i:02d}",    "temperature",    "CEL", "°C",      24.2 + i*0.3, 20,  28),
            ("velocidad",     f"Velocidad Espiral Amasadora A{i:02d}",   "rotationalSpeed","RPM", "rpm",     180 - i*10,   80, 200),
            ("par-motor",     f"Par Motor Amasadora A{i:02d}",           "torque",         "N.M", "N·m",     185 + i*5,    50, 350),
            ("corriente",     f"Corriente Motor Amasadora A{i:02d}",     "electricCurrent","AMP", "A",       28.4 + i*0.5,  0,  45),
            ("tiempo-ciclo",  f"Tiempo de Ciclo Amasadora A{i:02d}",     "time",           "MIN", "min",     14 + i,       8,  25),
        ]
    } for i in range(1, 5)],

    # ── RETARDER-PROVER (1 unidad grande) ────────────────────────────────────
    {
        "id": "retarder-prover-001", "model": "mondial-forni-cr240",
        "space": "camara-pre-fermentacion",
        "name": "Cámara Retarder-Prover Mondial Forni CR 240 — Pre-fermentación",
        "desc": "Bloqueo y activación controlada de la fermentación en bloque. "
                "Ciclo: retardo 2–6 °C hasta 16h / activación gradual hasta 30 °C.",
        "serial": "MONDE-CR240-2021-001", "status": "running", "power": 18, "voltage": 400,
        "supplier": "Mondial Forni España S.L.", "installed": "2021-10-01T00:00:00Z",
        "devices": [
            ("temp-interior",  "Temperatura Interior Retarder",          "temperature",    "CEL", "°C",      4.8,   1,  35),
            ("humedad",        "Humedad Relativa Retarder",               "humidity",       "P1",  "%",      82.0,  70,  92),
            ("temp-evap",      "Temperatura Evaporador Retarder",         "temperature",    "CEL", "°C",     -4.2, -15,   5),
            ("nivel-ocupacion","Nivel de Ocupación Retarder",             "fillingLevel",   "P1",  "%",      68.0,   0, 100),
            ("consumo-frio",   "Consumo Frigorífico Retarder",            "power",          "KWT", "kW",     12.4,   0,  20),
        ]
    },

    # ── DIVISORAS WP (3 unidades) ─────────────────────────────────────────────
    *[{
        "id": f"divisora-00{i}", "model": "wp-rotosplit-e",
        "space": "sala-formado",
        "name": f"Divisora Volumétrica WP RotoSplit E — Puesto {i}",
        "desc": f"División de piezas de {'250 g (baguette 40 cm)' if i<=2 else '300 g (barra rústica 50 cm)'}. Cadencia nominal 3000 piezas/h.",
        "serial": f"WPROTO-E600-2022-{i:03d}", "status": "running", "power": 5.5, "voltage": 400,
        "supplier": "WP Bakery Group Iberia", "installed": f"2022-02-{10+i:02d}T00:00:00Z",
        "devices": [
            ("peso-pieza",   f"Peso de Pieza Divisora D{i:02d}",         "weight",         "GRM", "g",      251.2 + i*0.8, 245,  270),
            ("cadencia",     f"Cadencia Divisora D{i:02d}",              "flow",           "C62", "pzas/h", 2980 - i*50,  1000, 3600),
            ("presion-camara",f"Presión Cámara Volumétrica D{i:02d}",    "pressure",       "BAR", "bar",     3.8 + i*0.1,  2.5,   5.5),
            ("contador",     f"Contador de Piezas D{i:02d}",             "cycleCount",     "C62", "pzas",  184500 + i*2000, 0, 9999999),
        ]
    } for i in range(1, 4)],

    # ── FORMADORAS-BAGUETERAS RONDO (2 unidades) ─────────────────────────────
    *[{
        "id": f"formadora-00{i}", "model": "rondo-dp800",
        "space": "sala-formado",
        "name": f"Formadora-Baguetera Rondo DP 800 — Línea {i}",
        "desc": f"Laminado, enrollado y formado de baguettes. Longitud {'400 mm' if i==1 else '500 mm'}. Producción 4500 piezas/h.",
        "serial": f"RONDO-DP800-2022-{10+i:03d}", "status": "running", "power": 7.5, "voltage": 400,
        "supplier": "Rondo Burgdorf AG (delegación España)", "installed": f"2022-03-{5+i*5:02d}T00:00:00Z",
        "devices": [
            ("presion-rodillos", f"Presión Rodillos Formadora F{i:02d}",    "pressure",   "BAR", "bar",      1.8 + i*0.1, 0.5,  3.5),
            ("cadencia",         f"Cadencia Formadora F{i:02d}",            "flow",       "C62", "pzas/h",  4420 - i*80, 2000, 5000),
            ("contador-barras",  f"Barras Formadas F{i:02d} hoy",           "cycleCount", "C62", "barras",  22140 + i*1000, 0, 9999999),
            ("velocidad-cinta",  f"Velocidad Cinta Salida F{i:02d}",        "velocity",   "MMS", "m/min",    8.4 + i*0.3, 3,    15),
        ]
    } for i in range(1, 3)],

    # ── CÁMARAS DE FERMENTACIÓN FINAL (2 unidades) ───────────────────────────
    *[{
        "id": f"camara-fermentacion-final-00{i}", "model": "mondial-forni-tf200",
        "space": "camara-fermentacion-final",
        "name": f"Cámara Fermentación Final Mondial Forni TF 200 — Unidad {i}",
        "desc": f"Fermentación final de barras antes de cocción. Lote actual: "
                f"{'BG-2024-4819 (baguette clásica)' if i==1 else 'BG-2024-4820 (barra rústica)'}.",
        "serial": f"MONDE-TF200-2021-{i:03d}", "status": "running", "power": 12, "voltage": 400,
        "supplier": "Mondial Forni España S.L.", "installed": f"2021-10-{10+i}T00:00:00Z",
        "devices": [
            ("temp-interior",  f"Temperatura Cámara CF-{i:02d}",        "temperature",    "CEL", "°C",     29.8 + i*0.4, 25,   36),
            ("humedad",        f"Humedad Relativa CF-{i:02d}",           "humidity",       "P1",  "%",      81.0 - i,     68,   92),
            ("co2",            f"CO2 Fermentación CF-{i:02d}",           "concentration",  "PPM", "ppm",   2840 + i*100, 800, 5000),
            ("nivel-ocupacion",f"Ocupación Bandejas CF-{i:02d}",         "fillingLevel",   "P1",  "%",     88.0 - i*5,    0,  100),
            ("velocidad-ventil",f"Velocidad Ventiladores CF-{i:02d}",    "rotationalSpeed","RPM", "rpm",    840 - i*40,  200, 1200),
            ("consumo-ene",    f"Consumo Energético CF-{i:02d}",         "power",          "KWT", "kW",     8.2 + i*0.3,  0,   14),
        ]
    } for i in range(1, 3)],

    # ── HORNOS DE TÚNEL REVENT 725 TS (3 unidades — EQUIPOS CLAVE) ───────────
    *[{
        "id": f"horno-tunel-00{i}", "model": "revent-725ts",
        "space": "sala-hornos",
        "name": f"Horno de Túnel Revent 725 TS — Línea {i} "
                f"({'Baguette Clásica' if i==1 else 'Barra Rústica' if i==2 else 'Barra Cereales'})",
        "desc": f"Cocción continua de {'baguette clásica (250 g, 400 mm)' if i==1 else 'barra rústica (300 g, 500 mm)' if i==2 else 'barra de cereales (280 g, 450 mm)'}. "
                f"Producción {'1800' if i==1 else '1500' if i==2 else '1600'} piezas/h.",
        "serial": f"REVENT-725TS-2021-{i:03d}", "status": "running", "power": 240, "voltage": 400,
        "supplier": "Revent Scandinavia AB — Delegación España", "installed": f"2021-11-{i*5:02d}T00:00:00Z",
        "devices": [
            ("temp-z1",        f"Temperatura Zona 1 — Entrada HT{i:02d}",   "temperature", "CEL", "°C",  215 + i*5,   180, 260),
            ("temp-z2",        f"Temperatura Zona 2 — Central HT{i:02d}",   "temperature", "CEL", "°C",  245 + i*3,   200, 280),
            ("temp-z3",        f"Temperatura Zona 3 — Dorado HT{i:02d}",    "temperature", "CEL", "°C",  238 - i*2,   200, 270),
            ("temp-z4",        f"Temperatura Zona 4 — Final HT{i:02d}",     "temperature", "CEL", "°C",  225 - i*3,   190, 265),
            ("temp-z5",        f"Temperatura Zona 5 — Salida HT{i:02d}",    "temperature", "CEL", "°C",  200 - i*2,   170, 250),
            ("presion-vapor",  f"Presión Vapor Inyección HT{i:02d}",        "pressure",    "BAR", "bar",   1.8 + i*0.1, 0.5, 3.5),
            ("caudal-vapor",   f"Caudal Vapor Inyección HT{i:02d}",         "flow",        "KGH", "kg/h",  18.4 + i*0.5, 2, 40),
            ("velocidad-cinta",f"Velocidad Cinta Horno HT{i:02d}",          "velocity",    "MMS", "m/min",  6.8 + i*0.2, 3,  12),
            ("consumo-gas",    f"Consumo Gas Natural HT{i:02d}",             "flow",        "M3H", "m³/h",  38.5 + i*1.2, 10, 70),
            ("temp-salida-prod",f"Temperatura Núcleo Producto HT{i:02d}",   "temperature", "CEL", "°C",   98.2 + i*0.3, 92, 102),
            ("contador-piezas",f"Producción Acumulada HT{i:02d}",           "cycleCount",  "C62", "pzas", 48200 + i*3000, 0, 9999999),
        ]
    } for i in range(1, 4)],

    # ── HORNOS ROTATIVOS MIWE (2 unidades) ───────────────────────────────────
    *[{
        "id": f"horno-rotativo-00{i}", "model": "miwe-aeromat-816",
        "space": "sala-hornos",
        "name": f"Horno Rotativo Miwe Aeromat 8.16 — {'Barras Especiales A' if i==1 else 'Hornada Extra / Flexibilidad'}",
        "desc": f"Cocción por convección forzada y vapor. {'Barras rústicas y de cereales de alta calidad' if i==1 else 'Flexibilidad para nuevos formatos y pruebas de producto'}.",
        "serial": f"MIWE-AERO816-2022-{i:03d}", "status": "running" if i==1 else "standby",
        "power": 32, "voltage": 400,
        "supplier": "Miwe Backtechnik GmbH — Delegación Ibérica", "installed": f"2022-01-{10+i*5:02d}T00:00:00Z",
        "devices": [
            ("temp-camara",   f"Temperatura Cámara Rotativo HR{i:02d}",    "temperature",    "CEL", "°C",   248 - i*8, 180, 280),
            ("humedad-camara",f"Humedad Cámara Rotativo HR{i:02d}",        "humidity",       "P1",  "%",    72 - i*5,  40,  90),
            ("vel-rotacion",  f"Velocidad Rotación Carro HR{i:02d}",       "rotationalSpeed","RPM", "rpm",   3.2 + i*0.2, 1,   6),
            ("consumo-gas",   f"Consumo Gas Natural Rotativo HR{i:02d}",   "flow",           "M3H", "m³/h", 14.8 - i*2, 3, 30),
            ("temp-salida",   f"Temperatura Núcleo Producto HR{i:02d}",    "temperature",    "CEL", "°C",   96.8 - i*2, 88, 102),
        ]
    } for i in range(1, 3)],

    # ── TÚNELES DE CONGELACIÓN IQF JBT (2 unidades) ──────────────────────────
    *[{
        "id": f"tunel-iqf-00{i}", "model": "jbt-gyrocompact-m",
        "space": "tunel-congelacion",
        "name": f"Túnel Congelación IQF JBT GYRoCOMPACT M — Línea {'A' if i==1 else 'B'}",
        "desc": f"Congelación individual de {'baguettes clásicas y barras rústicas' if i==1 else 'barras de cereales y formatos especiales'}. "
                f"Temperatura aire -38 °C. Tiempo congelación: 12–15 min.",
        "serial": f"JBT-GYRO-M160-2021-{i:03d}", "status": "running", "power": 185, "voltage": 400,
        "supplier": "JBT Food Technologies Iberia S.L.", "installed": f"2021-12-{i*5:02d}T00:00:00Z",
        "devices": [
            ("temp-aire-iqf",    f"Temperatura Aire IQF TI{i:02d}",        "temperature",  "CEL", "°C",   -37.8 + i*0.3, -42, -32),
            ("temp-salida-prod", f"Temperatura Núcleo Producto TI{i:02d}",  "temperature",  "CEL", "°C",   -19.2 - i*0.4, -25, -16),
            ("velocidad-cinta",  f"Velocidad Cinta IQF TI{i:02d}",         "velocity",     "MMS", "m/min",  1.8 + i*0.1, 0.5,  4),
            ("consumo-frio",     f"Consumo Frigorífico TI{i:02d}",         "power",        "KWT", "kW",    162 + i*8,    80, 200),
            ("temp-evaporador",  f"Temperatura Evaporador TI{i:02d}",      "temperature",  "CEL", "°C",   -43.2 - i*0.5,-50, -38),
            ("kg-procesados-h",  f"Producción Kg/h TI{i:02d}",             "flow",         "KGH", "kg/h",  1080 - i*40, 200, 1200),
        ]
    } for i in range(1, 3)],

    # ── ENVASADORAS ULMA (2 unidades) ────────────────────────────────────────
    *[{
        "id": f"envasadora-00{i}", "model": "ulma-tfs200rd",
        "space": "sala-envasado",
        "name": f"Envasadora Termoformado Ulma TFS 200 RD — Línea {i}",
        "desc": f"Envasado termoformado en atmósfera modificada de {'baguette clásica y barra rústica' if i==1 else 'barra de cereales y formatos 2 uds.'}.",
        "serial": f"ULMA-TFS200RD-2022-{i:03d}", "status": "running", "power": 14, "voltage": 400,
        "supplier": "Ulma Packaging S. Coop.", "installed": f"2022-05-{i*10:02d}T00:00:00Z",
        "devices": [
            ("temp-sellado-inf", f"Temperatura Sellado Inferior EV{i:02d}", "temperature",  "CEL", "°C",   182 + i*3,   160, 210),
            ("temp-sellado-sup", f"Temperatura Sellado Superior EV{i:02d}", "temperature",  "CEL", "°C",   175 + i*2,   155, 205),
            ("velocidad-linea",  f"Velocidad Línea Envasado EV{i:02d}",     "velocity",     "C62", "ciclos/min", 24 - i, 10,  30),
            ("contador-envases", f"Envases Producidos EV{i:02d} hoy",       "cycleCount",   "C62", "envases", 12840 + i*500, 0, 9999999),
            ("tasa-rechazo",     f"Tasa de Rechazo Calidad EV{i:02d}",      "efficiency",   "P1",  "%",       0.8 + i*0.2, 0, 5),
        ]
    } for i in range(1, 3)],

    # ── CHECKWEIGHERS + DETECTOR METALES (2 unidades) ────────────────────────
    *[{
        "id": f"checkweigher-00{i}", "model": "marel-semira",
        "space": "sala-envasado",
        "name": f"Checkweigher + Detector Metales Marel Semira — Línea {i}",
        "desc": f"Control de peso y seguridad alimentaria en línea {i}. "
                f"Umbral rechazo: peso ± 5 g. Detección metales: Fe 1.5 mm.",
        "serial": f"MAREL-SEM2000-2022-{i:03d}", "status": "running", "power": 1.2, "voltage": 230,
        "supplier": "Marel España S.A.U.", "installed": f"2022-05-{i*10+5:02d}T00:00:00Z",
        "devices": [
            ("peso-medio",        f"Peso Medio Producto CW{i:02d}",      "weight",       "GRM", "g",     251.8 + i*0.5, 240, 280),
            ("tasa-rechazo",      f"Tasa Rechazo Peso CW{i:02d}",        "efficiency",   "P1",  "%",       0.4 + i*0.1,   0,   5),
            ("detector-metales",  f"Estado Detector Metales CW{i:02d}",  "occupancyRate","P1",  "OK=100", 100,           0, 100),
            ("cadencia",          f"Cadencia Control CW{i:02d}",         "flow",         "C62", "pzas/min", 88 - i*5,   20, 120),
        ]
    } for i in range(1, 3)],

    # ── COMPRESORES ATLAS COPCO (2 unidades) ─────────────────────────────────
    *[{
        "id": f"compresor-00{i}", "model": "atlas-copco-ga75",
        "space": "almacen-harinas",
        "name": f"Atlas Copco GA 75 VSD+ — Compresor {'Principal' if i==1 else 'Respaldo'}",
        "desc": f"Compresor tornillo velocidad variable. Alimenta red de aire comprimido para "
                f"{'toda la planta (actuadores, limpieza, dosificación)' if i==1 else 'zona de envasado y backup'}.",
        "serial": f"ATLCO-GA75VSD-2021-{i:03d}", "status": "running" if i==1 else "standby",
        "power": 75, "voltage": 400,
        "supplier": "Atlas Copco Compressors S.A.U.", "installed": f"2021-08-{i*5:02d}T00:00:00Z",
        "devices": [
            ("presion-salida",  f"Presión Red Aire COM{i:02d}",           "pressure",    "BAR", "bar",      7.3 + i*0.1, 6.5, 8.0),
            ("temp-aire",       f"Temperatura Aire Comprimido COM{i:02d}","temperature", "CEL", "°C",       36 + i*2,   20,  70),
            ("caudal",          f"Caudal Producido COM{i:02d}",            "flow",        "M3M", "m³/min",  11.2 + i*0.3, 0, 12.2),
            ("horas",           f"Horas de Operación COM{i:02d}",          "time",        "HUR", "h",       14820 + i*800, 0, 9999999),
            ("nivel-aceite",    f"Nivel Aceite Compresor COM{i:02d}",      "fillingLevel","P1",  "%",       84 - i*8,   20, 100),
        ]
    } for i in range(1, 3)],
]

# ── Generar Máquinas + Devices + Measurements ─────────────────────────────────
MACHINES, DEVICES, MEASUREMENTS = [], [], []

for spec in MACHINE_CATALOG:
    mid   = spec["id"]
    space = space_id(spec["space"])
    lon, lat = jitter(BASE_LON, BASE_LAT)
    device_urns = [f"urn:ngsi-ld:Device:{mid}-{d[0]}" for d in spec["devices"]]

    machine = {
        "id":            f"urn:ngsi-ld:ManufacturingMachine:{mid}",
        "type":          "ManufacturingMachine",
        "name":          prop(spec["name"]),
        "description":   prop(spec["desc"]),
        "serialNumber":  prop(spec["serial"]),
        "status":        prop(spec["status"]),
        "online":        prop(spec["status"] != "maintenance"),
        "power":         prop(spec["power"]),
        "voltage":       prop(spec["voltage"]),
        "machineModel":  rel(model_id(spec["model"])),
        "building":      rel(BUILDING_ID),
        "locatedIn":     rel(space),
        "location":      geo(lon, lat),
        "installedAt":   prop(spec["installed"]),
        "supplierName":  prop(spec["supplier"]),
        "componentes":   prop(device_urns),
        "source":        prop("SCADA METAPAN — OPC-UA Bridge"),
        "dataProvider":  prop("https://data.metapan.es"),
    }
    MACHINES.append(machine)

    for d in spec["devices"]:
        suffix, dname, dprop, dunit, dunit_text, dval, vmin, vmax = d
        did = f"urn:ngsi-ld:Device:{mid}-{suffix}"
        dlon, dlat = jitter(lon, lat, 0.00005)

        DEVICES.append({
            "id":                 did,
            "type":               "Device",
            "name":               prop(dname),
            "description":        prop(f"Sensor/actuador '{dname}' en {spec['name']}."),
            "controlledAsset":    rel(f"urn:ngsi-ld:ManufacturingMachine:{mid}"),
            "controlledProperty": prop([dprop]),
            "deviceCategory":     prop(["sensor"]),
            "status":             prop("ok" if spec["status"] != "maintenance" else "maintenance"),
            "online":             prop(spec["status"] != "maintenance"),
            "unitCode":           prop(dunit),
            "unitText":           prop(dunit_text),
            "measurementType":    prop(["instantaneous"]),
            "location":           geo(dlon, dlat),
            "source":             prop("SCADA METAPAN — MQTT Bridge"),
            "dataProvider":       prop("https://data.metapan.es"),
        })

        MEASUREMENTS.append({
            "id":                 f"urn:ngsi-ld:DeviceMeasurement:{mid}-{suffix}-meas",
            "type":               "DeviceMeasurement",
            "device":             rel(did),
            "controlledProperty": prop(dprop),
            "numValue":           ts(dval, now_iso(random.randint(0, 8))),
            "measurementType":    prop("instantaneous"),
            "unitCode":           prop(dunit),
            "unitText":           prop(dunit_text),
            "minValue":           prop(vmin),
            "maxValue":           prop(vmax),
            "accuracy":           prop(0.5),
            "dateObserved":       prop(now_iso(random.randint(0, 8))),
            "location":           geo(dlon, dlat),
            "source":             prop("SCADA METAPAN — MQTT Bridge"),
            "dataProvider":       prop("https://data.metapan.es"),
        })

# ══════════════════════════════════════════════════════════════════════════════
# 6. OPERACIONES
# ══════════════════════════════════════════════════════════════════════════════
OP_DEFS = [
    ("op-amasado-lote-4821", "amasadora-001", "supervisor-amasado",
     "Amasado Lote BG-2024-4821 — Baguette Clásica T65", "running",
     {"loteId": "BG-2024-4821", "formula": "BAGUETTE-T65-V3.2",
      "pesoMasaKg": 240, "tempMasaC": 24.2, "tiempoCicloMin": 14,
      "ingredientes": {"harinaT65Kg": 150, "aguaKg": 97.5, "salKg": 3.0,
                       "levadurFrescaKg": 0.9, "mejoranteKg": 0.6}}),
    ("op-amasado-lote-4822", "amasadora-002", "supervisor-amasado",
     "Amasado Lote BG-2024-4822 — Baguette Clásica T65", "running",
     {"loteId": "BG-2024-4822", "formula": "BAGUETTE-T65-V3.2",
      "pesoMasaKg": 240, "tempMasaC": 24.5, "tiempoCicloMin": 14}),
    ("op-amasado-lote-4823", "amasadora-003", "supervisor-amasado",
     "Amasado Lote BR-2024-1105 — Barra Rústica T80", "running",
     {"loteId": "BR-2024-1105", "formula": "BARRA-RUSTICA-T80-V2.1",
      "pesoMasaKg": 240, "tempMasaC": 23.8, "tiempoCicloMin": 16}),
    ("op-pre-ferm-4820", "retarder-prover-001", "supervisor-amasado",
     "Pre-fermentación en Bloque — Lote BG-2024-4820", "running",
     {"loteId": "BG-2024-4820", "faseActual": "activacion",
      "tempRetardoC": 4.8, "tempActivacionC": 29.5,
      "tiempoRetardoH": 8.5, "tiempoActivacionMin": 45}),
    ("op-ferm-final-4819", "camara-fermentacion-final-001", "supervisor-hornos",
     "Fermentación Final Lote BG-2024-4819 — Previo a Cocción", "running",
     {"loteId": "BG-2024-4819", "tempCamaraC": 30.2, "humedadPct": 82,
      "volumenPiezasPct": 85, "tiempoRestanteMin": 22}),
    ("op-coccion-horno1-4818", "horno-tunel-001", "supervisor-hornos",
     "Cocción Horno Túnel 1 — Lote BG-2024-4818 Baguette Clásica", "running",
     {"loteId": "BG-2024-4818", "productoRef": "BAGUETTE-CLASICA-250g",
      "tempZ2C": 248, "presionVaporBar": 1.85,
      "velocidadCintaMmin": 6.8, "produccionHora": 1820,
      "colorIndice": 42, "alertas": []}),
    ("op-coccion-horno2-4817", "horno-tunel-002", "supervisor-hornos",
     "Cocción Horno Túnel 2 — Lote BR-2024-1104 Barra Rústica", "running",
     {"loteId": "BR-2024-1104", "productoRef": "BARRA-RUSTICA-300g",
      "tempZ2C": 252, "presionVaporBar": 1.9,
      "velocidadCintaMmin": 6.2, "produccionHora": 1480,
      "alertas": []}),
    ("op-coccion-rotativo1-spec", "horno-rotativo-001", "supervisor-hornos",
     "Cocción Rotativo 1 — Lote BC-2024-0312 Barra Cereales", "running",
     {"loteId": "BC-2024-0312", "productoRef": "BARRA-CEREALES-280g",
      "tempCamaraC": 245, "humedadPct": 68,
      "hornadas_turno": 18, "baguettesPorHornada": 128}),
    ("op-congelacion-iqf1-4816", "tunel-iqf-001", "supervisor-congelacion",
     "Congelación IQF Línea A — Lote BG-2024-4816 Baguette Clásica", "running",
     {"loteId": "BG-2024-4816", "tempAireC": -37.8, "tempProductoC": -19.2,
      "kgHora": 1080, "tiempoCongelacionMin": 13.5}),
    ("op-envasado-ev1-4815", "envasadora-001", "supervisor-congelacion",
     "Envasado Termoformado Línea 1 — Lote BG-2024-4815", "running",
     {"loteId": "BG-2024-4815", "formatoEnvase": "1-ud-baguette-250g",
      "pesoMedioG": 251.8, "envasesHora": 1440, "tasaRechazosPct": 0.6,
      "gasAtmModif": "N2/CO2 70/30"}),
    ("op-control-calidad-4814", "checkweigher-001", "jefe-calidad",
     "Control Calidad + Liberación Lote BG-2024-4814", "finished",
     {"loteId": "BG-2024-4814", "muestrasAnalizadas": 20,
      "resultadoPesoOK": True, "resultadoMetalesOK": True,
      "tempCentroC": -19.5, "actividadAguaAw": 0.932,
      "decisionLiberacion": "LIBERADO", "alertas": []}),
    ("op-mant-prev-horno3", "horno-tunel-003", "tecnico-mant-001",
     "Mantenimiento Preventivo PM-500h Horno Túnel 3", "running",
     {"tipoMantenimiento": "PM-500h",
      "tareasPendientes": ["limpieza quemadores", "verificacion sondas temperatura",
                           "calibracion caudalimetro vapor"],
      "horasRestantes": 3.5, "proximoPM": "PM-2000h"}),
]

OPERATIONS = []
for op_data in OP_DEFS:
    oid, machine_suffix, person_suffix, opname, opstatus, op_output = op_data
    start_offset = random.randint(30, 300)
    end_offset   = random.randint(0, 20) if opstatus == "finished" else None

    OPERATIONS.append({
        "id":               f"urn:ngsi-ld:ManufacturingMachineOperation:{oid}",
        "type":             "ManufacturingMachineOperation",
        "name":             prop(opname),
        "machine":          rel(f"urn:ngsi-ld:ManufacturingMachine:{machine_suffix}"),
        "operator":         rel(f"urn:ngsi-ld:Person:{person_suffix}"),
        "operationType":    prop(["process"]),
        "status":           prop(opstatus),
        "result":           prop("ok" if opstatus == "finished" else ""),
        "plannedStartAt":   prop(now_iso(start_offset + 60)),
        "plannedEndAt":     prop(now_iso(60)),
        "startedAt":        prop(now_iso(start_offset)),
        "endedAt":          prop(now_iso(end_offset) if end_offset is not None else ""),
        "operationOutput":  prop(op_output),
        "source":           prop("MES METAPAN — SAP PP / QM"),
        "dataProvider":     prop("https://data.metapan.es"),
    })

# ══════════════════════════════════════════════════════════════════════════════
# RESUMEN
# ══════════════════════════════════════════════════════════════════════════════
ALL_ENTITIES = (
    [BUILDING] + SPACES + MODELS + PERSONS +
    MACHINES + DEVICES + MEASUREMENTS + OPERATIONS
)
ALL_IDS = [e["id"] for e in ALL_ENTITIES]

def print_summary():
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║    METAPAN S.A. — Centro Producción Baguettes Congelados    ║
║    Polígono Industrial Carretera Málaga, Sevilla             ║
╠══════════════════════════════════════════════════════════════╣
║  Broker   : {BROKER:<48}║
║  Tenant   : {(ARGS.tenant or 'default (sin tenant)'):<48}║
╠══════════════════════════════════════════════════════════════╣
║  Building                  :   {len([BUILDING]):<5}                         ║
║  BuildingSpaces            :   {len(SPACES):<5}                         ║
║  ManufacturingMachineModels:   {len(MODELS):<5}                         ║
║  Persons                   :   {len(PERSONS):<5}                         ║
║  ManufacturingMachines     :   {len(MACHINES):<5}                         ║
║  Devices                   :   {len(DEVICES):<5}                         ║
║  DeviceMeasurements        :   {len(MEASUREMENTS):<5}                         ║
║  Operations                :   {len(OPERATIONS):<5}                         ║
╠══════════════════════════════════════════════════════════════╣
║  TOTAL ENTIDADES           :   {len(ALL_ENTITIES):<5}                         ║
╚══════════════════════════════════════════════════════════════╝
""")

# ── Carga ─────────────────────────────────────────────────────────────────────
def main_load():
    print_summary()
    if ARGS.dry_run: print("  [DRY-RUN] No se enviará nada.\n")
    batches = [
        ("Building",                        [BUILDING]),
        ("BuildingSpaces",                  SPACES),
        ("ManufacturingMachineModels",       MODELS),
        ("Persons",                         PERSONS),
        ("ManufacturingMachines",           MACHINES),
        ("Devices",                         DEVICES),
        ("DeviceMeasurements",              MEASUREMENTS),
        ("ManufacturingMachineOperations",  OPERATIONS),
    ]
    total_ok = total_err = 0
    for batch_name, entities in batches:
        print(f"\n▶  {batch_name} ({len(entities)})")
        ok = err = 0
        for e in entities:
            if post_entity(e): ok += 1; sys.stdout.write(".")
            else:              err += 1; sys.stdout.write("x")
            sys.stdout.flush()
            if ARGS.delay > 0: time.sleep(ARGS.delay)
        print(f"  → {ok} OK  /  {err} errores")
        total_ok += ok; total_err += err
    print(f"\n{'═'*60}\n  CARGA COMPLETADA  OK:{total_ok}  ERR:{total_err}\n{'═'*60}\n")

def main_delete():
    print_summary()
    print(f"  Eliminando {len(ALL_IDS)} entidades...")
    ok = err = 0
    for eid in ALL_IDS:
        if delete_entity(eid): ok += 1; sys.stdout.write(".")
        else:                   err += 1
        sys.stdout.flush()
    print(f"\n  Eliminadas: {ok}  /  No encontradas: {err}")

def main_list():
    print_summary()
    print("  IDs que se cargarian:\n")
    for i, eid in enumerate(ALL_IDS, 1): print(f"  {i:4d}.  {eid}")
    print(f"\n  Total: {len(ALL_IDS)}")

if __name__ == "__main__":
    if ARGS.delete: main_delete()
    elif ARGS.list: main_list()
    else:           main_load()