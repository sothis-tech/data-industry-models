/**
 * Matching de suscripciones Orion → QuantumLeap para el grafo de instancias.
 */

export type SubscriptionFilterMode = 'all' | 'subscribed' | 'unsubscribed'

export const SUBSCRIPTION_FILTER_OPTIONS: { value: SubscriptionFilterMode; labelKey: string }[] = [
  { value: 'all', labelKey: 'entities.list.subscriptionAll' },
  { value: 'subscribed', labelKey: 'entities.list.subscriptionYes' },
  { value: 'unsubscribed', labelKey: 'entities.list.subscriptionNo' },
]

const QL_URI_HINTS = ['quantumleap', '8668', '/v2/notify', '/notify']

export function isQuantumLeapNotifyUri(uri: unknown): boolean {
  if (typeof uri !== 'string' || !uri.trim()) return false
  const u = uri.toLowerCase()
  return QL_URI_HINTS.some((h) => u.includes(h.toLowerCase()))
}

export function isSubscriptionActive(sub: Record<string, unknown>): boolean {
  if (sub.isActive === false) return false
  const status = sub.status
  if (typeof status === 'string') {
    const s = status.toLowerCase()
    if (s === 'inactive' || s === 'failed' || s === 'expired') return false
  }
  return true
}

function notificationUri(sub: Record<string, unknown>): string | null {
  const notification = sub.notification
  if (!notification || typeof notification !== 'object') return null
  const endpoint = (notification as Record<string, unknown>).endpoint
  if (!endpoint || typeof endpoint !== 'object') return null
  const uri = (endpoint as Record<string, unknown>).uri
  return typeof uri === 'string' ? uri : null
}

/** IDs exactos referenciados por la suscripción (ignora idPattern por ahora). */
export function entityIdsFromSubscription(sub: Record<string, unknown>): string[] {
  const entities = sub.entities
  if (!Array.isArray(entities)) return []
  const ids: string[] = []
  for (const e of entities) {
    if (!e || typeof e !== 'object') continue
    const id = (e as Record<string, unknown>).id
    if (typeof id === 'string' && id.trim()) ids.push(id.trim())
  }
  return ids
}

export function isQuantumLeapEntitySubscription(sub: Record<string, unknown>): boolean {
  if (!isSubscriptionActive(sub)) return false
  const uri = notificationUri(sub)
  if (!uri || !isQuantumLeapNotifyUri(uri)) return false
  return entityIdsFromSubscription(sub).length > 0
}

/** Conjunto de entity ids con ≥1 suscripción activa a QuantumLeap. */
export function subscribedEntityIdsFromSubscriptions(
  subscriptions: unknown[],
): Set<string> {
  const out = new Set<string>()
  for (const raw of subscriptions) {
    if (!raw || typeof raw !== 'object') continue
    const sub = raw as Record<string, unknown>
    if (!isQuantumLeapEntitySubscription(sub)) continue
    for (const id of entityIdsFromSubscription(sub)) out.add(id)
  }
  return out
}

export function applySubscriptionVisibilityFilter(
  nodeIds: Iterable<string>,
  subscribedIds: Set<string>,
  mode: SubscriptionFilterMode,
): Set<string> {
  if (mode === 'all') return new Set(nodeIds)
  const out = new Set<string>()
  for (const id of nodeIds) {
    const sub = subscribedIds.has(id)
    if (mode === 'subscribed' && sub) out.add(id)
    if (mode === 'unsubscribed' && !sub) out.add(id)
  }
  return out
}

/**
 * En el grafo, los nodos que no cumplen el filtro de suscripción se atenúan
 * (fantasma) en lugar de ocultarse, para conservar el contexto de vecinos.
 * Vacío si mode === 'all'.
 */
export function subscriptionGhostNodeIds(
  visibleIds: Iterable<string>,
  subscribedIds: Set<string>,
  mode: SubscriptionFilterMode,
): Set<string> {
  if (mode === 'all') return new Set()
  const primary = applySubscriptionVisibilityFilter(visibleIds, subscribedIds, mode)
  const ghosts = new Set<string>()
  for (const id of visibleIds) {
    if (!primary.has(id)) ghosts.add(id)
  }
  return ghosts
}

/** IDs de suscripciones activas a QL que observan exactamente este entity id. */
export function quantumLeapSubscriptionIdsForEntity(
  subscriptions: unknown[],
  entityId: string,
): string[] {
  if (!entityId) return []
  const ids: string[] = []
  for (const raw of subscriptions) {
    if (!raw || typeof raw !== 'object') continue
    const sub = raw as Record<string, unknown>
    if (!isQuantumLeapEntitySubscription(sub)) continue
    if (!entityIdsFromSubscription(sub).includes(entityId)) continue
    const sid = sub.id
    if (typeof sid === 'string' && sid.trim()) ids.push(sid.trim())
  }
  return ids
}

export const QUANTUMLEAP_NOTIFY_URI = 'http://quantumleap:8668/v2/notify'

/** Payload NGSI-LD de suscripción a QL (mismo shape que EntityCreate). */
export function buildQuantumLeapSubscriptionPayload(
  entityId: string,
  entityType: string,
  attributes: string[],
): Record<string, unknown> {
  const attrs = attributes.filter((a) => a && a !== 'id' && a !== 'type' && a !== '@context')
  return {
    description: `Suscripción para persistir atributos de ${entityType}`,
    type: 'Subscription',
    entities: [{ id: entityId, type: entityType }],
    watchedAttributes: attrs,
    notification: {
      attributes: attrs,
      format: 'normalized',
      endpoint: {
        uri: QUANTUMLEAP_NOTIFY_URI,
        accept: 'application/json',
      },
    },
    '@context': ['https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld'],
  }
}
