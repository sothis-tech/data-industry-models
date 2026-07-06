import os
import uuid
import json
import asyncio
import logging
import traceback
from typing import Literal

import numpy as np
import soundfile as sf
import webrtcvad
import whisper

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from backend.wakeword import WhisperWakeWordDetector
from backend.tts_service import TTSService
from backend.services.agent_service import AgentService
from backend.session import AgentState, SessionContext
from backend.vad_manager import VADManager
from backend.config import config
from backend.command_pipeline import CommandPipeline

# =========================
# Logging
# =========================
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.DEBUG),
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
)
log = logging.getLogger("realtime-backend")

os.makedirs(config.DEBUG_AUDIO_DIR, exist_ok=True)

# =========================
# Models
# =========================
log.info("Cargando modelo Whisper...")
import torch
_device = "cuda" if torch.cuda.is_available() else "cpu"
if _device == "cpu":
    log.warning("CUDA no disponible (driver/runtime). Cargando Whisper en CPU (más lento).")
else:
    log.info("CUDA disponible. Cargando Whisper en GPU.")
model = whisper.load_model("medium", device=_device)
log.info("Whisper cargado en %s.", _device)

# Inicializar Servicio TTS (modelos fuera de backend para no ser ocultados por volumen Docker)
TTS_MODEL_PATH = os.path.join(config.get_tts_models_dir(), "es_ES-sharvard-medium.onnx")
tts_service = TTSService(TTS_MODEL_PATH)

# Inicializar Servicio de Agente (Cliente HTTP)
agent_service = AgentService(config.AGENT_API_URL)

# Inicializar VAD con modo configurable
vad = webrtcvad.Vad(config.VAD_MODE)

# Inicializar detector de Wake Word
wakeword_detector = WhisperWakeWordDetector(
    model, config.WAKE_WORD, config.WHISPER_LANG, aliases=config.WAKE_WORD_ALIASES
)

# Pipeline: transcribir → agente → TTS → WebSocket
pipeline = CommandPipeline(
    model,
    agent_service,
    tts_service,
    target_sr=config.TARGET_SR,
    whisper_lang=config.WHISPER_LANG,
    log=log,
)

log.info("Configuración de detección de voz:")
log.info("  MIN_RMS: %.4f", config.MIN_RMS)
log.info("  MIN_VOICE_SEC: %.2f s", config.MIN_VOICE_SEC)
log.info("  SILENCE_WAIT_MS: %d ms", config.SILENCE_WAIT_MS)
log.info("  VAD_MODE: %d (0=menos agresivo, 3=más agresivo)", config.VAD_MODE)
log.info("  WHISPER_LANG: %s", config.WHISPER_LANG)
log.info(
    "  WAKE_WORD_ALIASES: %s (from %s)",
    config.WAKE_WORD_ALIASES,
    "env" if config.ALIASES_FROM_ENV else "default",
)

# =========================
# FastAPI
# =========================
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _modelador_service_headers(websocket: WebSocket) -> dict[str, str]:
    """Headers TO-BE recibidos del modelador y propagados al MCP."""
    allowed = (
        "authorization",
        "ngsild-tenant",
        "x-modelador-kong-url",
        "x-modelador-tenant",
    )
    headers: dict[str, str] = {}
    for name in allowed:
        value = websocket.headers.get(name)
        if value:
            canonical = "-".join(part.capitalize() for part in name.split("-"))
            if name == "ngsild-tenant":
                canonical = "NGSILD-Tenant"
            headers[canonical] = value
    return headers


# =========================
# WebSocket: bucle de sesión de voz
# =========================
async def run_voice_session_loop(
    websocket: WebSocket,
    session_id: str,
    ctx: SessionContext,
    vad_manager: VADManager,
    *,
    wakeword_detector,
    pipeline: CommandPipeline,
    target_sr: int,
    log: logging.Logger,
    connection_mode: Literal["wake_word", "direct"] = "wake_word",
    initial_message: dict | None = None,
) -> None:
    """
    Bucle principal de una sesión WebSocket de voz.
    - wake_word: detecta palabra de activación en el audio (web).
    - direct: todo el audio se trata como comando (p. ej. gafas AR con wake word propio).
    """
    queue = asyncio.Queue()
    no_voice_streak_count = 0
    no_voice_streak_start_ts: float | None = None
    if initial_message is not None:
        await queue.put(initial_message)

    async def receive_loop():
        try:
            while True:
                message = await websocket.receive()
                if ctx.state == AgentState.PROCESSING:
                    if "bytes" in message or message.get("text") == "__END__":
                        continue
                await queue.put(message)
        except WebSocketDisconnect:
            await queue.put({"_internal_type": "disconnect"})
        except Exception as e:
            # Desconexión del cliente: no loguear como ERROR (es normal que receive falle tras cerrar)
            if "disconnect" in str(e).lower() or "receive" in str(e).lower():
                log.debug("[WS %s] receive_loop ended: %s", session_id, e)
            else:
                log.error("[WS %s] Error in receive_loop: %s", session_id, e)
            await queue.put({"_internal_type": "disconnect"})

    receive_task = asyncio.create_task(receive_loop())

    try:
        while True:
            if connection_mode == "wake_word" and ctx.check_timeout():
                await websocket.send_json({"event": "status_change", "status": "waiting_wakeword"})

            try:
                msg = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if msg.get("_internal_type") == "disconnect":
                raise WebSocketDisconnect()

            segment = None
            from_end_signal = False
            if "bytes" in msg:
                segment = vad_manager.process_chunk(msg["bytes"])
            elif msg.get("text") == "__END__":
                log.debug("[WS %s] __END__ signal.", session_id)
                from_end_signal = True
                segment = vad_manager.force_flush()

            if segment is not None:
                if connection_mode == "direct":
                    log.info("[WS %s] Direct mode: processing segment as command.", session_id)
                    ctx.transition_to(AgentState.PROCESSING)
                    result = await pipeline.run_command(segment, ctx, websocket)
                    ctx.transition_to(AgentState.WAITING_WAKEWORD)
                    if result == "ignored_invalid_transcript":
                        # Transcripción inválida: misma lógica híbrida que el descarte VAD.
                        now = asyncio.get_event_loop().time()
                        no_voice_streak_count += 1
                        if no_voice_streak_start_ts is None:
                            no_voice_streak_start_ts = now
                        streak_elapsed_sec = now - no_voice_streak_start_ts
                        mode = config.DIRECT_NO_VOICE_MODE
                        should_send_spoken_no_voice = mode == "spoken"
                        if mode == "hybrid":
                            should_send_spoken_no_voice = (
                                no_voice_streak_count > config.DIRECT_IGNORED_NOISE_MAX_COUNT
                                or streak_elapsed_sec >= config.DIRECT_IGNORED_NOISE_MAX_WINDOW_SEC
                            )
                        if should_send_spoken_no_voice:
                            log.debug(
                                "[WS %s] No voice threshold reached (count=%d, elapsed=%.2fs). Sending spoken no_voice.",
                                session_id, no_voice_streak_count, streak_elapsed_sec,
                            )
                            await websocket.send_json({
                                "transcript": "",
                                "response": "No se detectó voz.",
                                "audio": None,
                                "data": {},
                                "meta": {"session_id": session_id},
                            })
                            no_voice_streak_count = 0
                            no_voice_streak_start_ts = None
                        else:
                            log.debug(
                                "[WS %s] Invalid transcript discarded silently (count=%d, elapsed=%.2fs).",
                                session_id, no_voice_streak_count, streak_elapsed_sec,
                            )
                            await websocket.send_json({
                                "event": "ignored_noise",
                                "message": "Audio descartado por VAD del servidor",
                            })
                        continue
                    else:
                        # Comando válido: resetear racha de ruido.
                        no_voice_streak_count = 0
                        no_voice_streak_start_ts = None
                    await websocket.send_json({"event": "status_change", "status": "ready"})

                elif ctx.state == AgentState.WAITING_WAKEWORD:
                    ctx.transition_to(AgentState.PROCESSING)
                    is_detected, remainder = await wakeword_detector.detect(segment, target_sr)

                    if is_detected:
                        log.info("[WS %s] Wake word detected! Remainder: '%s'", session_id, remainder)
                        if remainder:
                            log.info("[WS %s] Executing immediate command from wake phrase.", session_id)
                            await websocket.send_json({"event": "status_change", "status": "processing"})
                            await pipeline.run_command(segment, ctx, websocket, pre_transcribed_text=remainder)
                            ctx.transition_to(AgentState.WAITING_WAKEWORD)
                            await websocket.send_json({"event": "status_change", "status": "waiting_wakeword"})
                        else:
                            ctx.transition_to(AgentState.ACTIVE)
                            await websocket.send_json({"event": "status_change", "status": "active"})
                    else:
                        ctx.transition_to(AgentState.WAITING_WAKEWORD)

                elif ctx.state == AgentState.ACTIVE:
                    ctx.transition_to(AgentState.PROCESSING)
                    await pipeline.run_command(segment, ctx, websocket)
                    ctx.transition_to(AgentState.WAITING_WAKEWORD)
                    await websocket.send_json({"event": "status_change", "status": "waiting_wakeword"})

            elif from_end_signal and segment is None and connection_mode == "direct":
                now = asyncio.get_event_loop().time()
                no_voice_streak_count += 1
                if no_voice_streak_start_ts is None:
                    no_voice_streak_start_ts = now

                streak_elapsed_sec = now - no_voice_streak_start_ts
                mode = config.DIRECT_NO_VOICE_MODE
                should_send_spoken_no_voice = mode == "spoken"
                if mode == "hybrid":
                    should_send_spoken_no_voice = (
                        no_voice_streak_count > config.DIRECT_IGNORED_NOISE_MAX_COUNT
                        or streak_elapsed_sec >= config.DIRECT_IGNORED_NOISE_MAX_WINDOW_SEC
                    )

                if should_send_spoken_no_voice:
                    log.debug(
                        "[WS %s] No voice threshold reached (count=%d, elapsed=%.2fs). Sending spoken no_voice.",
                        session_id,
                        no_voice_streak_count,
                        streak_elapsed_sec,
                    )
                    await websocket.send_json({
                        "transcript": "",
                        "response": "No se detectó voz.",
                        "audio": None,
                        "data": {},
                        "meta": {"session_id": session_id},
                    })
                    # Tras avisar al usuario, reiniciamos la racha para volver a dar margen.
                    no_voice_streak_count = 0
                    no_voice_streak_start_ts = None
                else:
                    log.debug(
                        "[WS %s] Discarded noise silently (count=%d, elapsed=%.2fs).",
                        session_id,
                        no_voice_streak_count,
                        streak_elapsed_sec,
                    )
                    await websocket.send_json({
                        "event": "ignored_noise",
                        "message": "Audio descartado por VAD del servidor",
                    })
                await websocket.send_json({"event": "status_change", "status": "ready"})

    except WebSocketDisconnect:
        log.info("[WS %s] Client disconnected.", session_id)
    except Exception as e:
        log.error("[WS %s] Critical error: %s\n%s", session_id, e, traceback.format_exc())
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        receive_task.cancel()
        vad_manager.close()
        log.info("[WS %s] Session closed.", session_id)


# =========================
# WebSocket endpoint
# =========================
@app.websocket("/ws/audio")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = str(uuid.uuid4())[:8]
    service_headers = _modelador_service_headers(websocket)
    if service_headers:
        log.info(
            "[WS %s] Modelador auth context received: tenant=%s kong=%s auth=%s",
            session_id,
            service_headers.get("NGSILD-Tenant") or service_headers.get("X-Modelador-Tenant") or "",
            service_headers.get("X-Modelador-Kong-Url") or "",
            "yes" if service_headers.get("Authorization") else "no",
        )
    else:
        log.info("[WS %s] Connected without Modelador auth context headers.", session_id)

    # Primer mensaje opcional: {"mode": "wake_word" | "direct"} (p. ej. gafas / web sin palabra de activación).
    # Si el cliente envía audio primero o no envía nada en 2s, se asume wake_word.
    connection_mode: Literal["wake_word", "direct"] = "wake_word"
    initial_message: dict | None = None
    try:
        first = await asyncio.wait_for(websocket.receive(), timeout=2.0)
        if "text" in first:
            try:
                data = json.loads(first["text"])
                if isinstance(data, dict) and data.get("mode") in ("direct", "wake_word"):
                    connection_mode = data["mode"]
                    log.info("[WS %s] Connected. Mode: %s (from client).", session_id, connection_mode)
                else:
                    log.info("[WS %s] Connected. Mode: wake_word (default).", session_id)
            except (json.JSONDecodeError, TypeError):
                log.info("[WS %s] Connected. Mode: wake_word (default).", session_id)
        elif "bytes" in first:
            connection_mode = "wake_word"
            initial_message = first
            log.info("[WS %s] Connected. Mode: wake_word (first message was audio).", session_id)
        else:
            log.info("[WS %s] Connected. Mode: wake_word (default).", session_id)
    except asyncio.TimeoutError:
        log.info("[WS %s] Connected. Mode: wake_word (no initial message).", session_id)

    ctx = SessionContext(session_id, config.ACTIVE_TIMEOUT_SEC, log, service_headers=service_headers)
    vad_manager = VADManager(
        session_id,
        vad,
        target_sr=config.TARGET_SR,
        silence_wait_ms=config.SILENCE_WAIT_MS,
        min_voice_sec=config.MIN_VOICE_SEC,
        min_rms=config.MIN_RMS,
        debug_audio_dir=config.DEBUG_AUDIO_DIR if (config.DEBUG_AUDIO_SAVE and config.DEBUG_SAVE_CONTINUOUS) else None,
        debug_save_continuous=config.DEBUG_SAVE_CONTINUOUS,
    )

    await run_voice_session_loop(
        websocket,
        session_id,
        ctx,
        vad_manager,
        wakeword_detector=wakeword_detector,
        pipeline=pipeline,
        target_sr=config.TARGET_SR,
        log=log,
        connection_mode=connection_mode,
        initial_message=initial_message,
    )
