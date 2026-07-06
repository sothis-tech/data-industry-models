/** Navegación desde Marvin / Entidades hacia Visualización (foco en instancia Orion). */

export const VIZ_FOCUS_ENTITY_KEY = 'viz_focus_entity_id'

export function setVizFocusEntityId(entityId: string): void {
  sessionStorage.setItem(VIZ_FOCUS_ENTITY_KEY, entityId)
}

/** Lee y borra el id pendiente (una sola consumición al montar Visualización). */
export function consumeVizFocusEntityId(): string | null {
  const id = sessionStorage.getItem(VIZ_FOCUS_ENTITY_KEY)
  if (id) sessionStorage.removeItem(VIZ_FOCUS_ENTITY_KEY)
  return id?.trim() || null
}
