## Cierre Fase 2 - Migración de lógica de negocio a backend

### Alcance completado
En esta fase se ha trasladado al backend la lógica de negocio principal que estaba en frontend legacy para las vistas de `visualizacion` y `entidades`.

### Endpoints incorporados
- `POST /api/graph/orion/build`  
  Construcción de grafo de instancias Orion-LD (nodos/enlaces/estadísticas).

- `GET /api/entities/{entity_id}/view`  
  Vista enriquecida de entidad para panel UI (atributos formateados con metadatos).

- `POST /api/graph/schema/build`  
  Construcción de grafo abstracto del modelo (tipos/relaciones/métricas).

- `POST /api/graph/schema/type-view`  
  Detalle de tipo del schema (`from_rels` / `to_rels`) para panel UI.

- `POST /api/entities/prepare-payload`  
  Preparación y normalización de payload de creación (type/id/context/input_mode/payload_to_send).

- `POST /api/entities/prepare-attrs-payload`  
  Preparación y normalización de payload de edición (`PATCH attrs`).

### Cambios en frontend
- Las páginas `visualizacion` y `entidades` consumen los endpoints de backend para construcción/enriquecimiento/normalización.
- Se han eliminado fallbacks locales principales de lógica de negocio.
- La capa API (`static/js/api/orion.js`) quedó homogenizada en manejo de errores y retorno (`status`, `error`).

### Validación
- Test suite backend actualizada y en verde para helpers/proxy.
- Verificación manual de flujos funcionales clave (crear, editar, borrar, visualizar grafos, detalle de paneles).

### Estado
Fase 2 queda cerrada para iniciar Fase 3 (shell React y convivencia controlada con legacy).


## Smoke Test - Cierre Fase 2

### A. Configuración base
- [ ] Backend arranca sin errores.
- [ ] Frontend legacy carga vistas (`/`, `/entidades`, `/visualizacion`).
- [ ] Broker seleccionado y salud visible en barra de estado.

### B. Entidades
- [ ] Crear entidad desde JSON válido.
- [ ] Validar create muestra errores claros con JSON inválido.
- [ ] Crear evita duplicado por `id`.
- [ ] Editar attrs (`PATCH`) funciona con payload preparado.
- [ ] Validar patch muestra errores claros.
- [ ] Eliminar entidad funciona y refresca lista.
- [ ] Selección de entidad mantiene panel coherente tras operaciones.

### C. Visualización Orion
- [ ] Carga grafo Orion correctamente.
- [ ] Filtro por tipos (checks + master) aplica visibilidad.
- [ ] Zoom in/out/fit funcional.
- [ ] Click nodo abre detalle enriquecido.
- [ ] Borrado desde panel detalle recarga grafo.

### D. Visualización Schema
- [ ] Carga grafo schema correctamente.
- [ ] Click nodo abre detalle de tipo (`from_rels` / `to_rels`) desde backend.
- [ ] Panel info abre/cierra y resize funciona.
- [ ] Zoom in/out/fit funcional.

### E. Calidad transversal
- [ ] Sin errores JS en consola del navegador en flujos principales.
- [ ] Sin errores backend en logs para requests válidas.
- [ ] Tests backend en verde:
    - [ ] `pytest backend/tests/test_helpers.py backend/tests/test_proxy.py -q`