# Manual de uso del backend (Voice Agent)

Guía rápida para usar el servicio de backend del agente de voz.

---

## 1. ¿Qué hace el backend?

- **Escucha por WebSocket** en el puerto 8000 (`/ws/audio`).
- Detecta la **palabra de activación** (por defecto: "marvin").
- **Transcribe** tu voz con Whisper.
- Envía el texto al **agente externo** (servicio de control de activos en la URL configurada en `AGENT_API_URL`).
- Genera **audio de respuesta** (TTS) con Piper y lo devuelve al frontend.

**Requisitos:** Docker, GPU NVIDIA (para Whisper y TTS). El **agente externo** debe estar levantado y accesible en la URL que configures en `AGENT_API_URL` (por ejemplo en el host en el puerto 8081).

---

## 2. Levantar el servicio

### Con Docker Compose (recomendado)

```bash
cd /ruta/al/voice_agent

# Copiar y editar la configuración (solo la primera vez)
cp config.env.example config.env
# Editar config.env (wake word, AGENT_API_URL, etc.)

# Levantar backend + frontend
docker compose up -d

# Ver que estén activos
docker compose ps
```

- **Backend:** http://localhost:8000  
- **Frontend:** http://localhost:4200  

### Solo el backend

```bash
docker compose up -d backend
```

---

## 3. Cómo usarlo

1. Abre el **frontend** en el navegador: **http://localhost:4200**
2. Permite el uso del **micrófono** cuando el navegador lo pida.
3. Di la **palabra de activación** (por defecto: **"Marvin"**) seguida de tu pregunta o comando.  
   Ejemplo: *"Marvin, ¿cuándo es la próxima inspección?"*
4. El backend transcribe, consulta al agente externo, genera la respuesta en voz y la escuchas en el navegador.

No hace falta enviar peticiones HTTP a mano para el uso normal; todo va por WebSocket desde el frontend.

---

## 4. Configuración principal (`config.env`)

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `LOG_LEVEL` | Nivel de log (DEBUG, INFO, WARNING) | `DEBUG` |
| `WAKE_WORD` | Palabra de activación | `marvin` |
| `WAKE_WORD_ALIASES` | Variantes aceptadas (separadas por coma) | `marby,martin,marlin` |
| `ACTIVE_TIMEOUT_SEC` | Segundos sin hablar antes de "dormir" | `8.0` |
| `WHISPER_LANG` | Idioma para transcripción | `es` |
| `AGENT_API_URL` | **URL del agente externo (obligatoria)** | `http://host.docker.internal:8081/api/chat` |

El backend **siempre** envía la transcripción al agente externo. Tienes que configurar `AGENT_API_URL` con la URL del servicio de control de activos (por ejemplo en el host en el puerto 8081). Si no está configurada o el agente no responde, el usuario oirá un mensaje de error de conexión.

Después de cambiar `config.env`, reinicia el backend:

```bash
docker compose restart backend
```

---

## 5. Comandos útiles

| Acción | Comando |
|--------|--------|
| Ver logs del backend en tiempo real | `docker compose logs -f backend` |
| Ver últimas 100 líneas de log | `docker compose logs --tail=100 backend` |
| Reiniciar solo el backend | `docker compose restart backend` |
| Parar todo | `docker compose down` |
| Ver contenedores activos | `docker ps` o `docker compose ps` |

---

## 6. Comprobar que todo está bien

- **Backend responde:**  
  `curl -s http://localhost:8000/docs`  
  (debería devolver la página de Swagger/OpenAPI.)

- **WebSocket:**  
  El frontend en http://localhost:4200 se conecta solo; si ves "WebSocket conectado" en la consola del navegador, el backend está aceptando conexiones.

- **Agente externo:**  
  En los logs del backend deberías ver líneas tipo `[Agent] Request → ...` y `[Agent] Response ← ...`. Si aparecen errores de conexión, revisa que el servicio en `AGENT_API_URL` esté levantado y accesible desde el contenedor (por ejemplo con `host.docker.internal` si está en el host).

---

## 7. Resumen rápido

```bash
# Levantar
docker compose up -d

# Usar
# Abrir http://localhost:4200 y decir "Marvin, <tu pregunta>"

# Logs
docker compose logs -f backend

# Parar
docker compose down
```

Si algo falla, revisa primero los logs del backend (`docker compose logs -f backend`) y que `config.env` exista con `AGENT_API_URL` apuntando al agente de control de activos en marcha.
