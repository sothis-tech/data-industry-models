# Ejemplos NGSI-LD – Horno industrial E-Therm

Ejemplos de entidades para el caso de uso del horno E-Therm (cámara de ahumado y cocción). Formato **key-values** compatible con NGSI-LD.

## Estructura

| Carpeta | Entidades | Descripción |
|---------|-----------|-------------|
| `ManufacturingMachineModel/` | 1 | Modelo E-Therm (catálogo) |
| `ManufacturingMachine/` | 1 | Instancia del horno con `hasPart` |
| `ManufacturingMachineOperation/` | 1 | Ciclo de operación con `operationOutput` |
| `Building/` | 1 | Edificio donde se ubica el horno |
| `Person/` | 1 | Operador |
| `Device/` | 12 | Componentes (TC, quemador, ventiladores, generador humo) + sondas (temperatura, humedad) |
| `DeviceMeasurement/` | 7 | Una medición por sonda (temperatura producto, room 1-4, generador humo, humedad) |

## Orden de carga recomendado

1. Registrar el **contexto** (`../context/industrial-oven-context.jsonld`)
2. Crear entidades en este orden:
   - `ManufacturingMachineModel` → `Building` → `Person`
   - `Device` (todos)
   - `ManufacturingMachine`
   - `ManufacturingMachineOperation`
   - `DeviceMeasurement` (uno por cada lectura; histórico)

## Relaciones entre ejemplos

```
ManufacturingMachineModel (e-therm-001)
    ↑ machineModel
ManufacturingMachine (horno-001) ← building → Building (edificio-001)
    | hasPart
    ├── Device (tc-001, burner, fans, smoke-generator)
    ├── Device (probe-product-temp, probe-room-1..4, probe-smoke-generator, probe-humidity)
    |
    ↑ machine
ManufacturingMachineOperation (op-001) ← operator → Person (operador-001)

Device (probe-*)
    ↑ refDevice
DeviceMeasurement (7 ejemplos: producto, room 1-4, generador humo, humedad)
```

## URIs de referencia

| Entidad | URI |
|---------|-----|
| Modelo | `urn:ngsi-ld:ManufacturingMachineModel:e-therm-001` |
| Horno | `urn:ngsi-ld:ManufacturingMachine:horno-001` |
| Operación | `urn:ngsi-ld:ManufacturingMachineOperation:op-001` |
| Edificio | `urn:ngsi-ld:Building:edificio-001` |
| Operador | `urn:ngsi-ld:Person:operador-001` |
| TC | `urn:ngsi-ld:Device:tc-001` |
| Quemador | `urn:ngsi-ld:Device:burner-001` |
| Ventilador circulación | `urn:ngsi-ld:Device:fan-circulation-001` |
| Ventilador extracción | `urn:ngsi-ld:Device:fan-extraction-001` |
| Generador de humo | `urn:ngsi-ld:Device:smoke-generator-001` |
| Sonda producto | `urn:ngsi-ld:Device:probe-product-temp` |
| Sondas cámara | `urn:ngsi-ld:Device:probe-room-1` … `probe-room-4` |
| Sonda humo | `urn:ngsi-ld:Device:probe-smoke-generator` |
| Sonda humedad | `urn:ngsi-ld:Device:probe-humidity` |

## Validación

Ejecutar `python scripts/validate.py` desde la raíz del proyecto para validar todos los ejemplos contra los schemas.

- **OK:** lista de `[OK]` por archivo y `--- 24 ejemplos válidos, 0 errores ---` (exit 0).
- **Error:** líneas `[ERROR] Carpeta/archivo.json: mensaje` y resumen con número de errores (exit 1).

## Referencias

- [context/industrial-oven-context.jsonld](../context/industrial-oven-context.jsonld)
- [docs/mapa-decisiones-data-model-horno.md](../docs/mapa-decisiones-data-model-horno.md)
