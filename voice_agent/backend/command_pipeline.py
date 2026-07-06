"""
Pipeline de comando: transcribir (Whisper) → agente remoto → TTS → enviar respuesta por WebSocket.
"""
import os
import time
import asyncio
import base64
import logging
import tempfile
from contextlib import contextmanager
from typing import Literal, Optional

import numpy as np
import soundfile as sf

from fastapi import WebSocket

from backend.session import SessionContext


@contextmanager
def _timed(section: str, log: logging.Logger, extra: dict | None = None):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        dt = (time.perf_counter() - t0) * 1000
        if extra:
            log.info("[TIMER] %s: %.1f ms | %s", section, dt, extra)
        else:
            log.info("[TIMER] %s: %.1f ms", section, dt)


class CommandPipeline:
    """
    Encapsula el flujo: audio → transcripción (opcional) → agente → TTS → envío por WebSocket.
    Recibe en el constructor los servicios (Whisper model, agent, TTS) y la config necesaria.
    """

    def __init__(
        self,
        whisper_model,
        agent_service,
        tts_service,
        *,
        target_sr: int,
        whisper_lang: str,
        log: Optional[logging.Logger] = None,
    ):
        self._model = whisper_model
        self._agent_service = agent_service
        self._tts_service = tts_service
        self._target_sr = target_sr
        self._whisper_lang = whisper_lang
        self._log = log or logging.getLogger("command-pipeline")
        self._invalid_transcriptions = {"", "(vacío)", "(error de transcripción)"}

    async def transcribe(self, audio: np.ndarray, session_id: str) -> str:
        """Transcribe audio a texto con Whisper."""
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                sf.write(tmp.name, audio, self._target_sr, subtype="PCM_16")
                tmp_path = tmp.name

            self._log.info("[WS %s] Transcribing...", session_id)

            # --- NUEVO: Definimos el contexto predictivo para Whisper ---
            contexto_industrial = (
                "Comando directo de operario industrial. "
                "Ignorar conversaciones cruzadas o ruido de fondo. "
                "Ejemplos: Hola Marvin, dime la presión. Marvin, finaliza la tarea. ¿Cuál es el estado de la máquina?"
            )

            with _timed("Whisper.transcribe", self._log, {"session": session_id}):
                res = await asyncio.to_thread(
                    self._model.transcribe,
                    tmp_path,
                    language=self._whisper_lang,
                    task="transcribe",
                    fp16=True,
                    initial_prompt=contexto_industrial, # <-- INYECCIÓN DEL PROMPT AQUÍ
                )

            try:
                os.remove(tmp_path)
            except OSError:
                pass

            text = (res.get("text") or "").strip() or "(vacío)"
            self._log.info("[WS %s] Transcript: %s", session_id, text)
            return text
        except Exception as e:
            self._log.error("[WS %s] Transcription error: %s", session_id, e)
            return "(error de transcripción)"

    async def run_command(
        self,
        audio: np.ndarray,
        ctx: SessionContext,
        websocket: WebSocket,
        *,
        pre_transcribed_text: Optional[str] = None,
    ) -> Literal["ok", "ignored_invalid_transcript"]:
        """
        Ejecuta el pipeline completo: transcribir (si hace falta) → enviar transcript →
        consultar agente → TTS → enviar respuesta.
        Envío de respuesta: `text` (chat enriquecido), `speech` (guion TTS) y `response`
        (= `speech`, alias para clientes gafas que solo leen `response`).
        """
        session_id = ctx.session_id

        if pre_transcribed_text:
            user_text = pre_transcribed_text
            self._log.info("[WS %s] Using pre-transcribed text: %s", session_id, user_text)
        else:
            user_text = await self.transcribe(audio, session_id)

        # Filtro temprano: si la transcripción es inválida/vacía, no enviamos nada
        # y dejamos que server.py gestione el feedback (streak híbrido).
        normalized_user_text = (user_text or "").strip().lower()
        if normalized_user_text in self._invalid_transcriptions:
            self._log.info("[WS %s] Invalid/empty transcript. Skipping pipeline.", session_id)
            return "ignored_invalid_transcript"

        try:
            await websocket.send_json({
                "transcript": user_text,
                "response": None,
                "meta": {"session_id": session_id},
            })
        except Exception as e:
            self._log.warning("[WS %s] Failed to send transcript: %s", session_id, e)

        reply_speech = ""
        reply_text = ""
        reply_data = {}
        try:
            self._log.info("[WS %s] Querying Remote Agent...", session_id)
            agent_response = await self._agent_service.process_request(
                user_text,
                session_id,
                extra_headers=ctx.service_headers,
            )
            reply_speech = agent_response.get("speech", "")
            reply_text = agent_response.get("text", reply_speech)
            reply_data = agent_response.get("data") or {}
            self._log.info("[WS %s] Agent Reply Speech: %d chars", session_id, len(reply_speech))
        except Exception as e:
            self._log.error("[WS %s] Agent error: %s", session_id, e)
            reply_speech = "Lo siento, hubo un error conectando con el agente."
            reply_text = reply_speech
            reply_data = {}

        audio_b64 = None
        try:
            if reply_speech and self._tts_service:
                self._log.info("[WS %s] Generating TTS...", session_id)
                audio_bytes = await asyncio.to_thread(
                    self._tts_service.generate_audio, reply_speech
                )
                if audio_bytes:
                    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                    self._log.info("[WS %s] TTS generated: %d bytes", session_id, len(audio_bytes))
        except Exception as e:
            self._log.error("[WS %s] TTS error: %s", session_id, e)

        reply_text = (reply_text or "").strip() or (reply_speech or "").strip()
        reply_speech = (reply_speech or "").strip() or reply_text
        try:
            await websocket.send_json({
                "transcript": user_text,
                "text": reply_text,
                "speech": reply_speech,
                "response": reply_speech,
                "audio": audio_b64,
                "data": reply_data,
                "meta": {"session_id": session_id},
            })
        except Exception as e:
            self._log.warning("[WS %s] Failed to send response: %s", session_id, e)

        return "ok"
