export type NgsiLdEntity = {
  id: string
  type: string
  '@context'?: unknown
  name?: { value?: string } | string
  [key: string]: unknown
}

export type ValidationError = {
  path: string
  message: string
}

export type ValidationResult = {
  valid: boolean
  errors: ValidationError[]
}

export type PreparePayloadResult = {
  error: string | null
  inputMode: 'plain' | 'normalized'
  payloadForValidation: Record<string, unknown>
  payloadToSend: Record<string, unknown>
}

export type PrepareAttrsResult = {
  error: string | null
  attrsPayloadToSend: Record<string, unknown>
}
