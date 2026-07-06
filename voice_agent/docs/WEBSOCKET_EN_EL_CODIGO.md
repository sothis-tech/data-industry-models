# Dónde está la comunicación WebSocket en el código

Resumen por archivo y por responsabilidad. La ruta del WebSocket es **`/ws/audio`**.

---

## 1. Entrada: endpoint WebSocket (FastAPI)

**Dónde:** En el archivo donde se crea la app FastAPI (por ejemplo `backend/server.py` o `main.py`). Busca:

- `@app.websocket("/ws/audio")`
- `async def websocket_endpoint(websocket: WebSocket):`

Ahí se hace:

1. `await websocket.accept()` — aceptar la conexión.
2. Lectura del **primer mensaje** (timeout 2 s) para saber el modo:
   - Si llega **texto** con JSON `{"mode": "direct"}` o `{"mode": "wake_word"}`, se guarda `connection_mode`.
   - Si llega **audio** (bytes) o timeout → modo `wake_word` y ese mensaje se guarda como `initial_message`.
3. Creación de `SessionContext`, `VADManager`, etc.
4. Llamada a **`run_voice_session_loop(..., connection_mode=..., initial_message=...)`**.

Todo lo que sigue (recibir mensajes y enviar respuestas) ocurre dentro de ese bucle.

---

## 2. Recepción de mensajes del cliente

**Dónde:** Mismo archivo que el endpoint, dentro de **`run_voice_session_loop`**.

- **Tarea en segundo plano** (por ejemplo `receive_loop`):
  - Bucle que hace `message = await websocket.receive()`.
  - Cada mensaje se pone en una cola: `await queue.put(message)`.
  - Si el mensaje es **bytes** → es audio.
  - Si es **texto** y el contenido es `"__END__"` → señal de fin de frase.
  - El backend no lee otro formato de “comandos”; solo diferencia binario (audio) vs texto (`__END__` o el primer mensaje `mode`).

- **Bucle principal** del mismo `run_voice_session_loop`:
  - Lee de la cola: `msg = await queue.get()`.
  - Si `msg` tiene **`"bytes"`** → se pasa a `vad_manager.process_chunk(msg["bytes"])` (audio).
  - Si `msg.get("text") == "__END__"` → se llama a `vad_manager.force_flush()` para cortar la frase.
  - Cuando el VAD devuelve un **segmento de audio** (o el flush), según el modo:
    - **Modo direct:** se envía `status_change → "processing"`, se llama al pipeline y luego `status_change → "ready"`.
    - **Modo wake_word:** se usa el detector de palabra de activación y, si aplica, también se llama al pipeline.

Ahí está toda la **recepción** WebSocket: un único sitio que hace `websocket.receive()` y el resto del código solo interpreta lo que llega (bytes vs texto y contenido).

---

## 3. Envío al cliente (respuestas por WebSocket)

Hay dos sitios que envían JSON al cliente:

### 3.1 Estados: `status_change`

**Dónde:** Mismo archivo que el endpoint, dentro de **`run_voice_session_loop`**.

Se usa:

- `await websocket.send_json({"event": "status_change", "status": "processing"})`
- `await websocket.send_json({"event": "status_change", "status": "ready"})`
- (En modo wake_word también se envían `"waiting_wakeword"` y `"active"`.)

Es decir: **toda la comunicación de “estado”** (processing, ready, etc.) está en el bucle de sesión, no en el pipeline.

### 3.2 Transcripción y respuesta (texto + audio)

**Dónde:** `backend/command_pipeline.py`, dentro de **`run_command`**, que recibe el `websocket` como argumento.

- **Primer envío** (solo transcripción):
  ```python
  await websocket.send_json({
      "transcript": user_text,
      "response": None,
      "meta": {"session_id": session_id},
  })
  ```
  Líneas ~107–111.

- **Segundo envío** (transcripción + respuesta del agente + audio TTS):

  ```python
  await websocket.send_json({
      "transcript": user_text,
      "text": reply_text,
      "speech": reply_speech,
      "response": reply_speech,
      "audio": audio_b64,
      "data": reply_data,
      "meta": {"session_id": session_id},
  })
  ```

Quien “habla” con el cliente por WebSocket en lo que respecta a **contenido** (transcript, response, audio) es solo **`CommandPipeline.run_command`** en `command_pipeline.py`.

---

## 4. Resumen visual

```
Cliente (gafas/web)
       │
       │  WebSocket: /ws/audio
       ▼
┌──────────────────────────────────────────────────────────────┐
│  Archivo principal (p. ej. server.py)                         │
│  • @app.websocket("/ws/audio") → websocket_endpoint()        │
│  • accept()                                                   │
│  • Primer mensaje → connection_mode                           │
│  • run_voice_session_loop()                                   │
│     ├─ receive_loop():  websocket.receive() → queue           │  ◄── RECEPCIÓN
│     └─ bucle principal:                                       │
│           queue.get() → bytes → VAD / text "__END__" → flush  │
│           send_json(status_change)                            │  ◄── ENVÍO (estado)
│           pipeline.run_command(segment, ..., websocket)      │
└──────────────────────────────────────────────────────────────┘
       │
       │  websocket pasado como argumento
       ▼
┌──────────────────────────────────────────────────────────────┐
│  backend/command_pipeline.py                                 │
│  • run_command(audio, ctx, websocket)                        │
│  • send_json(transcript, response=None)                       │  ◄── ENVÍO (transcripción)
│  • send_json(transcript, text, speech, response, audio)        │  ◄── ENVÍO (respuesta + TTS)
└──────────────────────────────────────────────────────────────┘
```

---

## 5. Otros archivos relacionados

- **`backend/session.py`**: Define el estado de la sesión (`AgentState`, `SessionContext`). No usa el WebSocket; el bucle de sesión usa este estado para decidir cuándo enviar `status_change` y cuándo llamar al pipeline.
- **`backend/vad_manager.py`**: Procesa los bytes de audio (`process_chunk`, `force_flush`). No envía nada por WebSocket.
- **`scripts/test_audio_segments.py`**: Cliente de prueba que se conecta a `ws://localhost:8000/ws/audio`, envía audio y recibe JSON (`ws.recv()`). Sirve como referencia de uso del WebSocket desde fuera del backend.
- **`nginx.conf`**: Proxy de `/ws/` al backend (puerto 8000). La comunicación WebSocket pasa por ahí cuando se usa el puerto 4200.

Si en tu copia el endpoint está en otro archivo (por ejemplo `main.py`), busca `@app.websocket` o la cadena `"/ws/audio"` para localizar el punto de entrada.
