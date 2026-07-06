# Contexto JSON-LD – Horno industrial E-Therm

Contexto para entidades NGSI-LD del caso de uso E-Therm. Compatible con brokers NGSI-LD (Orion-LD, Scorpio, etc.).

## Archivo

**industrial-oven-context.jsonld** — Incluye:

- Referencia al core context NGSI-LD
- Tipos: ManufacturingMachine, ManufacturingMachineModel, ManufacturingMachineOperation, Device, DeviceMeasurement, Building, Person, Organization
- Extensión: `hasPart` (schema.org) para ManufacturingMachine
- Mapeo de atributos estándar de los modelos referenciados

## Uso

Registrar el contexto en el broker antes de crear entidades, o incluir el `@context` en cada petición de creación/actualización.

Ejemplo con curl (Orion-LD):

```bash
curl -X POST http://localhost:1026/ngsi-ld/v1/jsonldContexts \
  -H "Content-Type: application/json" \
  -d @industrial-oven-context.jsonld
```

## Referencias

- [docs/extensions.md](../docs/extensions.md) — Extensiones documentadas
- [REFERENCES.md](../REFERENCES.md) — Modelos oficiales
