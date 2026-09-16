# Suscripciones Orion → QuantumLeap en el grafo (fase 1)

Fecha: 2026-08-17  
Rama: `feature/orion-subscriptions-ui`  
Estado: aprobado — implementación fase 1

## Objetivo

Permitir **ver** en la vista de grafo (instancias Orion) qué entidades tienen una suscripción activa hacia QuantumLeap, con filtro dedicado y badge en el nodo. Sin alta/baja de suscripciones en esta fase.

## Decisiones

| Tema | Decisión |
|---|---|
| Alcance | Solo lectura / visualización (fase 1) |
| Filtro UI | Misma columna que tipos, sección debajo + badge en nodo |
| Varias suscripciones | Si ≥1 activa a QL para esa entidad → “suscrita” |
| QL endpoint | Fijo `http://quantumleap:8668/v2/notify` (como al crear) |
| Fase 2 (fuera) | Toggle crear/editar, masivo, DELETE (histórico QL intacto) |

## Comportamiento

1. Al cargar el grafo de instancias (o al refrescar), el frontend pide las suscripciones del broker/tenant.
2. Se consideran “suscritas” las entidades cuyo `id` aparece en alguna suscripción:
   - no `inactive` / `failed` (si hay `status`);
   - cuyo `notification.endpoint.uri` apunta a QuantumLeap (`quantumleap` + `notify` / puerto 8668).
3. Filtro **Suscripciones**: Todas | Con suscripción | Sin suscripción, combinado con filtro de tipos (AND).
4. Badge/icono discreto en nodos suscritos.

## API

- Nuevo proxy: `GET /api/proxy/subscriptions?broker_base_url=&fiware_service=` → Orion `GET /ngsi-ld/v1/subscriptions`.

## Fuera de alcance (fase 1)

- POST/DELETE suscripciones desde editar / lista masiva.
- Gestionar suscripciones una a una.
- Configurable URL de QL.

## Criterios de aceptación

1. Con suscripciones en Orion hacia QL, los nodos correspondientes muestran badge.
2. Filtro “Con suscripción” deja solo esos nodos (respetando filtro de tipos).
3. “Sin suscripción” oculta los que tienen sub a QL.
4. Sin broker / error al listar: grafo usable; filtro suscripciones en estado neutro o deshabilitado con mensaje breve.
5. Tests unitarios del matching entidad↔suscripción y del proxy si aplica.
