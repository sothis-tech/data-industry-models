# Referencia: paquetes ZIP y scripts de carga (IBERMOT / METAPAN)

Documento de trabajo para alinear **guías puente** del modelador con los artefactos reales. Fuentes revisadas:

- Scripts: `load_factory.py`, `load_metapan.py` (copias en `Downloads/`; origen `07_inn_espacio_de_datos/examples/factory-0x/`).
- ZIP plantilla horno: `Data Spaces/mi_modelo.zip` (46 ficheros, raíz `mi_modelo/`).

---

## Dos formas de poblar Orion


| Vía                     | Uso                                                       | Modelador                                                      |
| ----------------------- | --------------------------------------------------------- | -------------------------------------------------------------- |
| **Paquete `.zip`**      | `context/` + `schemas/` + `examples/` + `descriptor.json` | **Sí** — Configuración → cargar ZIP → modelo en `localStorage` |
| **Scripts `load_*.py`** | Generan y **POST** entidades al broker en Python          | **No** cargan el modelo en la UI; solo datos en Orion          |


---

## Scripts de carga masiva

### Ubicación y comandos


| Caso          | Script                                | Entidades (cabecera del script) |
| ------------- | ------------------------------------- | ------------------------------- |
| CU-01 IBERMOT | `examples/factory-01/load_factory.py` | **415**                         |
| CU-02 METAPAN | `examples/factory-02/load_metapan.py` | **363**                         |


```bash
# IBERMOT (Valladolid)
python load_factory.py --broker http://localhost:1026 --tenant ibermot
python load_factory.py --dry-run    # solo listar IDs
python load_factory.py --list
python load_factory.py --delete     # borrar todas las entidades del script

# METAPAN (Sevilla) — ejemplo doc usa puerto 1028
python load_metapan.py --broker http://localhost:1028 --tenant metapan
```

Parámetros comunes: `--broker`, `--tenant` (`NGSILD-Tenant`), `--delay`, `--timeout`, `--dry-run`, `--delete`, `--list`.

### Orden de lotes al cargar (ambos scripts)

Coincide con el Word de casos de uso:

1. Building
2. BuildingSpaces
3. ManufacturingMachineModels
4. Persons
5. ManufacturingMachines
6. Devices
7. DeviceMeasurements
8. ManufacturingMachineOperations

Cada entidad se envía con `POST /ngsi-ld/v1/entities` y payload `{"@context": CONTEXT, ...entity}`.

### Contexto JSON-LD que usan los scripts

Ambos resuelven el contexto así:

```text
{script_dir}/../../07INN_DATA_SPACE/context/industrial-oven-context.jsonld
```

Si no existe el fichero, caen al **contexto NGSI-LD core** de ETSI.

**Implicación:** hoy reutilizan el **mismo contexto del horno E-Therm** (`industrial-oven-context.jsonld`). Para IBERMOT/METAPAN hace falta un contexto que declare al menos `**BuildingSpace`** y los términos de relación usados en planta (`locatedIn`, `isSpaceOf`, `controlledAsset`, `worksAt`, etc.). Si `BuildingSpace` no está en el `@context`, Orion puede aceptar entidades pero el modelador y la validación pueden comportarse de forma incoherente.

### Resumen de entidades generadas

**IBERMOT** (`load_factory.py`): 1 Building, 7 BuildingSpaces, 12 modelos, 14 personas, ~40 máquinas, ~150 devices, ~150 measurements, 15 operaciones.

**METAPAN** (`load_metapan.py`): 1 Building, 9 BuildingSpaces, 12 modelos, 12 personas, ~35 máquinas, ~120 devices, ~120 measurements, 12 operaciones (con `operationOutput` orientado a panadería: `loteId`, `formula`, fermentación, cocción, APPCC).

---

## Diferencias de modelo: scripts vs `mi_modelo.zip` (E-Therm)

Los scripts **no** serializan el mismo patrón que el ZIP del horno. Si el ZIP de factory se “basó” en `mi_modelo` pero el script ya evolucionó, hay desalineación.


| Tema                       | `mi_modelo.zip` (horno)                 | `load_factory.py` / `load_metapan.py`                           |
| -------------------------- | --------------------------------------- | --------------------------------------------------------------- |
| **BuildingSpace**          | No existe                               | Sí (`type: BuildingSpace`, `isSpaceOf` → Building)              |
| Máquina → dispositivos     | `**hasPart`** (Property, lista de URIs) | `**componentes**` (Property, lista de URIs) — nombre distinto   |
| Device → máquina           | Implícito vía `hasPart` del horno       | `**controlledAsset**` (Relationship)                            |
| DeviceMeasurement → Device | `**refDevice**` (Relationship)          | `**device**` (Relationship) — distinto del SDM / horno          |
| Person                     | Solo en operación como `operator`       | `**worksAt**` → Building; `**locatedIn**` / `**worksInSpaces**` |
| Máquina → nave             | Solo `building`                         | `**building**` + `**locatedIn**` → BuildingSpace                |
| `operationOutput`          | Perfil horno (setpoint, programa)       | METAPAN: `loteId`, `formula`, `ingredientes`, etc.              |
| Contexto                   | `industrial-oven-context.jsonld`        | Misma ruta por defecto (heredado)                               |
| Volumen en Orion           | ~24 ejemplos en ZIP                     | 415 / 363 entidades solo vía script                             |


### Contenido actual de `mi_modelo.zip`

Estructura (el backend del modelador **elimina** la carpeta raíz única `mi_modelo/` al clasificar):

```text
mi_modelo/
├── context/industrial-oven-context.jsonld
├── descriptor.json          # relaciones hasPart, refDevice (horno)
├── schemas/                 # 7 tipos (sin BuildingSpace.json)
└── examples/                # 24 JSON de ejemplo
```

Tipos en schemas: Building, Device, DeviceMeasurement, ManufacturingMachine, ManufacturingMachineModel, ManufacturingMachineOperation, Person.

---

## Qué debe llevar el ZIP de IBERMOT / METAPAN (objetivo modelador)

Misma **plantilla de carpetas** que `mi_modelo`, con contenido adaptado:

```text
factory-01.zip   (o factory-02.zip)
├── context/
│   └── *-context.jsonld     # Incluir BuildingSpace y relaciones de planta
├── schemas/
│   ├── Building.json
│   ├── BuildingSpace.json   # NUEVO — tipo local
│   ├── Device.json
│   ├── ...
│   └── ManufacturingMachineOperation.json  # Perfil operationOutput por caso
├── descriptor.json          # Relaciones alineadas con datos del script (ver tabla abajo)
└── examples/                # Opcional: 1 JSON por tipo para la UI (el script no los genera)
```

### `descriptor.json` sugerido (alineado con los scripts, no con el horno)


| sourceType                    | property        | targetType                |
| ----------------------------- | --------------- | ------------------------- |
| BuildingSpace                 | isSpaceOf       | Building                  |
| ManufacturingMachine          | machineModel    | ManufacturingMachineModel |
| ManufacturingMachine          | building        | Building                  |
| ManufacturingMachine          | locatedIn       | BuildingSpace             |
| Device                        | controlledAsset | ManufacturingMachine      |
| ManufacturingMachineOperation | machine         | ManufacturingMachine      |
| ManufacturingMachineOperation | operator        | Person                    |
| DeviceMeasurement             | device          | Device                    |
| Person                        | worksAt         | Building                  |
| Person                        | locatedIn       | BuildingSpace             |


Opcional en descriptor: relación lógica máquina–dispositivo vía lista `componentes` (Property, no Relationship en NGSI-LD).

El modelador solo guarda **un ejemplo por tipo** desde `examples/`; para ver el grafo Orion completo hace falta haber ejecutado antes el script contra el mismo broker.

---

## Checklist operativo

**Solo script (demo Orion):**

- Broker accesible; tenant si aplica (`ibermot` / `metapan`).
- Contexto del proyecto en `07INN_DATA_SPACE/context/` o aceptar contexto core.
- `python load_factory.py` o `load_metapan.py` sin errores HTTP.

**Modelador (modelo en UI):**

- ZIP con `schemas/` + `context/` (+ `descriptor.json` adaptado).
- Cargar ZIP en `/` → comprobar tipos listados (debe aparecer **BuildingSpace**).
- Sesión Orion si el broker va por Kong.
- `/visualizacion` → grafo Orion (datos del script) vs grafo esquema (del ZIP).
- `/entidades` → crear/editar usando schemas del ZIP.

**Coherencia script ↔ ZIP:**

- Mismos nombres de `type` y relaciones (`device` vs `refDevice`, `componentes` vs `hasPart`).
- Contexto incluye todos los tipos y propiedades que el script escribe.

---

## Pendiente / siguientes pasos

1. Publicar en repo o OneDrive los ZIP definitivos `factory-01` y `factory-02` (hoy solo está claro `mi_modelo.zip` del horno).
2. Generar `context` + `schemas/BuildingSpace.json` + `descriptor.json` por caso (no reutilizar el del horno sin cambios).
3. Decidir si `DeviceMeasurement` en ZIP/schemas usa `**refDevice`** (SDM) o `**device**` (como los scripts) y alinear script o modelo.
4. Redactar `CU-01-ibermot.md` y `CU-02-metapan.md` con URL de broker de prueba y capturas del modelador.

Copias locales de los scripts (referencia):  
`C:\Users\monica.montero\Downloads\load_factory.py`, `load_metapan.py`.