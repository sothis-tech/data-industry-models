# Archivo histórico — documentación AS-IS

Estos documentos describen el modelador en un **momento pasado** del proyecto (UI estática en `static/`, sin autenticación integrada en la herramienta). Se conservan como referencia de flujos, capturas y decisiones de esa fase.

**No usar como manual del producto actual.** Para operar o extender el modelador hoy:

- Funcional TO-BE: `TO-BE_FUNCIONAL.docx` (evidencias PT2 del proyecto 07-SMART DATA MODELS).
- Casos de uso IBERMOT / METAPAN: `Casos de Uso NGSI-LD.docx`.
- Índice actualizado: [../README.md](../README.md).

## Contenido


| Fichero                                  | Descripción                                                  |
| ---------------------------------------- | ------------------------------------------------------------ |
| [AS_IS_FUNCIONAL.md](AS_IS_FUNCIONAL.md) | Flujos de usuario, pantallas y casos detallados con capturas |
| [AS_IS_TECNICO.md](AS_IS_TECNICO.md)     | Arquitectura, API, secuencias y curl de la época estática    |
| [AS_IS_REUNION.md](AS_IS_REUNION.md)     | Resumen ejecutivo para reunión de arquitectura               |


Las imágenes de los flujos funcionales están en [images/as_is_funcional/](images/as_is_funcional/).

## Equivalencias aproximadas (AS-IS → hoy)


| AS-IS                       | Estado actual                                             |
| --------------------------- | --------------------------------------------------------- |
| `static/index.html`         | `frontend/` — ruta `/` (Configuración)                    |
| `static/visualizacion.html` | `frontend/` — `/visualizacion`                            |
| `static/entidades.html`     | `frontend/` — `/entidades`                                |
| Sin auth en la herramienta  | Sesión Orion/Keycloak — [auth-orion.md](../auth-orion.md) |
| Solo proxy broker           | + chat Marvin, RAG, WebSocket AEA                         |


