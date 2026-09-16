# Limpieza al eliminar entidad (anti-huérfanos)

Fecha: 2026-08-17  
Rama: `feature/orion-subscriptions-ui`  
Estado: aprobado

## Objetivo

Al borrar una entidad desde Entidades o Visualización, limpiar también:
1. Suscripciones activas a QuantumLeap de ese `id`
2. Atributos Relationship (u objetos URN) en **otras** entidades que apunten a ese `id`

Luego `DELETE` de la entidad.

## API

- Nuevo: `DELETE /api/proxy/entities/{id}/attrs/{attr}` → Orion delete attr
- Reutilizar GET/DELETE subscriptions y listado de entidades

## Comportamiento

- Orden: limpiar refs entrantes + subs → borrar entidad
- Fallos parciales de cleanup: se registran como avisos; se intenta igual el DELETE de la entidad
- Relación multi-objeto: si quedan otros targets, PATCH con la lista filtrada; si no queda ninguno, DELETE del atributo

## Criterios

1. Tras borrar X, no quedan subs QL de X
2. Tras borrar X, ninguna otra entidad apunta a X
3. El grafo no muestra nodo fantasma de X por relaciones rotas
