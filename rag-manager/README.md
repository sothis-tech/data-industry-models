# rag-manager

Herramienta para gestionar la base de conocimiento vectorial (ChromaDB).
Permite subir PDFs, organizarlos por tenant y vectorizarlos para que el agente pueda consultarlos.

---

## Estructura

```
rag-manager/
├── backend/      → API Python (FastAPI)
└── frontend/     → Interfaz React (Vite)
```

Debe estar al mismo nivel que `chromadb_service`:

```
proyectos/
├── chromadb_service/    ← ChromaDB dockerizado
├── rag-manager/         ← este proyecto
└── agente_control_data_space/
```

---

## Requisitos previos

- ChromaDB corriendo en `localhost:8200` (ver `chromadb_service/`)
- Python ≥ 3.11 con `uv` instalado
- Node.js ≥ 18

---

## Arrancar el backend

### Primera vez — instalación

Antes de instalar hay que asegurarse de que `uv` guarda la caché en un disco con espacio suficiente. En este servidor el disco raíz (`/`) es pequeño; todo va a `/data`. Ejecuta esto una sola vez por usuario:

```bash
echo 'export UV_CACHE_DIR=/data/uv_cache' >> ~/.bashrc
echo 'export UV_DATA_DIR=/data/uv_data'   >> ~/.bashrc
echo 'export PIP_CACHE_DIR=/data/pip_cache' >> ~/.bashrc
source ~/.bashrc
```

Luego instala y arranca:

```bash
cd backend

# Instalar dependencias (la primera vez tarda varios minutos, descarga modelos grandes)
uv sync

# El .env ya está configurado, no hace falta tocarlo salvo que cambies algo
# Si no existe, cópialo desde el ejemplo:
cp .env.example .env

# Arrancar
uv run uvicorn main:app --host 0.0.0.0 --port 8301 --reload
```

El backend queda en `http://localhost:8300`.
Documentación automática en `http://localhost:8300/docs`.

> **Si aparece "No space left on device"** durante el `uv sync` significa que la caché se está guardando en el disco raíz que está lleno. Asegúrate de haber ejecutado los `export` de arriba y de haber hecho `source ~/.bashrc` antes de volver a intentarlo. Si el error persiste, limpia la caché actual con `uv cache clean` y vuelve a ejecutar `uv sync`.

---

## Arrancar el frontend

```bash
cd frontend

# Primera vez
npm install

# Arrancar
npm run dev
```

La app queda en `http://localhost:5173`.

---

## Variables de entorno del backend

Están en `backend/.env` (copia de `.env.example`):

| Variable | Default | Descripción |
|---|---|---|
| `CHROMA_HOST` | `localhost` | Host de ChromaDB |
| `CHROMA_PORT` | `8200` | Puerto de ChromaDB |
| `CHROMA_COLLECTION` | `manuales_tecnicos` | Nombre de la colección |
| `DOCS_PATH` | `./docs` | Carpeta donde se guardan los PDFs |
| `HF_HOME` | `~/.cache/hf` | Caché de modelos HuggingFace |
| `PORT` | `8300` | Puerto del backend |

---

## Qué hace cada cosa

### Tenants
Cada tenant es un espacio aislado dentro de ChromaDB. Lo que se indexa en un tenant no es visible desde otro. Útil para separar documentos por cliente, proyecto o área.

- Puedes elegir un tenant existente o crear uno nuevo desde la interfaz.
- Al cambiar de tenant cambia todo: documentos, índice y estadísticas.
- Puedes eliminar un tenant completo pulsando la ✕ que aparece junto a su nombre. Pedirá confirmación antes de borrar. El tenant `default_tenant` no se puede eliminar.
- Al eliminar un tenant se borran su colección en ChromaDB, todos sus PDFs en disco y se elimina de la lista.

### Subir documentos
Arrastra PDFs a la zona de carga o haz clic para seleccionarlos. Los archivos se guardan en `backend/docs/<nombre_tenant>/`. Solo se suben al disco, no se vectorizan todavía.

### Vectorizar
Convierte los PDFs en embeddings y los guarda en ChromaDB. Puedes vectorizar todos los pendientes de golpe o uno a uno. Una vez vectorizado el agente puede consultarlo.

### Estados de un documento
- **pendiente** → está en disco pero no en ChromaDB
- **indexado** → está en ChromaDB y el agente puede buscarlo

### Quitar del índice
Elimina el documento de ChromaDB pero el PDF sigue en disco. Útil si quieres re-vectorizar con otros ajustes.

### Borrar
Elimina el documento de ChromaDB y también el PDF del disco, esté o no indexado. No hay vuelta atrás.

### Vaciar índice
Borra todos los chunks del tenant en ChromaDB. Los PDFs en disco se mantienen.

---

## Endpoints del backend (para integrar en otro proyecto)

```
GET    /tenants                              → lista de tenants
POST   /tenants                              → crear tenant  { name }
DELETE /tenants/{tenant}                     → eliminar tenant completo (índice + PDFs)
GET    /tenants/{tenant}/documents           → estado de documentos
POST   /tenants/{tenant}/upload              → subir PDF (multipart)
POST   /tenants/{tenant}/vectorize           → vectorizar  { filenames?: [] }
DELETE /tenants/{tenant}/documents/{file}    → quitar del índice  ?delete_file=true/false
DELETE /tenants/{tenant}/clear               → vaciar índice
GET    /health                               → estado de conexión con ChromaDB
```

---

## Integrar el hook en otro proyecto React

Copia `frontend/src/hooks/useRag.js` a tu proyecto y úsalo así:

```jsx
import { useRag } from "./hooks/useRag";

function MiComponente() {
  const rag = useRag();

  // estado disponible
  rag.tenants       // string[] — lista de tenants
  rag.tenant        // string  — tenant activo
  rag.docs          // objeto  — { indexed, disk_files, not_indexed, total_chunks }
  rag.loading       // boolean
  rag.error         // string | null

  // acciones
  rag.selectTenant(name)
  rag.createTenant(name)
  rag.deleteTenant(name)           // elimina tenant, índice y PDFs (no aplica a default_tenant)
  rag.uploadPdf(file)              // file = objeto File del input
  rag.vectorize()                  // todos los pendientes
  rag.vectorize(["doc.pdf"])       // solo ese fichero
  rag.deleteFromIndex(name)        // quita de ChromaDB, PDF queda en disco
  rag.deleteAll(name)              // quita de ChromaDB y borra el PDF (funciona aunque no esté indexado)
  rag.clearIndex()                 // vacía toda la colección del tenant
  rag.refresh()                    // recarga el estado
}
```

El hook usa el proxy de Vite (`/api` → `localhost:8300`). Si lo integras en otro proyecto sin Vite cambia la constante `BASE` en `useRag.js` por la URL completa del backend.
