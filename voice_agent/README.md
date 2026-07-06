# Voice Agent - Sistema de Agente de Voz

Sistema de agente de voz que integra:
- **Speech-to-Text**: Whisper para transcripción en tiempo real
- **Voice Activity Detection (VAD)**: Detección de voz y silencio
- **Wake word**: Palabra de activación (por defecto: "marvin")
- **Agente externo**: Envía la transcripción a un servicio de control de activos (API configurada en `AGENT_API_URL`)
- **Text-to-Speech (TTS)**: Piper para generar la respuesta en voz
- **Frontend Angular**: Interfaz web para interacción por voz

## 🏗️ Arquitectura

```
┌─────────────┐      WebSocket      ┌─────────────┐
│   Frontend  │ ◄─────────────────► │   Backend   │
│   Angular   │                     │   FastAPI   │
└─────────────┘                     └─────────────┘
                                            │
                                            ├─► Whisper (STT)
                                            ├─► Agente externo (AGENT_API_URL)
                                            ├─► Piper (TTS)
                                            └─► WebRTC VAD
```

## 📋 Requisitos Previos

- Docker y Docker Compose
- GPU NVIDIA (para Whisper y TTS)
- El **agente externo** (servicio de control de activos) debe estar levantado y accesible en la URL configurada en `AGENT_API_URL` (por ejemplo en el host en el puerto 8081)
- Para desarrollo local: Python 3.10+, Node.js

## 📦 Instalación de Dependencias

### Para Desarrollo Local (Windows)

# Crear entorno virtual
python -m venv venv
venv\Scripts\activate

# Instalar dependencias específicas de Windows (CUDA 12.1)
pip install -r requirements-windows.txt

# Instalar dependencias de desarrollo (opcional, para Jupyter notebooks)
pip install -r requirements-dev.txt 

**Nota**: `requirements-windows.txt` contiene versiones específicas de PyTorch (2.3.1) compatibles con CUDA 12.1 en Windows.

### Para Docker/Linux

Las dependencias se instalan automáticamente al construir la imagen Docker usando `requirements.txt` (optimizado para Linux con versiones flexibles).

docker compose build 

**Nota**: `requirements.txt` usa versiones flexibles de PyTorch que se adaptan al sistema Linux.

### Archivos de Requirements

- **`requirements.txt`**: Para Docker/Linux (versiones flexibles)
- **`requirements-windows.txt`**: Para Windows local con CUDA 12.1 (versiones específicas)
- **`requirements-dev.txt`**: Dependencias de desarrollo (Jupyter, IPython, etc.)

## 🚀 Inicio Rápido

### Opción 1: Docker Compose (Recomendado)

```bash
# Clonar el repositorio
git clone <repo-url>
cd voice_agent

# Copiar y editar la configuración (incluye AGENT_API_URL)
cp config.env.example config.env

# Iniciar todos los servicios
docker compose up -d

# Ver logs
docker compose logs -f
```

- **Frontend:** http://localhost:4200  
- **Backend:** http://localhost:8000  

**Importante:** Configura `AGENT_API_URL` en `config.env` con la URL del agente de control de activos. Sin ella, el backend no podrá generar respuestas. Ver [docs/MANUAL_USO_BACKEND.md](docs/MANUAL_USO_BACKEND.md) para más detalle.

### Opción 2: Desarrollo Local

#### Backend

```bash
# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements-windows.txt

# Iniciar servidor
uvicorn backend.server:app --reload --host 0.0.0.0 --port 8000 
start_backend.bat
```

#### Frontend

```bash
cd frontend
npm install
npm start
```

## 📁 Estructura del Proyecto

```
voice_agent/
├── backend/                 # Servidor FastAPI
│   ├── server.py            # Punto de entrada y WebSocket
│   ├── config.py            # Configuración (config.env)
│   ├── command_pipeline.py  # Pipeline: STT → agente → TTS
│   ├── services/
│   │   └── agent_service.py # Cliente del agente externo (AGENT_API_URL)
│   ├── tts_service.py       # TTS con Piper
│   └── vad_manager.py       # Detección de voz
├── frontend/                # Aplicación Angular
│   └── src/app/
│       ├── components/      # Chat, etc.
│       └── services/        # Mic, WebSocket
├── docs/
│   └── MANUAL_USO_BACKEND.md  # Manual de uso del backend
├── scripts/                 # Scripts de utilidad
│   ├── download_tts_model.py # Descarga modelo TTS
│   ├── mock_agent.py        # Mock del agente para pruebas
│   └── test_*.py
├── docker-compose.yml      # Backend + Frontend
├── Dockerfile.backend      # Imagen Docker backend
├── Dockerfile.frontend     # Imagen Docker frontend
├── config.env.example      # Ejemplo de configuración
└── requirements.txt        # Dependencias Python (Docker/Linux)
```

## 🔧 Configuración

El proyecto utiliza un sistema de configuración basado en variables de entorno para facilitar el despliegue y la personalización sin tocar el código.

### Configuración Rápida

1.  Copia el archivo de ejemplo:
    ```bash
    cp config.env.example config.env
    ```
2.  Edita `config.env` con tus preferencias.

### Variables Disponibles

| Variable | Descripción | Valor por Defecto |
| :--- | :--- | :--- |
| **Generales** | | |
| `LOG_LEVEL` | Nivel de detalle en logs (`DEBUG`, `INFO`, `WARNING`) | `DEBUG` |
| **Wake Word** | | |
| `WAKE_WORD` | Palabra clave para activar el agente | `marvin` |
| `WAKE_WORD_ALIASES` | Variantes fonéticas aceptadas (separadas por coma) | `marby,martin,marlin...` |
| `ACTIVE_TIMEOUT_SEC` | Segundos de espera tras activación antes de volver a dormir | `8.0` |
| **Detección de Voz (VAD)** | | |
| `MIN_RMS` | Sensibilidad del micrófono. Subir si hay ruido. | `0.01` |
| `MIN_VOICE_SEC` | Duración mínima para considerar una frase válida (segundos) | `1.0` |
| `SILENCE_WAIT_MS` | Tiempo de silencio para dar por terminada una frase (ms) | `2000` |
| **Transcripción** | | |
| `WHISPER_LANG` | Idioma para la transcripción (Whisper) | `es` |
| **Agente externo** | | |
| `AGENT_API_URL` | **URL del agente de control de activos (obligatoria)** | — |

El backend **siempre** envía la transcripción al agente externo. Sin `AGENT_API_URL` configurada o si el agente no responde, el usuario oirá un mensaje de error. Para pruebas locales puedes usar el mock: `python scripts/mock_agent.py` y configurar `AGENT_API_URL=http://localhost:8081/api/chat`.

### Notas de Despliegue
- El archivo `config.env` está en `.gitignore` para no subir configuraciones locales.
- En entornos Docker/Cloud, las variables de entorno del sistema tienen prioridad sobre el archivo `config.env`.

### Entornos en Docker Compose (base + override)

El backend carga configuración en dos capas desde `docker-compose.yml`:

1. `config.env` (base común)
2. `${BACKEND_ENV_FILE:-config.dev.env}` (override por entorno)

Si una variable existe en ambos archivos, prevalece la del segundo archivo (override).

Archivos de entorno disponibles:
- `config.env`: valores base compartidos.
- `config.dev.env`: overrides para desarrollo/pruebas.
- `config.prod.env`: overrides para producción.

Variables de timeout del agente externo:
- `AGENT_TIMEOUT_TOTAL_SEC`: timeout total de la petición HTTP al agente.
- `AGENT_TIMEOUT_CONNECT_SEC`: timeout máximo para establecer conexión TCP.

Valores actuales por entorno:
- **Dev (por defecto)**: `AGENT_TIMEOUT_TOTAL_SEC=120`, `AGENT_TIMEOUT_CONNECT_SEC=10`
- **Prod**: `AGENT_TIMEOUT_TOTAL_SEC=30`, `AGENT_TIMEOUT_CONNECT_SEC=10`

Comandos útiles:

```bash
# Levantar backend con entorno dev (por defecto)
docker compose up -d --force-recreate backend

# Levantar backend con entorno prod
BACKEND_ENV_FILE=config.prod.env docker compose up -d --force-recreate backend

# Ver logs del backend
docker compose logs -f backend
```

## 🧪 Testing y Evaluación

### Test de Segmentos de Audio

```bash
# Desde la raíz del proyecto
python scripts/test_audio_segments.py
```

### Evaluación de Precisión de Transcripción

```bash
# Desde la raíz del proyecto
python scripts/test_transcription_accuracy.py
```

Este script:
- Carga el dataset Common Voice
- Transcribe audios con Whisper
- Calcula WER (Word Error Rate) y CER (Character Error Rate)
- Guarda resultados progresivamente en `output/test_results/`

### Análisis de Resultados

Usa el notebook `analyze_transcription_results.ipynb` para:
- Analizar métricas de transcripción
- Filtrar casos problemáticos
- Comparar normalizaciones

## 📊 Métricas

El sistema calcula:
- **WER (Word Error Rate)**: Porcentaje de errores a nivel de palabras
- **CER (Character Error Rate)**: Porcentaje de errores a nivel de caracteres

## 🐳 Docker

### Construir imágenes

```bash
# Backend
docker build -f Dockerfile.backend -t voice-agent-backend .

# Frontend
docker build -f Dockerfile.frontend -t voice-agent-frontend .
```

### Ejecutar contenedores individuales

```bash
# Backend
docker run -p 8000:8000 --gpus all voice-agent-backend

# Frontend
docker run -p 4200:4200 voice-agent-frontend
```

## 🔍 Troubleshooting

### Problemas comunes

1. **No conecta con el agente externo**
   - Verifica que `AGENT_API_URL` esté definida en `config.env`.
   - Si el agente está en el host: usa `http://host.docker.internal:8081/api/chat` (el backend tiene `extra_hosts` para eso).
   - Revisa los logs: `docker compose logs -f backend` y busca `[Agent] Excepción conectando...` o `[Agent] Request →`.

2. **WebSocket se cierra durante el procesamiento**
   - Aumenta `--ws-ping-interval` y `--ws-ping-timeout` en el CMD del Dockerfile.backend o en uvicorn.

3. **Whisper muy lento**
   - El backend usa GPU por defecto (`device="cuda"`). Asegúrate de que el contenedor tenga acceso a la GPU (`deploy.resources` en docker-compose).

4. **Problemas con PyTorch en Windows**
   - Usa `requirements-windows.txt` con las versiones específicas para CUDA 12.1.

## 📝 Notas de Desarrollo

- El backend usa WebSockets para comunicación en tiempo real (`/ws/audio`).
- Los audios se procesan en chunks de 20 ms; VAD detecta voz/silencio (WebRTC VAD).
- La respuesta la genera el **agente externo** (AGENT_API_URL); el backend solo transcribe, reenvía y convierte la respuesta a voz (TTS).
- Manual detallado del backend: [docs/MANUAL_USO_BACKEND.md](docs/MANUAL_USO_BACKEND.md).
- Los scripts de testing se ejecutan desde la raíz del proyecto.

## 📄 Licencia

[Licencia aquí] #TODO

## 👥 Contribuidores

Mónica Montero Ceballos - Consultora de innovación 