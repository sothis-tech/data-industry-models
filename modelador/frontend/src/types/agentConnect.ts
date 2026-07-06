export type AgentConnectServiceStatus = {
  status: string
  types?: number
  total_entities?: number
  documents?: number
  total_chunks?: number
}

export type AgentConnectResult = {
  status: string
  tenant: string
  orion?: AgentConnectServiceStatus
  rag?: AgentConnectServiceStatus
  quantumleap?: AgentConnectServiceStatus
}
