/** Eventos desacoplados entre el panel Marvin y las páginas del modelador. */

export const AGENT_APPLY_ENTITY = 'modelador:agent-apply-entity'
export const AGENT_OPEN_ENTITY = 'modelador:agent-open-entity'
export const AGENT_OPEN_VIZ_ENTITY = 'modelador:agent-open-viz-entity'

export type AgentApplyEntityDetail = {
  payload: Record<string, unknown>
  mode?: 'create' | 'edit'
  entityId?: string
}

export type AgentOpenEntityDetail = {
  entityId: string
}

export type AgentOpenVizEntityDetail = {
  entityId: string
}

export function dispatchAgentApplyEntity(detail: AgentApplyEntityDetail): void {
  window.dispatchEvent(new CustomEvent(AGENT_APPLY_ENTITY, { detail }))
}

export function dispatchAgentOpenEntity(detail: AgentOpenEntityDetail): void {
  window.dispatchEvent(new CustomEvent(AGENT_OPEN_ENTITY, { detail }))
}

export function dispatchAgentOpenVizEntity(detail: AgentOpenVizEntityDetail): void {
  window.dispatchEvent(new CustomEvent(AGENT_OPEN_VIZ_ENTITY, { detail }))
}
