# Broker NGSI-LD con Docker

Orion-LD + MongoDB para probar el espacio de datos del horno E-Therm.

Los dos servicios se definen en el **`docker-compose.yml` de la raíz del proyecto** (no dentro de esta carpeta): el servicio `mongo` (MongoDB 4.4) y `orion-ld`, que usa MongoDB como base de datos (`-dbhost mongo`). Esta carpeta solo contiene este README con instrucciones de uso.

## Requisitos

- Docker
- Docker Compose

## Levantar el broker

Desde la raíz del proyecto:

```bash
docker compose up -d
```

El broker estará disponible en **http://localhost:1026**.

## Comprobar que funciona

```bash
curl http://localhost:1026/version
```

## Registrar el contexto

Desde la raíz del proyecto:

```bash
curl -X POST http://localhost:1026/ngsi-ld/v1/jsonldContexts \
  -H "Content-Type: application/json" \
  -H "NGSILD-Context: http://example.org/industrial-oven-context" \
  -d @context/industrial-oven-context.jsonld
```

## Crear una entidad de prueba

**Opción A – Con script Python** (recomendado):

```bash
pip install requests
python scripts/post-example.py examples/Device/example-burner.json
```

El script añade el contexto al payload y envía con `Content-Type: application/ld+json`.

**Opción B – Con Link header** (si el contexto está registrado antes):

```bash
curl -X POST "http://localhost:1026/ngsi-ld/v1/entities" \
  -H "Content-Type: application/json" \
  -H "Link: <http://example.org/industrial-oven-context>; rel=\"http://www.w3.org/ns/json-ld#context\"; type=\"application/ld+json\"" \
  -d @examples/Device/example-burner.json
```


## Consultar entidades

```bash
# Todas las entidades de tipo Device
curl "http://localhost:1026/ngsi-ld/v1/entities?type=Device"

# Entidad por ID
curl "http://localhost:1026/ngsi-ld/v1/entities/urn:ngsi-ld:Device:burner-001"
```

## Parar el broker

```bash
docker compose down
```

Para eliminar también los datos de MongoDB:

```bash
docker compose down -v
```
