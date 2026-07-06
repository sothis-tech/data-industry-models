export type NgsiModel = {
  schemas: unknown[]
  context: unknown
  descriptor: unknown
  examples: Record<string, unknown>
  schemaUrls: string[]
  contextUrl: string | null
  descriptorUrl: string | null
  exampleUrls: string[]
  packageName?: string
}
