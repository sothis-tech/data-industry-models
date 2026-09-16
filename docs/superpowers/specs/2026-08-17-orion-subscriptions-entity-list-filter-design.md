# Filtro de suscripciones en lista de entidades

Fecha: 2026-08-17  
Rama: `feature/orion-subscriptions-ui`  
Estado: aprobado

## Objetivo

En la vista Entidades, filtrar la lista por si la entidad tiene o no suscripción activa a QuantumLeap.

## UI

- Select en la toolbar: Todas / Con suscripción / Sin suscripción (junto a tipo + búsqueda).
- AND con filtros existentes.
- Sin badge en filas en este corte.

## Comportamiento

- Al cargar entidades, `GET` suscripciones en paralelo; matching igual que el grafo.
- Error al listar subs: filtro deshabilitado + aviso; lista usable.

## Criterios

1. “Con suscripción” muestra solo entidades con ≥1 sub activa a QL.
2. “Sin suscripción” las oculta.
3. Tipo + búsqueda + suscripción se combinan.
