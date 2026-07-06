#!/usr/bin/env python3
"""
Borra todas las entidades del horno y las recarga con contexto INLINE simplificado.
Esto hace que Orion guarde los tipos y atributos con nombres CORTOS (sin URIs largas),
lo que permite queries simples como type=DeviceMeasurement, q=numValue>70, etc.

Ejecutar desde: ~/proyectos/proyectos/07INN_DATA_SPACE
  python3 reload_clean.py
"""
import json, urllib.request, urllib.error, urllib.parse, sys

BROKER = "http://localhost:1026"
NGSI   = f"{BROKER}/ngsi-ld/v1"

# Contexto INLINE simplificado — solo el core NGSI-LD.
# Al no incluir el contexto externo de smartdatamodels, Orion guarda
# los nombres tal cual (nombres cortos), sin expandir a URIs largas.
CONTEXT = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"

GREEN, RED, YELLOW, NC = "\033[92m", "\033[91m", "\033[93m", "\033[0m"

def req(method, path, body=None, params=None):
    url = f"{NGSI}{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k:v for k,v in params.items() if v})
    data = json.dumps(body).encode() if body else None
    headers = {"Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/ld+json"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try: return e.code, json.loads(raw)
        except: return e.code, raw
    except Exception as ex:
        return 0, str(ex)

def delete_entity(eid):
    enc = urllib.parse.quote(eid, safe="")
    s, _ = req("DELETE", f"/entities/{enc}")
    return s in (204, 404)

def post_entity(entity):
    payload = {"@context": CONTEXT, **entity}
    s, b = req("POST", "/entities", body=payload)
    if s == 201:
        print(f"  {GREEN}✅ {entity['id'].split(':')[-1]} ({entity['type']}){NC}")
        return True
    elif s == 409:
        # Ya existe — hacer PATCH
        eid = entity["id"]
        attrs = {k:v for k,v in entity.items() if k not in ("id","type")}
        payload2 = {"@context": CONTEXT, **attrs}
        enc = urllib.parse.quote(eid, safe="")
        s2, b2 = req("PATCH", f"/entities/{enc}/attrs", body=payload2)
        if s2 == 204:
            print(f"  {YELLOW}⚠️  actualizada: {eid.split(':')[-1]}{NC}")
            return True
        print(f"  {RED}❌ PATCH {s2}: {b2}{NC}")
        return False
    else:
        print(f"  {RED}❌ HTTP {s}: {b}{NC}")
        return False

# ── Todas las entidades en formato limpio (sin contexto externo) ─────────────

ENTITIES = [

  # ── ManufacturingMachineModel ─────────────────────────────────────────────
  {"id":"urn:ngsi-ld:ManufacturingMachineModel:e-therm-001",
   "type":"ManufacturingMachineModel",
   "name":{"type":"Property","value":"E-Therm Smoking & Cooking Chamber"},
   "description":{"type":"Property","value":"Cámara de ahumado y cocción E-Therm"},
   "manufacturerName":{"type":"Property","value":"Emerson Technik"},
   "brandName":{"type":"Property","value":"E-Therm"},
   "manufacturingMachineType":{"type":"Property","value":["oven"]},
   "standardOperations":{"type":"Property","value":["smoking","cooking","drying","maturing"]},
  },

  # ── Building ──────────────────────────────────────────────────────────────
  {"id":"urn:ngsi-ld:Building:edificio-001",
   "type":"Building",
   "name":{"type":"Property","value":"Nave de procesado - Planta 1"},
   "category":{"type":"Property","value":["industrial"]},
   "address":{"type":"Property","value":{"addressLocality":"Madrid","addressCountry":"ES","streetAddress":"Polígono Industrial, Nave 2"}},
   "location":{"type":"GeoProperty","value":{"type":"Point","coordinates":[-3.7038,40.4168]}},
  },

  # ── Person ────────────────────────────────────────────────────────────────
  {"id":"urn:ngsi-ld:Person:operador-001",
   "type":"Person",
   "name":{"type":"Property","value":"Operador turno mañana"},
  },

  # ── Devices ───────────────────────────────────────────────────────────────
  {"id":"urn:ngsi-ld:Device:tc-001","type":"Device",
   "name":{"type":"Property","value":"Touch-Control TC"},
   "category":{"type":"Property","value":["controller"]},
   "controlledProperty":{"type":"Property","value":["power"]},
  },
  {"id":"urn:ngsi-ld:Device:burner-001","type":"Device",
   "name":{"type":"Property","value":"Quemador"},
   "category":{"type":"Property","value":["actuator"]},
   "controlledProperty":{"type":"Property","value":["temperature"]},
  },
  {"id":"urn:ngsi-ld:Device:fan-circulation-001","type":"Device",
   "name":{"type":"Property","value":"Ventilador de Circulación"},
   "category":{"type":"Property","value":["actuator"]},
   "controlledProperty":{"type":"Property","value":["speed"]},
  },
  {"id":"urn:ngsi-ld:Device:fan-extraction-001","type":"Device",
   "name":{"type":"Property","value":"Ventilador de Extracción"},
   "category":{"type":"Property","value":["actuator"]},
   "controlledProperty":{"type":"Property","value":["speed"]},
  },
  {"id":"urn:ngsi-ld:Device:smoke-generator-001","type":"Device",
   "name":{"type":"Property","value":"Generador de Humo"},
   "category":{"type":"Property","value":["actuator"]},
   "controlledProperty":{"type":"Property","value":["smoke"]},
  },
  {"id":"urn:ngsi-ld:Device:probe-product-temp","type":"Device",
   "name":{"type":"Property","value":"Sonda Temperatura Producto"},
   "category":{"type":"Property","value":["sensor"]},
   "controlledProperty":{"type":"Property","value":["temperature"]},
  },
  {"id":"urn:ngsi-ld:Device:probe-room-1","type":"Device",
   "name":{"type":"Property","value":"Sonda Temperatura Cámara 1"},
   "category":{"type":"Property","value":["sensor"]},
   "controlledProperty":{"type":"Property","value":["temperature"]},
  },
  {"id":"urn:ngsi-ld:Device:probe-room-2","type":"Device",
   "name":{"type":"Property","value":"Sonda Temperatura Cámara 2"},
   "category":{"type":"Property","value":["sensor"]},
   "controlledProperty":{"type":"Property","value":["temperature"]},
  },
  {"id":"urn:ngsi-ld:Device:probe-room-3","type":"Device",
   "name":{"type":"Property","value":"Sonda Temperatura Cámara 3"},
   "category":{"type":"Property","value":["sensor"]},
   "controlledProperty":{"type":"Property","value":["temperature"]},
  },
  {"id":"urn:ngsi-ld:Device:probe-room-4","type":"Device",
   "name":{"type":"Property","value":"Sonda Temperatura Cámara 4"},
   "category":{"type":"Property","value":["sensor"]},
   "controlledProperty":{"type":"Property","value":["temperature"]},
  },
  {"id":"urn:ngsi-ld:Device:probe-smoke-generator","type":"Device",
   "name":{"type":"Property","value":"Sonda Temperatura Generador de Humo"},
   "category":{"type":"Property","value":["sensor"]},
   "controlledProperty":{"type":"Property","value":["temperature"]},
  },
  {"id":"urn:ngsi-ld:Device:probe-humidity","type":"Device",
   "name":{"type":"Property","value":"Sonda de Humedad Psicométrica"},
   "category":{"type":"Property","value":["sensor"]},
   "controlledProperty":{"type":"Property","value":["relativeHumidity"]},
  },

  # ── ManufacturingMachine ──────────────────────────────────────────────────
  {"id":"urn:ngsi-ld:ManufacturingMachine:horno-001",
   "type":"ManufacturingMachine",
   "name":{"type":"Property","value":"Horno E-Therm Línea 1"},
   "description":{"type":"Property","value":"Cámara de ahumado y cocción E-Therm instalada en línea 1."},
   "serialNumber":{"type":"Property","value":"ET-2024-001"},
   "status":{"type":"Property","value":"running"},
   "online":{"type":"Property","value":True},
   "power":{"type":"Property","value":45},
   "voltage":{"type":"Property","value":400},
   "machineModel":{"type":"Relationship","object":"urn:ngsi-ld:ManufacturingMachineModel:e-therm-001"},
   "building":{"type":"Relationship","object":"urn:ngsi-ld:Building:edificio-001"},
   "location":{"type":"GeoProperty","value":{"type":"Point","coordinates":[-3.7038,40.4168]}},
   "address":{"type":"Property","value":{"addressLocality":"Madrid","addressCountry":"ES","streetAddress":"Nave 2, Planta 1"}},
   "installedAt":{"type":"Property","value":"2024-01-15T00:00:00Z"},
   "supplierName":{"type":"Property","value":"Emerson Technik"},
   "componentes":{"type":"Property","value":[
     "urn:ngsi-ld:Device:tc-001","urn:ngsi-ld:Device:burner-001",
     "urn:ngsi-ld:Device:fan-circulation-001","urn:ngsi-ld:Device:fan-extraction-001",
     "urn:ngsi-ld:Device:smoke-generator-001","urn:ngsi-ld:Device:probe-product-temp",
     "urn:ngsi-ld:Device:probe-room-1","urn:ngsi-ld:Device:probe-room-2",
     "urn:ngsi-ld:Device:probe-room-3","urn:ngsi-ld:Device:probe-room-4",
     "urn:ngsi-ld:Device:probe-smoke-generator","urn:ngsi-ld:Device:probe-humidity",
   ]},
  },

  # ── ManufacturingMachineOperation ─────────────────────────────────────────
  {"id":"urn:ngsi-ld:ManufacturingMachineOperation:op-001",
   "type":"ManufacturingMachineOperation",
   "machine":{"type":"Relationship","object":"urn:ngsi-ld:ManufacturingMachine:horno-001"},
   "operationType":{"type":"Property","value":["process"]},
   "status":{"type":"Property","value":"finished"},
   "result":{"type":"Property","value":"ok"},
   "plannedStartAt":{"type":"Property","value":"2024-02-10T08:00:00Z"},
   "plannedEndAt":{"type":"Property","value":"2024-02-10T14:00:00Z"},
   "startedAt":{"type":"Property","value":"2024-02-10T08:05:00Z"},
   "endedAt":{"type":"Property","value":"2024-02-10T13:58:00Z"},
   "operator":{"type":"Relationship","object":"urn:ngsi-ld:Person:operador-001"},
   "operationOutput":{"type":"Property","value":{
     "programName":"Programa 15","programId":"15",
     "temperatureSetPoint":72,"temperatureMin":68,"temperatureMax":75,
     "humiditySetPoint":65,"humidityMin":60,"humidityMax":70,
     "controlMode":"ProductTemperature","rhControl":True,
     "processSteps":["smoking","cooking","drying"],
     "durationMinutes":353,"alarms":[],
   }},
  },

  # ── DeviceMeasurements ────────────────────────────────────────────────────
  {"id":"urn:ngsi-ld:DeviceMeasurement:meas-room1-001","type":"DeviceMeasurement",
   "refDevice":{"type":"Relationship","object":"urn:ngsi-ld:Device:probe-room-1"},
   "numValue":{"type":"Property","value":74.2},
   "controlledProperty":{"type":"Property","value":"temperature"},
   "unit":{"type":"Property","value":"CEL"},
   "dateObserved":{"type":"Property","value":"2024-02-10T12:30:00Z"},
  },
  {"id":"urn:ngsi-ld:DeviceMeasurement:meas-room2-001","type":"DeviceMeasurement",
   "refDevice":{"type":"Relationship","object":"urn:ngsi-ld:Device:probe-room-2"},
   "numValue":{"type":"Property","value":73.8},
   "controlledProperty":{"type":"Property","value":"temperature"},
   "unit":{"type":"Property","value":"CEL"},
   "dateObserved":{"type":"Property","value":"2024-02-10T12:30:00Z"},
  },
  {"id":"urn:ngsi-ld:DeviceMeasurement:meas-room3-001","type":"DeviceMeasurement",
   "refDevice":{"type":"Relationship","object":"urn:ngsi-ld:Device:probe-room-3"},
   "numValue":{"type":"Property","value":74.0},
   "controlledProperty":{"type":"Property","value":"temperature"},
   "unit":{"type":"Property","value":"CEL"},
   "dateObserved":{"type":"Property","value":"2024-02-10T12:30:00Z"},
  },
  {"id":"urn:ngsi-ld:DeviceMeasurement:meas-room4-001","type":"DeviceMeasurement",
   "refDevice":{"type":"Relationship","object":"urn:ngsi-ld:Device:probe-room-4"},
   "numValue":{"type":"Property","value":73.5},
   "controlledProperty":{"type":"Property","value":"temperature"},
   "unit":{"type":"Property","value":"CEL"},
   "dateObserved":{"type":"Property","value":"2024-02-10T12:30:00Z"},
  },
  {"id":"urn:ngsi-ld:DeviceMeasurement:meas-temp-001","type":"DeviceMeasurement",
   "refDevice":{"type":"Relationship","object":"urn:ngsi-ld:Device:probe-product-temp"},
   "numValue":{"type":"Property","value":71.5},
   "controlledProperty":{"type":"Property","value":"temperature"},
   "unit":{"type":"Property","value":"CEL"},
   "dateObserved":{"type":"Property","value":"2024-02-10T12:30:00Z"},
  },
  {"id":"urn:ngsi-ld:DeviceMeasurement:meas-smoke-001","type":"DeviceMeasurement",
   "refDevice":{"type":"Relationship","object":"urn:ngsi-ld:Device:probe-smoke-generator"},
   "numValue":{"type":"Property","value":155.0},
   "controlledProperty":{"type":"Property","value":"temperature"},
   "unit":{"type":"Property","value":"CEL"},
   "dateObserved":{"type":"Property","value":"2024-02-10T12:30:00Z"},
  },
  {"id":"urn:ngsi-ld:DeviceMeasurement:meas-hum-001","type":"DeviceMeasurement",
   "refDevice":{"type":"Relationship","object":"urn:ngsi-ld:Device:probe-humidity"},
   "numValue":{"type":"Property","value":65.0},
   "controlledProperty":{"type":"Property","value":"relativeHumidity"},
   "unit":{"type":"Property","value":"P1"},
   "dateObserved":{"type":"Property","value":"2024-02-10T12:30:00Z"},
  },
]

ALL_IDS = [e["id"] for e in ENTITIES]

def main():
    print("=" * 55)
    print("  Recarga limpia del modelo de datos E-Therm")
    print(f"  Broker: {BROKER}")
    print("=" * 55)

    # Paso 1: borrar entidades existentes
    print("\n── Paso 1: Limpiando entidades anteriores ────────────")
    deleted = sum(1 for eid in ALL_IDS if delete_entity(eid))
    print(f"  {deleted} entidades eliminadas/no existían")

    # Paso 2: crear en orden correcto
    print("\n── Paso 2: Creando entidades ─────────────────────────")
    ok = sum(post_entity(e) for e in ENTITIES)

    # Paso 3: verificar
    print("\n── Paso 3: Verificación rápida ───────────────────────")
    for type_name in ["DeviceMeasurement", "Device", "ManufacturingMachine", "ManufacturingMachineOperation"]:
        s, b = req("GET", "/entities", params={"type": type_name, "options": "keyValues", "limit": 20})
        count = len(b) if isinstance(b, list) else 0
        icon = GREEN+"✅"+NC if count > 0 else RED+"❌"+NC
        print(f"  {icon} {type_name}: {count} entidades")

    print(f"\n{'=' * 55}")
    print(f"  Total: {ok}/{len(ENTITIES)} entidades cargadas")
    print("=" * 55)
    if ok == len(ENTITIES):
        print(f"\n{GREEN}🎉 Listo. Pregunta al agente:{NC}")
        print("   '¿qué temperatura hay en el horno?'")
        print("   '¿cuál es el estado del horno?'")
        print("   '¿qué hay en Orion?'")

if __name__ == "__main__":
    main()
