import { describe, expect, it } from 'vitest'
import {
  applySubscriptionVisibilityFilter,
  buildQuantumLeapSubscriptionPayload,
  isQuantumLeapEntitySubscription,
  isQuantumLeapNotifyUri,
  quantumLeapSubscriptionIdsForEntity,
  subscribedEntityIdsFromSubscriptions,
  subscriptionGhostNodeIds,
} from '../../lib/subscriptions'

const QL_SUB = {
  id: 'urn:ngsi-ld:Subscription:1',
  status: 'active',
  entities: [{ id: 'urn:ngsi-ld:Device:001', type: 'Device' }],
  notification: {
    endpoint: { uri: 'http://quantumleap:8668/v2/notify', accept: 'application/json' },
  },
}

describe('subscriptions matching', () => {
  it('detecta URI de QuantumLeap', () => {
    expect(isQuantumLeapNotifyUri('http://quantumleap:8668/v2/notify')).toBe(true)
    expect(isQuantumLeapNotifyUri('http://other:9000/hook')).toBe(false)
  })

  it('acepta suscripción activa a QL con entity id', () => {
    expect(isQuantumLeapEntitySubscription(QL_SUB)).toBe(true)
  })

  it('rechaza suscripción inactive', () => {
    expect(isQuantumLeapEntitySubscription({ ...QL_SUB, status: 'inactive' })).toBe(false)
  })

  it('rechaza endpoint que no es QL', () => {
    expect(
      isQuantumLeapEntitySubscription({
        ...QL_SUB,
        notification: { endpoint: { uri: 'http://example.org/hook' } },
      }),
    ).toBe(false)
  })

  it('agrega ids suscritos (unión de varias subs)', () => {
    const ids = subscribedEntityIdsFromSubscriptions([
      QL_SUB,
      {
        ...QL_SUB,
        id: 'urn:ngsi-ld:Subscription:2',
        entities: [{ id: 'urn:ngsi-ld:Building:1', type: 'Building' }],
      },
      { status: 'inactive', entities: [{ id: 'urn:ngsi-ld:Device:999' }], notification: QL_SUB.notification },
    ])
    expect([...ids].sort()).toEqual([
      'urn:ngsi-ld:Building:1',
      'urn:ngsi-ld:Device:001',
    ])
  })

  it('filtra visibilidad por modo', () => {
    const subscribed = new Set(['a', 'b'])
    const all = ['a', 'b', 'c']
    expect([...applySubscriptionVisibilityFilter(all, subscribed, 'all')].sort()).toEqual(['a', 'b', 'c'])
    expect([...applySubscriptionVisibilityFilter(all, subscribed, 'subscribed')].sort()).toEqual(['a', 'b'])
    expect([...applySubscriptionVisibilityFilter(all, subscribed, 'unsubscribed')].sort()).toEqual(['c'])
  })

  it('calcula nodos fantasma (visibles que no cumplen el filtro)', () => {
    const subscribed = new Set(['a', 'b'])
    const all = ['a', 'b', 'c']
    expect([...subscriptionGhostNodeIds(all, subscribed, 'all')]).toEqual([])
    expect([...subscriptionGhostNodeIds(all, subscribed, 'subscribed')].sort()).toEqual(['c'])
    expect([...subscriptionGhostNodeIds(all, subscribed, 'unsubscribed')].sort()).toEqual(['a', 'b'])
  })

  it('devuelve ids de suscripción QL para una entidad', () => {
    const ids = quantumLeapSubscriptionIdsForEntity(
      [
        QL_SUB,
        {
          ...QL_SUB,
          id: 'urn:ngsi-ld:Subscription:2',
          entities: [{ id: 'urn:ngsi-ld:Device:001', type: 'Device' }],
        },
        {
          ...QL_SUB,
          id: 'urn:ngsi-ld:Subscription:other',
          entities: [{ id: 'urn:ngsi-ld:Building:1', type: 'Building' }],
        },
      ],
      'urn:ngsi-ld:Device:001',
    )
    expect(ids.sort()).toEqual([
      'urn:ngsi-ld:Subscription:1',
      'urn:ngsi-ld:Subscription:2',
    ])
  })

  it('construye payload de suscripción a QL', () => {
    const payload = buildQuantumLeapSubscriptionPayload(
      'urn:ngsi-ld:Device:001',
      'Device',
      ['temp', 'id', 'type', '@context'],
    )
    expect(payload.entities).toEqual([{ id: 'urn:ngsi-ld:Device:001', type: 'Device' }])
    expect(payload.watchedAttributes).toEqual(['temp'])
    expect((payload.notification as { endpoint: { uri: string } }).endpoint.uri).toContain('quantumleap')
  })
})
