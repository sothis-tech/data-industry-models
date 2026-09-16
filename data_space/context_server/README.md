# Context Server

Servidor de contexto multi-tenant del espacio de datos. Almacena el modelo
NGSI-LD de cada tenant en disco, con la misma estructura que el paquete `.zip`
estándar del modelador:

```
<TENANTS_ROOT>/<tenant>/
    descriptor.json
    meta.json                 # packageName, updatedAt
    context/context.jsonld
    schemas/<Entidad>.json
    examples/<Entidad>/example.json
```

## API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado del servicio |
| GET | `/tenants` | Lista de tenants |
| POST | `/tenants` | Alta de tenant (`{"name": "..."}`, idempotente) |
| DELETE | `/tenants/{tenant}` | Baja de tenant (borra su carpeta completa) |
| GET | `/tenants/{tenant}/model` | Modelo completo (schemas, context, descriptor, examples, contextUrl) |
| PUT | `/tenants/{tenant}/model` | Sustituye el modelo del tenant (reemplazo total) |
| DELETE | `/tenants/{tenant}/model` | Borra el modelo pero conserva el tenant |
| GET | `/tenants/{tenant}/context.jsonld` | Contexto JSON-LD crudo (usable como URL de `@context`) |

## Persistencia desde el modelador

**Regla:** cada carga **sustituye** el contenido del tenant. Lo que no viene en esa carga no queda en disco.

Si un mismo dato llega por zip y por URL, **gana la URL**.

| Entrada | En disco del tenant | `@context` / `meta.contextUrl` |
|---|---|---|
| Solo URLs | schemas + descriptor + examples; **sin** `context/` | URL externa en meta |
| Solo zip | Todo, incluido `context/context.jsonld` | URL estable del context server |
| Zip + URL de contexto | schemas + descriptor + examples del zip; **sin** `context/` (la URL gana) | URL externa |

Con URL externa, `GET /tenants/{tenant}/context.jsonld` responde 404 (el contexto no está materializado; hay que fetchear la URL).

## URLs de contexto (para Orion / IoT Agent / simulador)

Red Docker (canónica, igual que `http://context-provider/...`):

```text
http://context-server:8090/tenants/<tenant>/context.jsonld
```

Desde el host (puerto publicado, p. ej. `8095:8090`):

```text
http://localhost:8095/tenants/<tenant>/context.jsonld
```

El IoT Agent necesita una **URL HTTP**, no una ruta de fichero. Este endpoint cumple ese rol (mismo patrón que el `context-provider` nginx). Requisito: el tenant debe tener contexto cargado (p. ej. zip desde el modelador).

## Desarrollo local

```bash
pip install -r requirements.txt
TENANTS_ROOT=./tenants uvicorn main:app --reload --port 8090
```

## Tests

```bash
pip install pytest httpx
pytest tests/
```
