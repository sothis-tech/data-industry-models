# Plan de integración (desglose de tareas)

Documento vivo para cerrar integración entre el modelador NGSI-LD (este repo), Orion-LD en Azure, agente de escucha activa (AEA), orquestación, Keycloak/Kong y datos históricos/simulados. Roles: **Tú** = persona que coordina desde el front/modelador; **C1–C4** = compañeros por épica.

---

## Épica A — Agente de escucha activa (AEA) + front modelador

**Contrato WebSocket documentado:** [AEA-WEBSOCKET-CONTRACT.md](AEA-WEBSOCKET-CONTRACT.md) (mensajes, audio, handshake futuro auth).

| Tarea | Dueño | Depende de | Entregable |
|--------|--------|------------|------------|
| Contrato técnico: WebSocket (URL, auth, mensajes, errores, reconexión) con el agente de escucha | Tú + C1 | Acuerdo con quien implementa el agente | [AEA-WEBSOCKET-CONTRACT.md](AEA-WEBSOCKET-CONTRACT.md) + extensiones auth acordadas |
| Integración Orion + AEA + agente de control (orquestación) en entorno integrado | C1 (lidera) · Tú apoyo en encaje con modelador | Orion accesible desde VM | Demo E2E + notas |
| Decisión: misma instancia AEA que Smart Data Models vs nueva | Tú + C1 (+ arquitectura) | Criterios tenant/carga/aislamiento | Acta breve |
| Vista React: chat + micrófono (UX, estados, errores) | Tú | Contrato WS mínimo acordado | Cambios en front + capturas |
| Cliente WebSocket hacia el agente de escucha (¿pasa por Kong?) | Tú | Contrato + URL final + CORS/proxy | Funciona en dev y en VM |
| Desplegar Orion en VM Azure | Tú o C1 (acordado) | Puertos/DNS con épica C | Orion estable + URL documentada |
| Desplegar solución web (front + API modelador) en VM Azure | Tú | Orion + variables de entorno | URL + checklist despliegue |
| Pruebas de orquestación con varios data models | C1 (lidera) · Tú casos desde UI | Modelos cargados en Orion | Matriz prueba → resultado |
| Documentación épica A | Tú + C1 | Tareas previas relevantes | Diagrama despliegue + flujo usuario |

---

## Épica B — Autenticación y autorización

| Tarea | Dueño | Depende de | Entregable |
|--------|--------|------------|------------|
| Desplegar Keycloak en VM Azure | C2 | VM/red | Realm + client SPA + redirect URIs |
| Configurar usuarios, roles y tenants (claims) en Keycloak | C2 | Modelo de autorización acordado | Export realm o doc de configuración |
| Desplegar Kong en VM Azure | C2 | Keycloak disponible para validación JWT/OIDC | Rutas base + TLS si aplica |
| Plugins Kong: JWT/OIDC + autorización por tenant | C2 | Claims en token | Reglas + prueba con curl |
| Integración login / logout en la Web (React) | Tú | Client Keycloak y URLs conocidas | Flujo estable en SPA |
| Tokens: llamadas API vía Kong + cabecera `Authorization` | Tú (SPA) · C2 (gateway) | Rutas Kong | `API_BASE`/env documentados |
| Pruebas docker modelador en local contra IdP/proxy (opcional) | C2 | Guía mínima | Doc “local + Keycloak/Kong mock” si aplica |
| Documentación épica B | Tú + C2 | — | OAuth/OIDC, CORS, variables, troubleshooting |

**Reparto sugerido:** C2 = infra (Keycloak, Kong, plugins, usuarios); Tú = integración en SPA y alineación con el código actual del modelador (`fetch`, `API_BASE`).

---

## Épica C — Histórico (QuantumLeap), Orion-LD, SDM y puertos

| Tarea | Dueño | Depende de | Entregable |
|--------|--------|------------|------------|
| Reunión de alineación: estado del modelador + SDM | Tú + C3 | — | Acta + decisiones |
| Confirmar funcionamiento SDM en el entorno objetivo | Tú + C3 | Orion y contextos | Checklist OK/KO |
| Matriz única: servicio → contenedor → puertos host/internos | C3 (lidera) · Tú validas con modelador | — | Tabla + compose o equivalente |
| Integración de histórico separado por tipos SDM (p. ej. QuantumLeap) | C3 | Matriz de puertos + Orion | Series/histórico según diseño |
| Migrar/clonar infra Smart Machine compatible con SDM | C3 | Matriz | Entorno clonado documentado |
| Ajustar puertos para evitar conflictos entre contenedores FIWARE | C3 | Matriz cerrada | Verificación sin colisiones |
| Documentación épica C | C3 · revisión Tú | — | Despliegue FIWARE + puertos |

---

## Épica D — Generación de datos simulados

| Tarea | Dueño | Depende de | Entregable |
|--------|--------|------------|------------|
| Crear entornos de simulación | C4 | Tipos NGSI-LD acordados | Scripts/containers reproducibles |
| Generar datos hacia Orion | C4 | Entorno anterior | Dataset o job documentado |
| Cambios en web si la simulación se dispara desde la UI | Tú | Contrato backend con C4 | Vista + API si se pide para v1 |
| Documentación épica D | C4 · Tú si hay UI | — | Cómo ejecutar y verificar entidades |

---

## Orden recomendado entre épicas

1. **C (puertos + SDM + Orion estable)** cuanto antes: desbloquea despliegues y pruebas reales.
2. **B (Keycloak + Kong)** puede ir en paralelo con A, antes de exponer la SPA.
3. **A (WS + chat)** cuando exista contrato del agente y URLs finales (confirmar soporte WS en Kong si aplica).
4. **D** cuando Orion y los tipos de entidad estén acordados.

---

## Riesgos a vigilar

- **Solape Tú / C1** en “integrar sistemas”: repartir orquestación vs. modelador/UI.
- **Solape Tú / C2** en tokens: repartir configuración Kong vs. cambios en React.
- **WebSocket + Kong:** validar proxy WS, timeouts y TLS antes de comprometer fechas en voz/chat.

---

## Referencias en este repositorio

- [TESTS.md](TESTS.md) — estrategia de pruebas (unitarios, E2E, Orion opcional).
- [LOGGING.md](LOGGING.md) — formato JSON y variables `LOG_*` / `VITE_*`.
- [AEA-WEBSOCKET-CONTRACT.md](AEA-WEBSOCKET-CONTRACT.md) — contrato con el agente de escucha activa (voz, WebSocket).
