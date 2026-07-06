import { describe, expect, it } from 'vitest'
import { isOrionAuthFailure } from '../../lib/orionSessionEvents'

describe('isOrionAuthFailure', () => {
  it('detecta error_code del proxy BFF', () => {
    expect(isOrionAuthFailure(401, { error_code: 'orion_token_expired' }, null)).toBe(true)
    expect(isOrionAuthFailure(401, { error_code: 'orion_auth_required' }, 'Sesión requerida')).toBe(true)
  })

  it('detecta mensajes de sesión en error o detail', () => {
    expect(isOrionAuthFailure(401, {}, 'Sesión Orion expirada; vuelve a conectar.')).toBe(true)
    expect(isOrionAuthFailure(401, { detail: 'Chat bloqueado hasta iniciar sesión en Orion.' }, null)).toBe(true)
  })

  it('ignora otros códigos HTTP', () => {
    expect(isOrionAuthFailure(403, { error_code: 'orion_token_expired' }, null)).toBe(false)
    expect(isOrionAuthFailure(500, {}, 'Sesión Orion expirada')).toBe(false)
  })
})
