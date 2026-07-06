# Cliente Web — Contrato WebSocket

Especificación del **cliente web** que se conecta al backend del voice agent. A diferencia del cliente de gafas, el cliente web **no tiene detección propia de palabra de activación**: el backend detecta la wake word en el audio continuo que el cliente le envía.

---

## 1. Resumen

- El cliente web se conecta por **WebSocket** al backend (`/ws/audio`).
- Envía **audio continuo** (PCM) mientras el usuario habla o espera.
- El backend detecta la **palabra de activación** ("Marvin" por defecto) y, al oírla, pasa a estado activo para escuchar el comando.
- El backend devuelve **eventos de estado**, **transcripción** y la respuesta del agente con **`text`** (chat / markdown), **`speech`** (guion TTS) y **`response`** (igual que `speech`, alias útil para clientes legacy).
- El **modelador** debe mostrar **`text`** en el chat; **`response` no es el texto enriquecido** en la implementación actual.

### Actividad por componente

| Componente | Se comunica con | Descripción |
|------------|-----------------|-------------|
| **Cliente web** | Backend (voice agent) | WebSocket: envía audio binario continuo; recibe `status_change`, `transcript`, `text`, `speech`, `response`, `audio`. |
| **Backend** | Cliente web | Detecta wake word, transcribe, llama al LLM y devuelve respuesta. |
| **Backend** | Agente LLM | HTTP POST (interno al backend; el cliente web no interviene). |

---

## 2. URL del WebSocket

- Conexión vía **proxy** (recomendado para web, mismo origen):
  `ws://<IP-del-servidor>:4200/ws/audio`
- Conexión **directa al backend**:
  `ws://<IP-del-servidor>:8000/ws/audio`

---

## 3. Contrato estricto (según el código del backend)

### 3.1 Mensajes cliente → servidor

| Orden | Tipo | Contenido | Referencia en código |
|-------|------|-----------|----------------------|
| 1º (opcional, ≤ 2 s) | **Texto** (JSON) | `{"mode": "wake_word"}` — puede omitirse; es el comportamiento por defecto. | `server.py`: `data.get("mode")` |
| Continuo | **Binario** | Bytes de audio: PCM 16 bits little-endian, mono, 16000 Hz o 48000 Hz, chunks de ~20 ms. | `vad_manager.process_chunk(msg["bytes"])` |
| Fin de frase (opcional) | **Texto** | `__END__` (string plano, sin JSON). Fuerza el flush del VAD si hay audio pendiente. | `server.py`: `msg.get("text") == "__END__"` |

> En modo web **no es obligatorio** enviar `__END__`; el VAD detecta el silencio solo tras `SILENCE_WAIT_MS` ms (por defecto 2000 ms). `__END__` sirve para forzar el corte antes del silencio.

**Primer mensaje (si se envía):**

```json
{"mode": "wake_word"}
```

Si el primer mensaje es audio directamente, el backend también asume `wake_word`.

### 3.2 Mensajes servidor → cliente

Todos los mensajes del servidor son **texto** (JSON).

#### A) Cambios de estado (`event: status_change`)

El campo `status` puede tomar estos valores en modo web:

| `status` | Significado |
|----------|-------------|
| `"waiting_wakeword"` | Escuchando; esperando que el usuario diga la wake word. Estado inicial y de reposo. |
| `"active"` | Wake word detectada; el backend escucha ahora el **comando** del usuario. |
| `"processing"` | Procesando: transcribiendo, consultando al agente, generando TTS. |
| `"waiting_wakeword"` | (de nuevo) Tras responder, vuelve a esperar wake word. |

Forma exacta:

```json
{"event": "status_change", "status": "waiting_wakeword"}
```
```json
{"event": "status_change", "status": "active"}
```
```json
{"event": "status_change", "status": "processing"}
```

#### B) Transcripción (primer JSON de respuesta por comando)

Enviado justo tras transcribir, antes de tener la respuesta del agente:

```json
{
  "transcript": "<texto transcrito del usuario>",
  "response": null,
  "meta": {"session_id": "<uuid corto>"}
}
```

- `response` es siempre `null` en este mensaje.

#### C) Respuesta completa

Enviado cuando el agente ha respondido y se ha generado TTS:

```json
{
  "transcript": "<texto transcrito del usuario>",
  "text": "<markdown / texto de chat del agente>",
  "speech": "<guion TTS (puede coincidir con text si el agente no los separa)>",
  "response": "<igual que speech>",
  "audio": "<base64 del WAV>" | null,
  "data": {},
  "meta": {"session_id": "<uuid corto>"}
}
```

- `transcript`: lo que el usuario dijo.
- `text`: campo **`text`** del agente (pantalla / chat enriquecido).
- `speech`: campo **`speech`** del agente (TTS; el audio se genera con este texto).
- `response`: duplicado de `speech` por compatibilidad con clientes que solo leen este campo; **no usar como sustituto de `text`** en el modelador web.
- `audio`: Base64 del WAV PCM generado por TTS, o `null` si no se generó.
- `meta.session_id`: identificador de la sesión (consistente durante toda la conexión).

---

## 4. Flujo completo (máquina de estados)

```
Conectar WebSocket
        │
        ▼
[waiting_wakeword] ◄────────────────────────────────────────┐
        │                                                    │
        │  VAD detecta segmento de audio                     │
        ▼                                                    │
  ¿Se escucha la wake word?                                  │
        │                                                    │
   Sí ──┼── Con comando inmediato ──► [processing] ──────────┤
        │   (p.ej. "Marvin, pon la calefacción")             │
        │                                                    │
        └── Solo wake word ──► [active]                      │
                │                                            │
                │  VAD detecta siguiente segmento            │
                ▼                                            │
           [processing]                                      │
                │                                            │
                │  Transcripción + Agente + TTS              │
                ▼                                            │
          Envía transcript + response + audio ───────────────┘
```

> Si pasan `ACTIVE_TIMEOUT_SEC` segundos (por defecto 8 s) en estado `active` sin detectar audio, el backend vuelve solo a `waiting_wakeword` y envía el evento correspondiente.

---

## 5. Secuencia de mensajes paso a paso

1. **Al conectar:** Opcionalmente enviar `{"mode": "wake_word"}` en los primeros 2 s (o no enviar nada).
2. **Audio continuo:** Enviar chunks de audio binario (~20 ms, PCM 16 bits mono) mientras el micrófono está activo.
3. **Recibir `waiting_wakeword`:** El cliente puede mostrar un indicador de "esperando wake word".
4. **Recibir `active`:** El backend oyó la wake word. Mostrar indicador de "escuchando comando".
5. **Recibir `processing`:** El backend está procesando. Mostrar indicador de carga.
6. **Recibir transcript con `response: null`:** Mostrar la transcripción del usuario en la UI.
7. **Recibir respuesta completa** (`text` para pantalla; `audio` para TTS; `response`/`speech` son el guion de voz): Mostrar **`text`** y reproducir el audio (Base64 → WAV).
8. **Recibir `waiting_wakeword`:** Vuelve al estado de reposo; ocultar indicadores activos.

---

## 6. Formato del audio enviado por el cliente

- **Codificación:** PCM lineal 16 bits little-endian, mono.
- **Sample rate:** 16000 Hz o 48000 Hz.
- **Tamaño de chunk:** ~20 ms → 640 bytes a 16 kHz (320 muestras × 2 bytes) o 1920 bytes a 48 kHz (960 muestras × 2 bytes).

El backend infiere el sample rate del tamaño del primer chunk asumiendo frames de 20 ms (`vad_manager.py`).

---

## 7. Checklist rápido (cliente web)

| Paso | Acción |
|------|--------|
| 1 | Conectar WebSocket a `ws://<servidor>:4200/ws/audio`. |
| 2 | (Opcional) Enviar texto `{"mode": "wake_word"}` en < 2 s. |
| 3 | Enviar audio binario continuo (PCM 16 bits mono, chunks ~20 ms). |
| 4 | `status: "waiting_wakeword"` → mostrar estado de espera. |
| 5 | `status: "active"` → mostrar estado escuchando comando. |
| 6 | `status: "processing"` → mostrar spinner/cargando. |
| 7 | `transcript` con `response: null` → mostrar transcripción del usuario. |
| 8 | `transcript` + `text` + `speech`/`response` + `audio` → mostrar **`text`**, reproducir audio. |
| 9 | `status: "waiting_wakeword"` → volver al estado de reposo. |

---

## 8. Diferencias clave respecto al cliente de gafas

| Aspecto | Cliente web (`wake_word`) | Cliente gafas (`direct`) |
|---------|--------------------------|--------------------------|
| Detección de wake word | El **backend** la detecta en el audio | El **dispositivo** la detecta; el backend no |
| Primer mensaje | `{"mode": "wake_word"}` o nada | `{"mode": "direct"}` (obligatorio en < 2 s) |
| Estados recibidos | `waiting_wakeword`, `active`, `processing` | `processing`, `ready` |
| Campo `text` | **`text`** del agente (markdown en chat) | Igual (también se envía en direct) |
| Campo `response` | No usar como principal; es **`speech`** (alias) | **Speech** del agente (= `response`) |
| `__END__` | Opcional (el VAD corta solo por silencio) | Recomendado para señalar fin de frase |
| Audio continuo | Sí (siempre enviando) | Solo mientras el usuario habla |
