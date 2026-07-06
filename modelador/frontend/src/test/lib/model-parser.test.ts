import { describe, it, expect } from 'vitest'
import {
  parseModel,
  getTypeUri,
  getSchemaForType,
  getContextForPayload,
  buildCreateBasePayload,
  compactAttributeKeysForSchema,
  normalizeImportedEntityPayload,
  resolveSchemaTypeName,
} from '../../lib/model-parser'

// ── Fixtures ─────────────────────────────────────────────────────────────────
// Todas las funciones reciben el JSON raw (string), igual que localStorage.

const MODEL_JSON = JSON.stringify({
  schemas: [
    {
      $schema: 'https://json-schema.org/draft/2020-12/schema',
      title: 'ManufacturingMachine',
      type: 'object',
      properties: { id: { type: 'string' }, type: { type: 'string' }, name: { type: 'string' } },
    },
    {
      $schema: 'https://json-schema.org/draft/2020-12/schema',
      title: 'Area',
      type: 'object',
      properties: { id: { type: 'string' }, type: { type: 'string' } },
    },
  ],
  context: {
    '@context': {
      ManufacturingMachine: 'https://example.org/ManufacturingMachine',
      Area: 'https://example.org/Area',
    },
  },
  descriptor: null,
  examples: {},
})

// ── parseModel ────────────────────────────────────────────────────────────────

describe('parseModel', () => {
  it('returns empty result for null input', () => {
    const result = parseModel(null)
    expect(result.types).toEqual([])
    expect(result.relationships).toEqual([])
  })

  it('returns empty result for invalid JSON', () => {
    const result = parseModel('{ not valid json }')
    expect(result.types).toEqual([])
  })

  it('extracts type names from schema titles', () => {
    const result = parseModel(MODEL_JSON)
    expect(result.types).toContain('ManufacturingMachine')
    expect(result.types).toContain('Area')
  })

  it('returns relationships array (empty when no descriptor)', () => {
    const result = parseModel(MODEL_JSON)
    expect(Array.isArray(result.relationships)).toBe(true)
  })

  it('returns empty types for empty schemas array', () => {
    const result = parseModel(JSON.stringify({ schemas: [], context: null }))
    expect(result.types).toEqual([])
  })
})

// ── getTypeUri ────────────────────────────────────────────────────────────────

describe('getTypeUri', () => {
  it('returns the full IRI for a known type', () => {
    const uri = getTypeUri('ManufacturingMachine', MODEL_JSON)
    expect(uri).toBe('https://example.org/ManufacturingMachine')
  })

  it('returns the type name itself when not found in context', () => {
    const uri = getTypeUri('Unknown', MODEL_JSON)
    expect(uri).toBe('Unknown')
  })

  it('returns the type name when storedModelJson is null', () => {
    const uri = getTypeUri('Machine', null)
    expect(uri).toBe('Machine')
  })

  it('returns the type name when storedModelJson is invalid JSON', () => {
    const uri = getTypeUri('Machine', '{ invalid }')
    expect(uri).toBe('Machine')
  })
})

// ── getSchemaForType ──────────────────────────────────────────────────────────

describe('getSchemaForType', () => {
  it('returns the schema for a known type', () => {
    const schema = getSchemaForType('ManufacturingMachine', MODEL_JSON)
    expect(schema).toBeDefined()
    expect((schema as { title: string }).title).toBe('ManufacturingMachine')
  })

  it('returns null for an unknown type', () => {
    const schema = getSchemaForType('NonExistent', MODEL_JSON)
    expect(schema).toBeNull()
  })

  it('returns null when storedModelJson is null', () => {
    const schema = getSchemaForType('Machine', null)
    expect(schema).toBeNull()
  })
})

// ── getContextForPayload ──────────────────────────────────────────────────────

describe('getContextForPayload', () => {
  it('returns context from a valid model JSON', () => {
    const ctx = getContextForPayload(MODEL_JSON)
    expect(ctx).toBeDefined()
    expect(ctx).not.toBeNull()
  })

  it('returns fallback ETSI URL when storedModelJson is null', () => {
    const ctx = getContextForPayload(null)
    expect(typeof ctx === 'string' ? ctx : '').toContain('etsi.org')
  })

  it('returns fallback ETSI URL when JSON is invalid', () => {
    const ctx = getContextForPayload('{ bad json }')
    expect(typeof ctx === 'string' ? ctx : '').toContain('etsi.org')
  })
})

// ── buildCreateBasePayload ────────────────────────────────────────────────────

describe('buildCreateBasePayload', () => {
  it('returns an object with payload and fromExample', () => {
    const result = buildCreateBasePayload('ManufacturingMachine', MODEL_JSON)
    expect(result).toHaveProperty('payload')
    expect(result).toHaveProperty('fromExample')
  })

  it('payload.type is set to the requested type', () => {
    const { payload } = buildCreateBasePayload('ManufacturingMachine', MODEL_JSON)
    expect(payload.type).toBe('ManufacturingMachine')
  })

  it('payload.id follows urn:ngsi-ld pattern', () => {
    const { payload } = buildCreateBasePayload('ManufacturingMachine', MODEL_JSON)
    expect(String(payload.id)).toMatch(/^urn:ngsi-ld:/)
  })

  it('payload includes @context', () => {
    const { payload } = buildCreateBasePayload('ManufacturingMachine', MODEL_JSON)
    expect(payload['@context']).toBeDefined()
  })

  it('works when storedModelJson is null', () => {
    const { payload } = buildCreateBasePayload('Machine', null)
    expect(payload.type).toBe('Machine')
    expect(String(payload.id)).toMatch(/^urn:ngsi-ld:Machine:/)
  })
})

// ── resolveSchemaTypeName / compact / normalize (chat → editor) ───────────────

describe('resolveSchemaTypeName', () => {
  it('extrae el nombre corto desde una URI de tipo', () => {
    expect(resolveSchemaTypeName('https://smartdatamodels.org/dataModel.Building/Building')).toBe('Building')
  })
})

describe('compactAttributeKeysForSchema', () => {
  const expanded = {
    id: 'urn:ngsi-ld:Building:1',
    type: 'Building',
    'https://smartdatamodels.org/dataModel.Device/category': ['industrial'],
    'https://smartdatamodels.org/address': { addressLocality: 'Valladolid' },
  }

  it('compacta IRIs aunque no haya bloques @context del modelo', () => {
    const out = compactAttributeKeysForSchema(expanded, [], null)
    expect(out.category).toEqual(['industrial'])
    expect(out.address).toEqual({ addressLocality: 'Valladolid' })
  })
})

describe('normalizeImportedEntityPayload', () => {
  it('normaliza tipo y atributos expandidos del chat', () => {
    const raw = {
      '@context': ['https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld'],
      id: 'urn:ngsi-ld:Building:ibermot',
      type: 'https://smartdatamodels.org/dataModel.Building/Building',
      'https://smartdatamodels.org/dataModel.Device/category': ['industrial', 'manufacturingPlant'],
      'https://smartdatamodels.org/address': { postalCode: '47009' },
    }
    const out = normalizeImportedEntityPayload(raw, null)
    expect(out.type).toBe('Building')
    expect(out.category).toEqual(['industrial', 'manufacturingPlant'])
    expect(out.address).toEqual({ postalCode: '47009' })
    expect(out['@context']).toBeDefined()
  })
})
