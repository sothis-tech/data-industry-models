# Schemas – Industrial Oven

Schemas JSON para validación de entidades del espacio de datos local. Siguen las directrices de Smart Data Models: **extender sin modificar** los modelos base.

## Enfoque

- **Extender (allOf + $ref):** ManufacturingMachine, ManufacturingMachineOperation → añaden solo atributos nuevos.
- **Sin modificar ($ref directo):** ManufacturingMachineModel, Device, DeviceMeasurement, Building → usan el schema oficial tal cual.
- **Person:** no existe en Smart Data Models; se usa un schema mínimo basado en Schema.org.

## Entidades

| Schema | Entidad | Enfoque |
|--------|---------|---------|
| ManufacturingMachine.json | ManufacturingMachine | Extiende: añade `hasPart` |
| ManufacturingMachineModel.json | ManufacturingMachineModel | $ref oficial (valores standardOperations en [extensions.md](../docs/extensions.md)) |
| ManufacturingMachineOperation.json | ManufacturingMachineOperation | Extiende: `operationOutput` con perfil E-Therm |
| Device.json | Device | $ref oficial |
| DeviceMeasurement.json | DeviceMeasurement | $ref oficial |
| Building.json | Building | $ref oficial |
| Person.json | Person | Schema local (Schema.org/Person) |

## Validación

```bash
pip install -r requirements.txt
python scripts/validate.py
```

El script valida todos los ejemplos contra sus schemas correspondientes. Los schemas con `$ref` a URLs remotas se resuelven automáticamente.

**Salida cuando todo está OK:**
```
Validando ejemplos contra schemas...

  [OK] Building/example.json
  [OK] Device/example-burner.json
  ...
  [OK] Person/example.json

--- 24 ejemplos válidos, 0 errores ---
```
(exit code 0)

**Salida cuando hay errores:**
```
Validando ejemplos contra schemas...

  [OK] Building/example.json
  [ERROR] Device/example-burner.json: 'controlledProperty' is a required property
  [OK] Device/example-fan-circulation.json
  ...

--- 23 ejemplos válidos, 1 errores ---
```
(exit code 1)

## Device – campos obligatorios y enums

El schema oficial Device requiere `controlledProperty` (obligatorio) y define enums para `category` y `controlledProperty`. Ver [docs/mapa-decisiones-data-model-horno.md](../docs/mapa-decisiones-data-model-horno.md) para los valores usados en este proyecto.

## Referencias

- [REFERENCES.md](../REFERENCES.md) – Modelos oficiales
- [docs/extensions.md](../docs/extensions.md) – Extensiones documentadas
