# Docker: despliegue del Modelador NGSI-LD

Este documento describe la imagen Docker y cómo ejecutarla (local o en una VM, p. ej. Azure).

## Qué incluye la imagen

- **Un solo contenedor**: no hace falta un servicio aparte para el frontend.
- **Multi-stage** (`Dockerfile` en la raíz del repo):
  1. **`frontend-builder`** (Node 20): copia `frontend/`, instala dependencias con `npm install` y ejecuta `npm run build`. El resultado va a `frontend/dist` dentro del contexto de build.
  2. **`runtime`** (Python 3.12): instala dependencias de `backend/requirements.txt` omitiendo `pytest` y `pytest-asyncio`, copia el código de `backend/` y los estáticos compilados a **`/app/frontend/dist`**, que es la ruta que usa FastAPI en `main.py` para servir la SPA en `/` y rutas bajo el mismo origen que `/api`.

Así, **la SPA del repositorio es la que se empaqueta**; cada `docker build` recompila el front desde el código fuente del proyecto.

## Puerto

- El proceso **uvicorn** escucha en el **8844** dentro del contenedor (se eligió para no chocar con el 8000 habitual de desarrollo).
- Con **Docker Compose**, el puerto del **host** se configura con `HOST_PORT` (por defecto **8844**), mapeando `HOST_PORT:8844`.

Ejemplos:

- Mismo puerto en host y contenedor: sin tocar nada → `http://<host>:8844/`.
- Otro puerto en el host: `HOST_PORT=9080` → la app responde en `http://<host>:9080/`; el contenedor sigue escuchando en 8844 por dentro.

## Variables de entorno

Defínelas en un fichero **`.env`** junto a `docker-compose.yml` (puedes partir de `.env.docker.example`).

| Variable      | Descripción |
|---------------|-------------|
| `HOST_PORT`   | Puerto publicado en la máquina anfitriona (por defecto `8844`). |
| `CORS_ORIGINS` | Orígenes permitidos para el navegador, separados por comas. Para acceso por IP o dominio de la VM, incluye la URL base (p. ej. `http://203.0.113.10:8844`). `*` es válido cuando no usas credenciales por cookie hacia orígenes concretos. Ver `backend/main.py` y [LOGGING.md](LOGGING.md) si aplica. |
| `LOG_FORMAT`  | Por ejemplo `json` (recomendado en servidores). |
| `LOG_LEVEL`   | Por ejemplo `INFO` o `DEBUG`. |

Otros valores que el backend lea desde el entorno (Orion, AEA, etc.) se pueden pasar igual en `environment:` de Compose cuando los añadas al proyecto.

## Comandos habituales

Desde la **raíz del repositorio** (donde están `Dockerfile` y `docker-compose.yml`):

```bash
# Construir y levantar en segundo plano
docker compose up -d --build

# Ver logs
docker compose logs -f modelador

# Parar y quitar contenedores
docker compose down
```

Sin Compose (solo imagen):

```bash
docker build -t inn-data-space-modelador:latest .
docker run --rm -p 8844:8844 \
  -e CORS_ORIGINS='*' \
  inn-data-space-modelador:latest
```

## Comprobación rápida

- Documentación OpenAPI: `GET http://<host>:<puerto>/openapi.json`
- Interfaz: `GET http://<host>:<puerto>/`

El **healthcheck** de la imagen consulta `/openapi.json` en `127.0.0.1:8844` dentro del contenedor.

## Despliegue en VM (Azure u otra)

1. Instalar **Docker** y **Docker Compose** en la VM.
2. Clonar o copiar el repositorio (o solo los artefactos si publicas una imagen en un registry).
3. Crear `.env` desde `.env.docker.example` y ajustar `CORS_ORIGINS` a la URL pública real (esquema + host + puerto si no es 80/443).
4. Abrir en el **NSG / firewall** el puerto elegido (`HOST_PORT`, por defecto 8844).
5. Ejecutar `docker compose up -d --build`.

Para no reconstruir en la VM, podéis hacer `docker build` en CI, subir la imagen a ACR u otro registry y en la VM usar `docker compose pull` con una imagen versionada en lugar del `build:` local.

## Notas sobre el build del frontend

En la etapa Node se usa **`npm install`** (no `npm ci`) para tolerar pequeños desajustes entre `package-lock.json` y el registry en distintos entornos. Para builds totalmente reproducibles, alinear el lockfile con Node 20 en local y valorar volver a `npm ci` en el `Dockerfile`.

## Archivos relacionados

| Archivo | Rol |
|---------|-----|
| `Dockerfile` | Build multi-stage y comando `uvicorn` en `:8844`. |
| `docker-compose.yml` | Servicio `modelador`, puertos y variables. |
| `.dockerignore` | Reduce contexto de build (excluye `node_modules`, tests, etc.). |
| `.env.docker.example` | Plantilla de variables para copiar a `.env`. |
