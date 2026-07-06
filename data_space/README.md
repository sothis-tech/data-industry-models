# Espacio de datos – Horno industrial E-Therm

Implementación del modelo de datos para la cámara de ahumado y cocción E-Therm (Emerson Technik) en un espacio de datos interoperable, basado en **Smart Data Models**.

## Contenido

| Carpeta | Descripción |
|---------|-------------|
| `docs/` | Documentación: decisiones de diseño, extensión, sensores |
| `context/` | Contexto JSON-LD para NGSI-LD |
| `schemas/` | Schemas JSON para validación (extienden modelos oficiales) |
| `examples/` | Ejemplos de entidades en formato key-values |
| `scripts/` | Script de validación de ejemplos |
| `docker/` | Instrucciones para broker Orion-LD con Docker Compose |

## Modelo de datos

- **Reutilización:** ManufacturingMachineModel, ManufacturingMachine, ManufacturingMachineOperation, Building, Person, Device, DeviceMeasurement
- **Extensiones (local):** `hasPart` en ManufacturingMachine, perfil de `operationOutput` en ManufacturingMachineOperation
- **Sensores:** Device + DeviceMeasurement para temperatura y humedad (histórico por lectura)
- **Enfoque:** Extender sin modificar; schemas referencian URLs oficiales con `$ref` y `allOf`

## Uso rápido

1. **Contexto:** Usar `context/industrial-oven-context.jsonld` al provisionar entidades en un broker NGSI-LD (Orion-LD, Scorpio, etc.).

2. **Validación:** Ejecutar `python scripts/validate.py` para validar todos los ejemplos contra los schemas (requiere `pip install -r requirements.txt`).

   - **Cuando todo está OK:** lista de `[OK]` por cada archivo y resumen `--- 24 ejemplos válidos, 0 errores ---` (exit code 0).
   - **Cuando falla:** líneas `[ERROR] Carpeta/archivo.json: mensaje del error` y resumen `--- N ejemplos válidos, M errores ---` (exit code 1).

3. **Ejemplos:** Los JSON en `examples/` pueden cargarse directamente. Ver orden recomendado en `examples/README.md`.

4. **Broker local (Docker):** Ejecutar `docker compose up -d` para levantar Orion-LD en http://localhost:1026. Ver [docker/README.md](docker/README.md).

## Documentación

| Documento | Descripción |
|-----------|-------------|
| [docs/mapa-decisiones-data-model-horno.md](docs/mapa-decisiones-data-model-horno.md) | Especificación formal: entidades, relaciones, esquemas |
| [docs/data-model-horno-industrial.md](docs/data-model-horno-industrial.md) | Modelo detallado, sensores según manual, decisiones de diseño |
| [docs/extensions.md](docs/extensions.md) | Extensiones aplicadas (hasPart, operationOutput, standardOperations) |
| [docs/guardrails-requisitos.md](docs/guardrails-requisitos.md) | Gobernanza del espacio de datos: requisitos de seguridad, alertas y criterios de aceptación (alineado con IDSA Rulebook) |
| [docs/guia-integracion-llm.md](docs/guia-integracion-llm.md) | **Guía para el desarrollador del LLM/agente:** cómo conectarse al broker Orion, usar el contexto y buenas prácticas |
| [REFERENCES.md](REFERENCES.md) | Enlaces a modelos oficiales de Smart Data Models |
