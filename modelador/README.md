# Modelador oficial de espacios de datos NGSI-LD

Aplicación web para actuar como **modelador** de espacios de datos NGSI-LD: conectar a brokers Orion-LD (vía Kong), cargar modelos (schemas, contexto JSON-LD), visualizar tipos y relaciones en grafos, y dar de alta o modificar entidades con validación.

## Objetivos

- Conectar a uno o varios brokers **Orion-LD** (URL configurable, tenant FIWARE, comprobar conectividad y sesión).
- Cargar la definición del modelo desde:
  - URL(s) de **JSON Schemas** (entidades y atributos),
  - URL del **contexto JSON-LD** (@context),
  - Paquete comprimido (ZIP/TAR) o descriptor JSON opcional.
- Visualizar la estructura: grafos D3 del **esquema** del modelo y de las **entidades** en Orion.
- **Alta de entidades**: formulario según modelo, validación JSON Schema, POST a `/ngsi-ld/v1/entities` vía proxy.
- **Modificar atributos**: listar entidades (por tipo o ID), seleccionar y enviar PATCH a `/ngsi-ld/v1/entities/{id}/attrs`.
- Varios Orion: guardar y cambiar entre brokers (nombre + URL + tenant); modelo en el navegador (`localStorage`).
- Asistente de chat (texto y voz vía WebSocket AEA) y gestión **RAG** de documentación por tenant (requieren sesión Orion activa).

## Requisitos técnicos

- **Frontend**: SPA **React 19** + **TypeScript** + **Vite**, enrutado con `react-router-dom`, grafos con **D3**.
- **Backend**: **FastAPI** como BFF (proxy Orion, autenticación Keycloak en sesión HTTP-only, validación, grafos, RAG, chat).
- Consumo de schemas y contexto desde **URLs externas** o paquete subido al backend (evita CORS desde el navegador).

## Estructura del proyecto

```
├── backend/
│   ├── main.py              # FastAPI: proxy Orion, auth, API REST, WebSocket AEA, sirve frontend/dist
│   ├── orion_auth.py        # Sesión Orion / Keycloak en el BFF
│   ├── requirements.txt
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── pages/           # config, entidades, visualización
│   │   ├── components/      # chatbot, StatusBar, modales, …
│   │   ├── hooks/           # broker, modelo, listado entidades, voz AEA, …
│   │   ├── api/             # clientes HTTP hacia /api
│   │   ├── lib/             # http, storage, model-parser, graph-utils, …
│   │   ├── types/
│   │   └── styles/          # CSS por capas (tokens, layout, páginas)
│   ├── e2e/                 # pruebas Playwright
│   └── package.json
├── docs/                    # Índice, operación, contratos; archive/ = AS-IS histórico
│   ├── README.md
│   ├── archive/             # AS_IS_* (UI estática, abril 2026)
│   └── casos-uso/           # Guías IBERMOT / METAPAN (en preparación)
├── package.json             # scripts de arranque del backend desde la raíz
├── docker-compose.yml
└── README.md
```

## Cómo ejecutar

### Desarrollo local (recomendado)

En desarrollo conviene levantar **dos procesos**: el backend (API y proxy) y el frontend Vite (UI con hot reload).

**1. Backend** (puerto **8000**):

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Desde la raíz del proyecto:

```bash
npm run backend
```

**2. Frontend** (puerto **5173**, proxy `/api` → `8000`):

```bash
# si usas nvm: nvm use
cd frontend
npm install
npm run dev
```

Abre **http://127.0.0.1:5173/**.

Rutas de la SPA:

| Ruta | Pantalla |
|------|----------|
| `/` | Configuración (broker, modelo, onboarding, RAG) |
| `/entidades` | Alta, edición, listado y búsqueda de entidades |
| `/visualizacion` | Grafos de esquema y de datos en Orion |

La versión de Node queda fijada en `.nvmrc` y en `frontend/package.json` (`engines`: Node 20.x).

### Backend con build de producción del frontend

Si existe `frontend/dist` (tras `npm run build` en `frontend/`), el mismo proceso uvicorn sirve la SPA y la API en **http://127.0.0.1:8000/** (mismo origen, sin proxy de Vite).

```bash
cd frontend && npm run build
cd ../backend && uvicorn main:app --reload
```

### Docker (API + SPA en un solo contenedor)

Despliegue listo para una **VM u otro servidor**: imagen multi-stage que construye `frontend/`, copia `dist` y arranca FastAPI sirviendo SPA y `/api` en el **mismo origen** (puerto **8844** en el contenedor).

**Requisitos:** Docker y Docker Compose v2.

```bash
# En la raíz del repo: copiar variables (opcional)
cp .env.docker.example .env   # Windows: copy .env.docker.example .env

docker compose up -d --build
```

Por defecto: **http://127.0.0.1:8844/**. Ajusta el puerto del host con `HOST_PORT` en `.env`.

Variables principales: `HOST_PORT`, `CORS_ORIGINS`, `LOG_FORMAT`, `LOG_LEVEL`. Plantilla en **`.env.docker.example`**.

Documentación: **[docs/DOCKER.md](docs/DOCKER.md)**.

## API del backend (resumen)

El frontend llama a `/api/*` con el broker activo (`broker_base_url`, tenant) guardado en `localStorage`. Las peticiones autenticadas a Orion usan **cookies de sesión** del BFF (`credentials: 'include'`); el token Keycloak no se expone al navegador.

| Área | Ejemplos de rutas |
|------|-------------------|
| Salud y auth | `GET /api/health`, `POST /api/health/orion`, `POST /api/auth/orion/login`, `GET /api/auth/orion/status` |
| Proxy Orion | `GET/POST/PATCH/DELETE /api/proxy/entities`, `POST /api/proxy/fetch` |
| Modelo | `POST /api/upload/model-package`, `GET /api/context` |
| Entidades | `POST /api/entities/prepare-payload`, `GET /api/entities/{id}/view` |
| Validación | `POST /api/validate/entity`, `POST /api/validate/attrs` |
| Grafos | `POST /api/graph/schema/build`, `POST /api/graph/orion/build` |
| Chat / voz | `GET /api/chat/config`, `POST /api/chat/text`, `WebSocket /api/aea/ws` |
| RAG | `GET/POST /api/rag/tenants`, `POST /api/rag/upload`, `POST /api/rag/vectorize`, … |

Detalle de autenticación: **[docs/auth-orion.md](docs/auth-orion.md)**.

## Flujo de la aplicación

1. **Configuración** (`/`): URL del broker (Kong), tenant, login Orion/Keycloak, comprobar sesión, cargar modelo (URLs o ZIP), opcionalmente documentación RAG.
2. **Visualización** (`/visualizacion`): grafos del esquema y de entidades en Orion; filtros; enlace a entidades vía `sessionStorage`.
3. **Entidades** (`/entidades`): listado paginado, crear/editar/duplicar/eliminar con validación según el modelo cargado.

El **chatbot flotante** (texto y voz) está disponible en todas las pantallas cuando la sesión Orion es válida.

## Tests

```bash
cd frontend
npm test              # Vitest (unitarios)
npm run test:e2e      # Playwright
```

Más información: **[docs/TESTS.md](docs/TESTS.md)**.

## Roadmap y documentación

- **Índice de documentación:** **[docs/README.md](docs/README.md)** (TO-BE, operación, casos de uso).
- Autenticación Orion (Kong/Keycloak): **[docs/auth-orion.md](docs/auth-orion.md)**.
- Casos de uso IBERMOT / METAPAN: **[docs/casos-uso/README.md](docs/casos-uso/README.md)** (especificación en `Casos de Uso NGSI-LD.docx`, evidencias PT2).
- Plan de integración (Azure, AEA, seguridad): **[docs/INTEGRATION-PLAN.md](docs/INTEGRATION-PLAN.md)**.
- Contrato WebSocket agente de voz: **[docs/AEA-WEBSOCKET-CONTRACT.md](docs/AEA-WEBSOCKET-CONTRACT.md)**.
- Contrato `data` del chat Marvin (bloques UI): **[docs/AGENT-CHAT-DATA-CONTRACT.md](docs/AGENT-CHAT-DATA-CONTRACT.md)**.
- Migración desde la UI estática legacy: **[docs/MIGRACION_PAGINAS.md](docs/MIGRACION_PAGINAS.md)**.
- Archivo histórico AS-IS (UI estática): **[docs/archive/](docs/archive/)**.

## Referencias

- [NGSI-LD](https://www.etsi.org/deliver/etsi_gs/CIM/001_099/009/01.04.01_60/gs_CIM009v010401p.pdf)
- [Orion-LD](https://github.com/FIWARE/context.Orion-LD)
