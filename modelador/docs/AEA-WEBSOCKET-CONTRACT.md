# Contrato: cliente (modelador web) ↔ agente de escucha activa (AEA)

Referencia para integrar el **front de este repositorio** con el backend WebSocket del agente de escucha activa. El AEA se desarrolló en otro proyecto (cliente **gafas** y otra web); aquí se **reutiliza** el mismo protocolo. Los detalles siguen el comportamiento descrito en el README/código del backend del AEA (`server.py`, `command_pipeline.py`, `vad_manager`, etc.) — las líneas exactas pueden cambiar entre versiones del agente.

**Relación con otros documentos:** autorización global (Keycloak, Kong, JWT) → [INTEGRATION-PLAN.md](INTEGRATION-PLAN.md) épica B. El tramo **backend AEA → agente LLM (HTTP)** está documentado más abajo solo para contexto; el **modelador** en principio solo habla por **WebSocket** con el AEA.

---

## 1. Autenticación (pendiente / preventiva)

La capa de seguridad la define el compañero owner (Keycloak/Kong). Hasta que exista el flujo cerrado, se puede ir reservando:

| Campo / mecanismo | Uso probable | Notas |
|-------------------|---------------|--------|
| `user_id` | Correlacionar sesión de voz con usuario en Keycloak | Mismo identificador que claim `sub` o id interno acordado |
| Tenants / scopes | Limitar qué datos Orion o qué `client_id`/`level_id` usa el agente interno | Alinear con claims JWT o lista en `meta` del handshake |
| Tokens | `Authorization: Bearer <JWT>` en upgrade WebSocket, query `?token=`, o cookie — **lo define Kong + Keycloak** | Validar con C2 si el WS pasa por Kong (subprotocolos, timeouts) |

**Primer mensaje opcional (vista al futuro):** si el equipo AEA amplía el JSON inicial, es natural añadir campos junto a `mode`, por ejemplo:

```json
{
  "mode": "direct",
  "user_id": "<string>",
  "tenant_ids": ["<id1>", "<id2>"]
}
```

(o un único `"tenant_id"`). Esto **no** está hoy en el contrato estricto original; hay que acordarlo entre quien mantiene `server.py` del AEA y quien define auth (épica B). Mientras tanto, el backend del AEA puede seguir usando `user_id: "unknown"` hacia el agente LLM.

---

## 2. Mensajes cliente → servidor (WebSocket, request)

### 2.1 Orden y tipos

| Orden | Tipo de mensaje | Contenido | Comportamiento |
|-------|-----------------|------------|----------------|
| 1.º (opcional, en los **primeros 2 s**) | **Texto** (JSON) | Objeto con un único campo `mode`. Valores: `"direct"` o `"wake_word"`. | Si no llega a tiempo o llega audio primero → el servidor asume `wake_word`. |
| Después | **Binario** | Audio **PCM 16-bit LE, mono** (chunks). | Procesado por VAD en el servidor. |
| Fin de frase | **Texto** (string plano, no JSON) | Exactamente: `__END__` | Cierra el turno de usuario. |

**Ejemplo primer mensaje (modo similar a gafas, control directo):**

```json
{"mode": "direct"}
```

Reglas:

- Debe ser el **primer** mensaje dentro de **2 segundos** desde la apertura del WebSocket.
- No añadir otros campos si el backend actual **solo** valida `mode` (salvo ampliación acordada; ver §1).

**Fin de frase:** enviar mensaje de texto cuyo contenido sea exactamente la cadena `__END__` (en el wire como texto, no como JSON con comillas escapadas incorrectamente).

---

## 3. Mensajes servidor → cliente (WebSocket, response)

Todos son **JSON en texto** WebSocket. Interpretación según presencia de `event`, o de `transcript` / `response`.

### 3. A) Eventos de estado (modo direct: típicos)

```json
{"event": "status_change", "status": "processing"}
```

```json
{"event": "status_change", "status": "ready"}
```

- **`processing`:** transcribiendo, llamando al agente / generando TTS. No enviar más audio hasta nueva fase coherente según implementación.
- **`ready`:** listo para nuevo audio o nuevo `__END__`.

### 3. A.1) Ruido descartado (modo direct)

Si con `__END__` no hay segmento de voz válido (VAD):

```json
{"event": "ignored_noise", "message": "Audio descartado por VAD del servidor"}
```

Luego el servidor suele volver a `status: "ready"`. Tras varios descartes puede generarse respuesta hablada tipo *"No se detectó voz."* (véase §3. D).

### 3. B) Transcripción sola (primer JSON de respuesta del turno)

Tras transcribir, **antes** de la respuesta completa del agente:

```json
{
  "transcript": "<texto transcrito>",
  "response": null,
  "meta": {"session_id": "<uuid corto>"}
}
```

`response` es `null` en este mensaje.

### 3. C) Respuesta completa (transcripción + agente + opcional TTS)

```json
{
  "transcript": "<mismo texto que en el mensaje anterior>",
  "response": "<texto para mostrar o speech limpio>",
  "audio": "<base64 WAV>" | null,
  "data": {},
  "meta": {"session_id": "<uuid corto>"}
}
```

| Campo | Significado típico |
|-------|-------------------|
| `transcript` | Lo que entró como voz (Whisper/servidor). |
| `response` | En **web modelo gafas / direct**, texto limpio del **speech** (lo que muestra Piper); no es el Markdown largo del LLM. |
| `audio` | WAV en Base64 desde TTS (**Piper**), o `null` si no hubo TTS o falló. |
| `data` | JSON opcional para UI (gráficos, etc.); reenvío de lo que devuelve el agente Activos cuando aplica. |
| `meta.session_id` | Misma sesión que en mensajes previos del turno. |

### 3. D) Sin voz detectada (modo direct)

Cuando todo el audio fue ruido y no hay transcript útil tras `__END__`:

```json
{
  "transcript": "",
  "response": "No se detectó voz.",
  "audio": null,
  "meta": {"session_id": "<uuid corto>"}
}
```

Mostrar `response` al usuario y no reproducir audio. Suele seguir `status_change` → `ready`.

---

## 4. Cadena backend AEA ↔ agente LLM (HTTP — contexto solo)

Este flujo ocurre **dentro del servidor del AEA**; el cliente del **modelador** no llama aquí salvo diseño futuro (BFF). Sirve para alinear payloads con `user_id`, `session_id`, `client_id`, `level_id`.

### 4.1 Petición (AEA backend → agente Activos)

- **Método:** `POST`
- **Cuerpo JSON:**

```json
{
  "request_id": "<uuid-v4>",
  "session_id": "<string>",
  "user_id": "<string>",
  "client_id": "<string>",
  "level_id": "<string>",
  "input_text": "<transcripción Whisper>",
  "modality": "speech"
}
```

`modality` puede ser `"speech"` | `"text"`.

Valores por defecto habituales si no hay identidad aún: `user_id` como `"unknown"`, `client_id` / `level_id` como `"default_client"` / `"default_level"` (ajustar cuando exista mapeo tenant/planta).

### 4.2 Respuesta (agente Activos → AEA backend)

```json
{
  "request_id": "<mismo uuid>",
  "status": "success",
  "error_code": "",
  "error_message": "",
  "response": {
    "speech": "<texto limpio para Piper TTS>",
    "text": "<markdown o texto para pantalla>",
    "data": {}
  }
}
```

En error: `status: "error"` y campos `error_code` / `error_message` rellenos.

- El **backend AEA** convierte `response.speech` en audio Piper y rellena el **WebSocket** `audio` (Base64 WAV) y el `response` que ve el cliente según tipo de cliente (gafas vs web).

---

## 5. Implicaciones para el front del modelador (React)

1. **WebSocket:** abrir con URL y estrategia de auth acordada (énfica B).
2. **Audio:** captura → resample/formato PCM 16 LE mono si hace falta en el navegador; enviar chunks binarios y `__END__` al terminar la frase.
3. **Estado UI:** reaccionar a `status_change`, `ignored_noise`, mensajes con `transcript`/`response`/`audio`, y errores de conexión.
4. **Auth preventiva:** guardar variables de sesión (`user_id`, tenants) disponibles cuando existan en el SPA para rellenar el futuro handshake (§1).

---

## 6. Referencias cruzadas

- [INTEGRATION-PLAN.md](INTEGRATION-PLAN.md) — dependencias Azure, Kong, Keycloak.
- [LOGGING.md](LOGGING.md) — logs JSON en API y cliente (útil para depurar WS y proxy).
