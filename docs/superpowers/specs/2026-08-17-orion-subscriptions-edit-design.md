# Suscripciones Orion → QuantumLeap desde editar entidad (fase 2A)

Fecha: 2026-08-17  
Rama: `feature/orion-subscriptions-ui`  
Estado: aprobado — implementación en curso / fase 2A

## Objetivo

Permitir **activar o desactivar** la notificación a QuantumLeap al **editar** una entidad existente, sin gestión masiva ni cambios en el flujo de creación (salvo reutilizar el mismo payload de suscripción).

## Decisiones

| Tema | Decisión |
|---|---|
| Alcance de este corte | Solo **EntityEdit** (opción A) |
| Granularidad | Todos los atributos actuales del payload de attrs (como en crear) |
| Quitar suscripción | `DELETE` en Orion de las subs a QL de esa entidad |
| Varias subs | ≥1 activa a QL ⇒ checkbox ON; al quitar, borrar **todas** las activas a QL de ese `id` |
| Endpoint QL | Fijo `http://quantumleap:8668/v2/notify` |
| Histórico QL | Intactos al borrar la suscripción |
| Fallo de sub | No bloquea el guardado de atributos; aviso breve en UI |
| Grafo | Se actualiza al recargar instancias (sin sync en vivo) |

## Comportamiento

1. Al abrir/cargar la entidad en edición:
   - `GET` suscripciones del broker/tenant.
   - Checkbox “Notificar a QuantumLeap” marcado si el `id` de la entidad está en el conjunto de suscritas (misma lógica de matching que el grafo: activa + URI QL + `entities[].id`).
2. El usuario puede cambiar el checkbox libremente; el efecto se aplica al **guardar** (junto al PATCH de attrs, o justo después si el PATCH tiene éxito).
3. Tras PATCH de attrs exitoso:
   - Si checkbox **ON** y no había sub activa a QL → `POST` suscripción (mismo shape que `EntityCreate`).
   - Si checkbox **OFF** y había una o más subs activas a QL → `DELETE` de cada una por su `id`.
   - Si el estado del checkbox coincide con el estado previo → no llamar a POST/DELETE de suscripciones.
4. Si el PATCH de attrs falla → no tocar suscripciones.
5. Si POST/DELETE de suscripción falla → attrs ya guardados; mostrar mensaje no bloqueante (p. ej. bajo el checkbox o en la zona de validación).

## API

- Reutilizar: `GET` / `POST` `/api/proxy/subscriptions`.
- Nuevo: `DELETE /api/proxy/subscriptions/{subscription_id}?broker_base_url=&fiware_service=` → Orion `DELETE /ngsi-ld/v1/subscriptions/{id}`.
- Frontend: `getSubscriptions`, `postSubscription`, nuevo `deleteSubscription`.

## UI

- Checkbox en `EntityEdit`, mismo copy que en crear: “Notificar a QuantumLeap”.
- Estado inicial según suscripciones; deshabilitar mientras carga la entidad o las suscripciones.
- Opcional: texto auxiliar si no se pudieron cargar las suscripciones (checkbox deshabilitado o neutro OFF + aviso).

## Fuera de alcance

- Acción masiva en listado.
- URL de QL configurable.
- Edición manual de `watchedAttributes` / varias subs “a medida”.
- Actualización automática del grafo sin recargar.
- Cambiar el comportamiento del checkbox en **crear** (sigue igual).

## Criterios de aceptación

1. Entidad con sub activa a QL: al editar, el checkbox aparece marcado.
2. Desmarcar y guardar: desaparecen las subs a QL de esa entidad en Orion; el histórico en QL no se borra desde el modelador.
3. Marcar y guardar en entidad sin sub: se crea una sub con los atributos actuales y endpoint QL fijo.
4. Guardar sin cambiar el checkbox: no se crean ni borran suscripciones.
5. Error al listar/crear/borrar sub: el PATCH de attrs no se revierte; hay feedback visible.
6. Tests: matching helpers si se amplían; proxy DELETE con validación de `broker_base_url`; smoke de EntityEdit si el proyecto ya cubre el checkbox de create de forma análoga.
