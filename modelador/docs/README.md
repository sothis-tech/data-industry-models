# Documentación del modelador NGSI-LD

Índice de la documentación versionada en este repositorio. La **referencia funcional y de casos de uso vigente** la mantiene el arquitecto en Word (carpeta de evidencias del proyecto 07-SMART DATA MODELS); aquí se enlaza el contrato técnico implementado y material operativo.

## Documentación vigente (TO-BE / operación)


| Documento                                                  | Contenido                                                                         |
| ---------------------------------------------------------- | --------------------------------------------------------------------------------- |
| [../README.md](../README.md)                               | Visión del producto, arranque, API resumida                                       |
| [auth-orion.md](auth-orion.md)                             | Autenticación Orion vía Kong/Keycloak (derivado de `TO_BE_TECNICO AUTENTICACION`) |
| [DOCKER.md](DOCKER.md)                                     | Despliegue con Docker Compose                                                     |
| [CLONAR_EN_VM_AZURE.md](CLONAR_EN_VM_AZURE.md)             | Clonado y despliegue en VM Azure                                                  |
| [TESTS.md](TESTS.md)                                       | Estrategia y ejecución de pruebas                                                 |
| [LOGGING.md](LOGGING.md)                                   | Logs JSON y variables de entorno                                                  |
| [INTEGRATION-PLAN.md](INTEGRATION-PLAN.md)                 | Plan de integración (AEA, Azure, seguridad)                                       |
| [AEA-WEBSOCKET-CONTRACT.md](AEA-WEBSOCKET-CONTRACT.md)     | Contrato WebSocket agente de escucha activa                                       |
| [AGENT-CHAT-DATA-CONTRACT.md](AGENT-CHAT-DATA-CONTRACT.md) | Bloques `data` del chat Marvin en la UI                                           |
| [QA-E2E-AGENT-PANEL.md](QA-E2E-AGENT-PANEL.md)             | Guion E2E manual del panel de agente                                              |


### Casos de uso industriales (IBERMOT, METAPAN)


| Recurso                                  | Ubicación                                                                                      |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Especificación y metodología de modelado | `Casos de Uso NGSI-LD.docx` en evidencias PT2 (ver [casos-uso/README.md](casos-uso/README.md)) |
| Guías puente modelador ↔ paquete `.zip`  | [casos-uso/](casos-uso/) — [ZIP y scripts `load_*`](casos-uso/REFERENCIA-PAQUETE-Y-SCRIPTS.md) |


### Fuentes oficiales fuera del repo (Word)

Ruta habitual de evidencias (OneDrive/NUNSYS):

`...\07-SMART DATA MODELS\03_Tecnico\PT2\Evidencias\`


| Fichero                                                   | Rol                                               |
| --------------------------------------------------------- | ------------------------------------------------- |
| `TO-BE_FUNCIONAL.docx`                                    | Funcionalidad objetivo del modelador + AEA        |
| `TO_BE_TECNICO AUTENTICACION v2.docx`                     | Auth (resumido en [auth-orion.md](auth-orion.md)) |
| `Casos de Uso NGSI-LD.docx`                               | CU-01 IBERMOT, CU-02 METAPAN, metodología ZIP     |
| `Guia de modelado de nueva entidad Document NGSI_LD.docx` | Alta de tipos/entidades en el modelo              |


Los `.docx` no se versionan en git (ver `.gitignore`: `docs/*.docx`).

## Migración y cierre legacy


| Documento                                              | Contenido                     |
| ------------------------------------------------------ | ----------------------------- |
| [MIGRACION_PAGINAS.md](MIGRACION_PAGINAS.md)           | Migración UI estática → React |
| [MIGRACION_FASE2_CIERRE.md](MIGRACION_FASE2_CIERRE.md) | Checklist cierre fase 2       |


## Archivo histórico (AS-IS)

Fotografía del producto con **frontend HTML/JS estático** (abril 2026). No describe el estado actual (React 19, auth Orion, panel Marvin/AEA).

→ [archive/README.md](archive/README.md)