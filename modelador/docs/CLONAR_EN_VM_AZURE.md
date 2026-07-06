# Clonar y ejecutar el modelador en la VM de Azure

Repositorio en Azure DevOps:
`https://icd-devops@dev.azure.com/icd-devops/Innovacion/_git/07_INN_DATA_SPACE_MODELADOR`

## 1. En tu máquina local (antes de ir a la VM)

Asegúrate de tener subido el último código en la rama desde la que despliegas (p. ej. **`dev`**):

```bash
git push origin dev
```

Si el repo es privado, en la VM necesitarás autenticarte (ver abajo).

---

## 2. En la VM de Azure (Linux)

### Requisitos

- Git instalado.
- Para **Docker** (recomendado para despliegue SPA + API): Docker Engine y Docker Compose v2.
- Sin Docker: **Python 3.8+** solo para el backend manual.

### Clonar el repositorio

```bash
# Clonar (te pedirá usuario/contraseña o token si el repo es privado)
git clone https://icd-devops@dev.azure.com/icd-devops/Innovacion/_git/07_INN_DATA_SPACE_MODELADOR
cd 07_INN_DATA_SPACE_MODELADOR
git checkout dev
git pull origin dev
```

**Si el repo es privado en Azure DevOps:**

- **Opción A – Personal Access Token (PAT):**  
  En Azure DevOps: User settings → Personal access tokens → New token (permisos “Code: Read”).  
  Al hacer `git clone` usa como usuario tu cuenta (o el que tenga acceso) y como contraseña el **PAT**.

- **Opción B – SSH (si está configurado en el proyecto):**  
  En Azure DevOps ve a la URL del repo → Clone → SSH y usa esa URL, por ejemplo:  
  `git clone git@ssh.dev.azure.com:v3/icd-devops/Innovacion/07_INN_DATA_SPACE_MODELADOR`

### Con Docker (imagen única: frontend compilado + FastAPI)

Documentación detallada: [DOCKER.md](DOCKER.md).

```bash
cd 07_INN_DATA_SPACE_MODELADOR   # ya con rama dev actualizada
cp .env.docker.example .env      # editar CORS_ORIGINS con tu URL pública si aplica
docker compose up -d --build
```

Por defecto la aplicación queda en **`http://<IP-o-dominio-VM>:8844`** (mapeo `8844:8844`; cambia `HOST_PORT` en `.env` si necesitas otro puerto en el host).

### Sin Docker: solo backend con Python

```bash
cd backend
python3 -m venv venv
source venv/bin/activate   # En Windows (PowerShell): .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

La API responde en **`http://<IP-o-dominio-VM>:8000`**. Para servir la **SPA React** desde `frontend/dist`, antes hay que compilar en `frontend/` (`npm install && npm run build`) o, más simple, usar **Docker** (el build va en la imagen).

### (Opcional) Solo frontend estático legacy (`static/`)

Si en la VM solo quieres servir archivos estáticos (sin proxy al broker):

```bash
# Desde la raíz del repo
npx serve static -p 3000
```

Para producción suele usarse el backend (uvicorn) para tener proxy a Orion-LD y a las URLs del modelo.

---

## 3. En la VM de Azure (Windows)

### Con Docker (PowerShell)

```powershell
git clone https://icd-devops@dev.azure.com/icd-devops/Innovacion/_git/07_INN_DATA_SPACE_MODELADOR
cd 07_INN_DATA_SPACE_MODELADOR
git checkout dev
git pull origin dev
copy .env.docker.example .env
docker compose up -d --build
```

Abre `http://localhost:8844` desde la propia VM o `http://<IP-pública>:8844` desde fuera (abre el puerto en el NSG).

### Sin Docker: solo backend

```powershell
git clone https://icd-devops@dev.azure.com/icd-devops/Innovacion/_git/07_INN_DATA_SPACE_MODELADOR
cd 07_INN_DATA_SPACE_MODELADOR\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 4. Integración con otras partes

- **Orion-LD:** En la app (Conexión) pon la URL del broker (ej. `http://<ip-orion>:1026` si Orion está en la misma red de la VM).
- **Firewall / NSG:** Abre el puerto que uses (**8844** con Docker por defecto, **8000** si solo uvicorn sin Docker).
- **CORS:** Si accedes por IP o dominio público, define `CORS_ORIGINS` en `.env` junto a `docker-compose.yml` (ver `.env.docker.example`).
- **Actualizar código** en la VM cuando haya cambios:

  ```bash
  cd 07_INN_DATA_SPACE_MODELADOR
  git checkout dev
  git pull origin dev
  docker compose up -d --build    # con Docker
  ```
