import type { StoredBroker } from '../types/broker'

export type { StoredBroker }

const BROKERS_KEY = 'ngsi_brokers'
const CURRENT_BROKER_URL_KEY = 'ngsi_current_broker_url'
const CURRENT_BROKER_NAME_KEY = 'ngsi_current_broker_name'
const CURRENT_BROKER_TENANT_KEY = 'ngsi_current_broker_tenant'

export function getStoredBrokers(): StoredBroker[] {
  try {
    const raw = localStorage.getItem(BROKERS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as StoredBroker[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function setStoredBrokers(brokers: StoredBroker[]): void {
  localStorage.setItem(BROKERS_KEY, JSON.stringify(brokers))
}

export function getCurrentBroker(): StoredBroker | null {
  const url = localStorage.getItem(CURRENT_BROKER_URL_KEY)
  const name = localStorage.getItem(CURRENT_BROKER_NAME_KEY)
  const tenant = localStorage.getItem(CURRENT_BROKER_TENANT_KEY) ?? undefined
  return url ? { name: name || url, url, tenant } : null
}

export function setCurrentBroker(name: string, url: string, tenant?: string): void {
  if (!url) return
  localStorage.setItem(CURRENT_BROKER_URL_KEY, url)
  localStorage.setItem(CURRENT_BROKER_NAME_KEY, name || url)
  if (tenant) {
    localStorage.setItem(CURRENT_BROKER_TENANT_KEY, tenant)
  } else {
    localStorage.removeItem(CURRENT_BROKER_TENANT_KEY)
  }
}

export function clearCurrentBroker(): void {
  localStorage.removeItem(CURRENT_BROKER_URL_KEY)
  localStorage.removeItem(CURRENT_BROKER_NAME_KEY)
  localStorage.removeItem(CURRENT_BROKER_TENANT_KEY)
}
