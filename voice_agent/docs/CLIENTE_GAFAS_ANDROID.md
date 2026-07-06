# Cliente de gafas AR (Android / Java)

Especificación del **cliente de gafas** (app Android en Java) que se conecta al backend del voice agent. El dispositivo de gafas tiene **detección propia de palabra de activación**; el backend no la detecta. Por eso el cliente debe usar el **modo "direct"**.

---

## 1. Resumen

- El **cliente de gafas** se conecta por **WebSocket** al backend (voice agent).
- Tras conectar, envía **un mensaje de texto** indicando modo directo.
- Cuando detecta su palabra de activación, envía **audio en bruto** (PCM).
- El **backend** transcribe, llama al Agente Activos (LLM) por HTTP y devuelve al cliente **texto y audio** (TTS) por WebSocket.

### Actividad por componente

| Componente | Se comunica con | Descripción |
|------------|------------------|-------------|
| **Cliente de gafas** | Backend (voice agent) | WebSocket: envía `{"mode":"direct"}`, audio y `__END__`; recibe `status_change`, `transcript`, `response`, `audio`, `data`. |
| **Backend** | Cliente de gafas (y cliente web) | WebSocket con el mismo contrato (sección 3). |
| **Backend** | Agente Activos (LLM) | HTTP POST con el contrato de la sección 7; obtiene texto para pantalla y texto para TTS. |

El **cliente de gafas** no implementa el contrato con el LLM: no envía peticiones al Agente Activos ni recibe su respuesta. El backend realiza el POST al LLM; el cliente de gafas recibe por WebSocket solo el resultado ya procesado. En modo direct, el campo `response` es el **speech** del agente (texto limpio); el campo `audio` es el TTS generado por el backend a partir de ese mismo speech. El contrato del LLM (sección 7) se incluye como **referencia** del origen de esos datos.

---

## 2. URL del WebSocket

- Conexión **directa al backend**:  
  `ws://<IP-del-servidor>:8000/ws/audio`
- Conexión vía **proxy** (mismo origen que la web):  
  `ws://<IP-del-servidor>:4200/ws/audio`  
  (puerto 4200 hace de proxy al 8000)

`<IP-del-servidor>`: IP o dominio donde corre el voice agent.

---

## 3. Contrato estricto (según el código del backend)

Los siguientes formatos son los que usa el backend. 

### 3.1 Mensajes cliente → servidor (request)

| Orden | Tipo de mensaje | Contenido exacto | Referencia en código |
|-------|-----------------|------------------|----------------------|
| 1º (opcional, en los primeros 2 s) | **Texto** (JSON) | Objeto con un único campo `mode`. Valores permitidos: `"direct"` o `"wake_word"`. | `server.py`: `data.get("mode") in ("direct", "wake_word")` |
| Después | **Binario** | Bytes de audio: PCM 16 bits little-endian, mono. | `vad_manager.process_chunk(msg["bytes"])` |
| Para indicar fin de frase | **Texto** (string plano) | Exactamente la cadena `__END__` (sin JSON). | `server.py`: `msg.get("text") == "__END__"` |

**Ejemplo de primer mensaje (modo gafas):**

```json
{"mode": "direct"}
```

- Debe ser el **primer** mensaje y llegar en un plazo de **2 segundos** tras abrir el WebSocket. Si lo primero que llega es audio o no llega nada, el backend usa `wake_word`.
- No incluir otros campos; el backend solo lee `mode`.

**Fin de frase:**

- Mensaje de **texto** (no binario) con el contenido literal: `__END__` (en el wire, string sin comillas; en Java se envía la string `"__END__"`).

### 3.2 Mensajes servidor → cliente (response)

Todos los mensajes del servidor son **texto** (JSON). Distinguir por la presencia del campo `event` o de `transcript`/`response`.

#### A) Cambio de estado (modo direct: solo estos dos)

Forma exacta:

```json
{"event": "status_change", "status": "processing"}
```

```json
{"event": "status_change", "status": "ready"}
```

- `processing`: el backend está transcribiendo, llamando al agente o generando TTS. No enviará más mensajes de estado hasta terminar.
- `ready`: ha terminado; puede recibir más audio (o `__END__` para la siguiente frase).

Definido en `server.py` (líneas 156 y 159 para modo direct).

#### A.1) Ruido descartado (modo direct)

Cuando el backend recibe `__END__` pero no obtiene un segmento valido de voz (filtrado por VAD), puede enviar:

```json
{"event": "ignored_noise", "message": "Audio descartado por VAD del servidor"}
```

- En configuracion `hybrid` (recomendada): primero envia `ignored_noise` para no interrumpir al usuario.
- Si el descarte se repite durante varios intentos o tiempo acumulado, el backend vuelve a enviar la respuesta hablada `"No se detecto voz."`.
- Despues de `ignored_noise`, el backend envia `{"event":"status_change","status":"ready"}`.

#### B) Transcripción (primer JSON de respuesta por comando)

Enviado justo después de transcribir, **antes** de la respuesta del agente:

```json
{
  "transcript": "<texto transcrito del usuario>",
  "response": null,
  "meta": {"session_id": "<uuid corto>"}
}
```

- `response` es siempre `null` en este mensaje.  
Definido en `command_pipeline.py` (primer `send_json`).

#### C) Respuesta completa (transcript + agente + TTS)

Enviado cuando el agente ha respondido y se ha generado el TTS (si aplica):

```json
{
  "transcript": "<texto transcrito del usuario>",
  "text": "<markdown / texto de chat del agente>",
  "speech": "<speech del agente (texto limpio para TTS)>",
  "response": "<igual que speech>",
  "audio": "<base64 del WAV>" | null,
  "data": {},
  "meta": {"session_id": "<uuid corto>"}
}
```

- `transcript`: mismo que en el mensaje anterior.
- `text`: texto enriquecido del agente (p. ej. markdown). El cliente de **gafas** puede ignorarlo si solo usa la vía corta.
- `speech`: guion TTS; el backend genera `audio` a partir de este campo.
- `response`: **igual que `speech`** (alias para apps que históricamente solo leían `response`).
- `audio`: string Base64 del WAV (PCM) de la voz, o `null` si no hubo TTS o falló.
- `data`: objeto JSON opcional con payload estructurado devuelto por el agente (por ejemplo, datos de gráfico).
- `meta.session_id`: mismo que en el mensaje de transcripción.

Definido en `command_pipeline.py` (segundo `send_json`).

#### D) Sin voz detectada (solo en modo direct)

Cuando el cliente envía `__END__` y el backend no tiene ningún segmento de voz (todo el audio se descartó como ruido), envía este JSON para que la app pueda mostrar un mensaje y no quede esperando:

```json
{
  "transcript": "",
  "response": "No se detectó voz.",
  "audio": null,
  "meta": {"session_id": "<uuid corto>"}
}
```

A continuación el backend envía `{"event": "status_change", "status": "ready"}`. El cliente puede mostrar `response` (por ejemplo "No se detectó voz.") y no intentar reproducir `audio`.

---

## 4. Secuencia de mensajes (resumen)

1. **Al conectar:** En los primeros 2 s, el cliente envía **un mensaje de texto** con `{"mode": "direct"}` (sin otros campos).
2. **Durante el habla:** El cliente envía **audio en bruto** en mensajes **binarios** (PCM 16 bits mono; p. ej. 16 kHz o 48 kHz; chunks de ~20 ms para que el backend infiera el sample rate).
3. **Fin de frase:** El cliente envía mensaje de **texto** con contenido exacto `__END__`.
4. **Mensajes entrantes:** El cliente parsea JSON. Si existe `event` → `status_change` con `status` `"processing"` o `"ready"`. Si existe `transcript` y `response === null` → solo transcripción. Si existe `transcript`, `response` (string), `audio` y `data` → respuesta completa: mostrar texto y reproducir `audio` (Base64 → WAV) si no es `null`; usar `data` para payload estructurado (p. ej. gráfico). Si `transcript === ""` y `response === "No se detectó voz."` y `audio === null` → mostrar ese mensaje (sin reproducir) y esperar `ready`.

---

## 5. Implementación en Android / Java

### 5.1 Librería WebSocket

Librerías WebSocket habituales en Android:

- **OkHttp** (incluye soporte WebSocket):  
  [https://square.github.io/okhttp/](https://square.github.io/okhttp/)
- **Java-WebSocket**:  
  [https://github.com/TooTallNate/Java-WebSocket](https://github.com/TooTallNate/Java-WebSocket)

### 5.2 Flujo del cliente

1. Abrir conexión WebSocket a `ws://<host>:8000/ws/audio` (o 4200 si se usa proxy).
2. En el callback de conexión abierta, enviar **en menos de 2 s** el mensaje de texto:  
   `{"mode": "direct"}` (sin otros campos).
3. Tras detectar la palabra de activación en el dispositivo: capturar audio PCM 16 bits mono y enviar chunks como **mensajes binarios**.
4. Al terminar el habla: enviar mensaje de **texto** con contenido exacto `__END__`.
5. En el handler de mensajes entrantes: parsear JSON; si tiene `event` → tratar como `status_change` (`processing` / `ready`); si tiene `transcript`, `response` (string), `audio` y `data` → mostrar `response`, reproducir `audio` (Base64 → WAV) si no es `null`, y consumir `data` (payload estructurado, p. ej. gráfico). El mensaje con `response: null` es solo transcripción intermedia.

### 5.3 Formato del audio enviado por el cliente

- **Codificación:** PCM lineal 16 bits little-endian, mono.
- **Sample rate:** 16000 Hz o 48000 Hz. El backend infiere el rate del tamaño del primer chunk asumiendo 20 ms (`vad_manager.py`: `source_sample_rate = samples_per_frame / 0.02`). Chunks de ~20 ms para que la detección sea correcta.
- **Ejemplo 16 kHz, 20 ms:** 320 muestras × 2 bytes = **640 bytes** por chunk.

En Java, el `byte[]` obtenido del `AudioRecord` se envía tal cual por el WebSocket como frame binario.

---

## 6. Resumen rápido (checklist cliente)

| Paso | Acción del cliente |
|------|--------------------|
| 1 | Conectar WebSocket a `ws://<servidor>:8000/ws/audio`. |
| 2 | En &lt; 2 s, enviar **texto** `{"mode": "direct"}` (solo ese campo). |
| 3 | Enviar **audio binario** (PCM 16 bits mono, chunks ~20 ms). |
| 4 | Al terminar el habla, enviar **texto** `__END__`. |
| 5 | Recibir JSON: `event` + `status` → estado; `transcript` + `response` (null = solo transcripción; string + `audio` + `data`) → mostrar, reproducir y usar payload estructurado. |

Los formatos exactos de request y response están definidos en la **sección 3** según el código del backend (`backend/server.py`, `backend/command_pipeline.py`).

---

## 7. Contrato con el Agente Activos (LLM) — referencia

Este contrato lo usa **solo el backend** para comunicarse con el Agente Activos (HTTP). **El cliente de gafas no envía ni recibe este JSON.** Se incluye como referencia: el backend recibe `text` y `speech` del LLM y en el WebSocket envía **`text`**, **`speech`** y **`response`** (este último duplicado de `speech` para compatibilidad con clientes que solo leen `response`).

Implementación en el backend: `backend/services/agent_service.py`.

### 7.1 Petición (Backend → Agente Activos)

- **Protocolo:** HTTP POST.
- **Cuerpo (JSON):**

```json
{
  "request_id": "uuid-v4",
  "session_id": "string",
  "user_id": "string",
  "client_id": "string",
  "level_id": "string",
  "input_text": "string",
  "modality": "speech" | "text"
}
```

- `request_id`: UUID generado por el backend.
- `session_id`: ID de la sesión WebSocket (persistente para el usuario).
- `user_id`: Identificador del usuario (hoy el backend puede usar `"unknown"` si no se pasa).
- `client_id`, `level_id`: Definición cliente/planta (en el código hay valores por defecto `"default_client"` / `"default_level"`).
- `input_text`: Transcripción de Whisper (lo que el usuario dijo).
- `modality`: `"speech"` o `"text"` según el origen del request.

### 7.2 Respuesta (Agente Activos → Backend)

- **Protocolo:** JSON en el cuerpo de la respuesta HTTP.

```json
{
  "request_id": "uuid-v4",
  "status": "success" | "error",
  "error_code": "",
  "error_message": "",
  "response": {
    "speech": "string",
    "text": "string",
    "data": {}
  }
}
```

- `request_id`: Mismo que en la petición (correlación).
- `status`: `"success"` o `"error"`.
- `error_code`, `error_message`: Rellenos cuando `status === "error"`.
- `response.speech`: Texto limpio para Piper TTS → el backend lo convierte en el campo `audio` (Base64 WAV) que el cliente recibe por WebSocket.
- `response.text`: Texto/Markdown para pantalla → el backend lo reenvía en el campo **`text`** del WebSocket. El cliente de gafas que solo mire **`response`** verá el **speech** (porque `response` === `speech` en el JSON WebSocket).
- `response.data`: Opcional, datos extra; el backend lo reenvía al cliente en el campo `data` del mensaje WebSocket.

**Resumen:** El cliente de gafas utiliza únicamente el contrato WebSocket (sección 3). El backend realiza la cadena voz → Whisper → POST al Agente Activos → respuesta del agente → Piper → y devuelve al cliente `transcript`, `text`, `speech`, `response` (= `speech`), `audio` y `data` por WebSocket.
