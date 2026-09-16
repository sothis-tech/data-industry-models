# Suscripciones QL en EntityEdit (fase 2A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** En editar entidad, checkbox “Notificar a QuantumLeap” que crea (POST) o borra (DELETE) suscripciones a QL según el estado al guardar.

**Architecture:** Reutilizar matching de `lib/subscriptions.ts`; nuevo helper para IDs de sub por entidad y builder de payload; proxy DELETE en backend; `EntityEdit` carga estado inicial con GET y sincroniza tras PATCH exitoso.

**Tech Stack:** FastAPI proxy, React + Vitest, Orion NGSI-LD subscriptions.

---

## Files

| File | Role |
|---|---|
| `modelador/backend/main.py` | `DELETE /api/proxy/subscriptions/{id}` |
| `modelador/backend/tests/test_proxy.py` | Validación broker_base_url |
| `modelador/frontend/src/api/orion.ts` | `deleteSubscription` |
| `modelador/frontend/src/lib/subscriptions.ts` | Helpers: IDs de sub QL por entity + build payload |
| `modelador/frontend/src/pages/entities/EntityEdit.tsx` | Checkbox + sync al guardar |
| `modelador/frontend/src/test/lib/subscriptions.test.ts` | Tests helpers |
| `modelador/frontend/src/test/components/EntityEdit.test.tsx` | Tests checkbox / sync |

### Task 1: Helpers + tests

- [ ] Ampliar `subscriptions.ts` con `quantumLeapSubscriptionIdsForEntity` y `buildQuantumLeapSubscriptionPayload`
- [ ] Tests unitarios
- [ ] Implementar hasta verde

### Task 2: DELETE proxy

- [ ] Endpoint DELETE + tests de validación URL
- [ ] `deleteSubscription` en `orion.ts`

### Task 3: EntityEdit UI

- [ ] Cargar GET al abrir; checkbox; sync tras PATCH OK
- [ ] Tests EntityEdit (marcado inicial, POST al activar, DELETE al desactivar, sin cambio)

### Task 4: Verificar

- [ ] `npm test` relevantes + typecheck
