export type SchemaGraphNode = {
  id: string
  [key: string]: unknown
}

export type SchemaGraphLink = {
  source: string | SchemaGraphNode
  target: string | SchemaGraphNode
  property?: string
  implicit?: boolean
}

export type SchemaGraphData = {
  nodes: SchemaGraphNode[]
  links: SchemaGraphLink[]
}

export type OrionGraphNode = {
  id: string
  type: string
  label: string
  [key: string]: unknown
}

export type OrionGraphLink = {
  source: string | OrionGraphNode
  target: string | OrionGraphNode
  property?: string
  implicit?: boolean
}

export type OrionGraphData = {
  nodes: OrionGraphNode[]
  links: OrionGraphLink[]
}

export type NsBadge = {
  label: string
  color: string
}

export type EntityViewAttr = {
  key: string
  short: string
  ns: NsBadge | null
  typeTag: string | null
  value: string
  display: string
}

export type EntityView = {
  id: string
  attrs: EntityViewAttr[]
}

export type SchemaTypeRelation = {
  from?: string
  to?: string
  property: string
  property_short?: string
  property_ns?: NsBadge
  implicit?: boolean
  cardinality?: string
}

export type SchemaTypeView = {
  from_rels: SchemaTypeRelation[]
  to_rels: SchemaTypeRelation[]
}
