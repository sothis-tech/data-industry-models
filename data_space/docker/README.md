# Broker NGSI-LD con Docker

> **Usa el compose de la raíz del monorepo**, no un compose local en esta carpeta.

```bash
# desde la raíz del proyecto (07_inn_espacio_de_datos/)
docker compose up -d
```

Servicios relevantes:

| Servicio | Puerto host | Notas |
|---|---|---|
| `orion-ld` | 1027→1026 (u el mapeo del compose raíz) | Broker NGSI-LD |
| `context-provider` | 8080 | Nginx estático (`data_space/context/`) — demo E-Therm |
| `context-server` | **8095→8090** | Context server multi-tenant (modelos por tenant). Interno siempre `:8090`. |

## Context server (multi-tenant)

URL del contexto de un tenant (red Docker):

```text
http://context-server:8090/tenants/<tenant>/context.jsonld
```

Desde el host:

```text
http://localhost:8095/tenants/<tenant>/context.jsonld
```

Documentación completa: [`../context_server/README.md`](../context_server/README.md).

## Context provider (estático)

Sigue sirviendo los ficheros de `data_space/context/` en `http://context-provider/...` / `http://localhost:8080/...`. No se elimina en esta iteración.

## Comprobar Orion

```bash
curl http://localhost:1026/version
# o el puerto publicado en el compose raíz
```
