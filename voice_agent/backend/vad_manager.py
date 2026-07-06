"""VAD (Voice Activity Detection), buffering y resampling de audio por sesión."""
import os
import time
import logging
from typing import Optional

import numpy as np
import soundfile as sf
import scipy.signal


class VADManager:
    """
    Gestiona la detección de voz/silencio, el buffer de audio y el resampling.
    Devuelve un segmento de audio completo cuando se detecta fin de frase (silencio prolongado).
    """

    def __init__(
        self,
        session_id: str,
        vad,
        *,
        target_sr: int = 16000,
        silence_wait_ms: int = 2000,
        min_voice_sec: float = 1.0,
        min_rms: float = 0.01,
        debug_audio_dir: Optional[str] = None,
        debug_save_continuous: bool = False,
    ):
        self.session_id = session_id
        self._vad = vad
        self._target_sr = target_sr
        self._silence_wait_sec = silence_wait_ms / 1000.0
        self._min_voice_sec = min_voice_sec
        self._min_rms = min_rms

        self.arr_buffer: list[np.ndarray] = []
        self.source_sample_rate: Optional[int] = None
        self.last_speech_time: Optional[float] = None
        self.continuous_sink = None

        log = logging.getLogger("realtime-backend")
        if debug_audio_dir and debug_save_continuous:
            path = os.path.join(debug_audio_dir, f"{session_id}_continuous.wav")
            try:
                self.continuous_sink = sf.SoundFile(
                    path, mode="w", samplerate=target_sr, channels=1, subtype="PCM_16"
                )
                log.info("[WS %s] Debug continuo: %s", session_id, path)
            except Exception as e:
                log.warning("Error creating continuous sink: %s", e)

    def process_chunk(self, data: bytes) -> Optional[np.ndarray]:
        """
        Procesa un chunk de audio: decodifica, resamplea si hace falta, aplica VAD y buffer.
        Devuelve un segmento completo (np.ndarray float32) cuando termina una frase, o None.
        """
        arr = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

        if self.source_sample_rate is None:
            samples_per_frame = len(arr)
            self.source_sample_rate = int(samples_per_frame / 0.02)
            log = logging.getLogger("realtime-backend")
            log.info("[WS %s] Sample rate detectado: %d Hz", self.session_id, self.source_sample_rate)

        if self.source_sample_rate != self._target_sr:
            num_samples = int(len(arr) * self._target_sr / self.source_sample_rate)
            arr = scipy.signal.resample(arr, num_samples)

        self.arr_buffer.append(arr)
        if self.continuous_sink:
            self.continuous_sink.write(arr)

        return self._check_vad()

    def _check_vad(self) -> Optional[np.ndarray]:
        if not self.arr_buffer:
            return None

        accumulated_audio = np.concatenate(self.arr_buffer)
        accumulated_int16 = (accumulated_audio * 32768.0).astype(np.int16)
        accumulated_bytes = accumulated_int16.tobytes()

        vad_frame_size = int(self._target_sr * 0.02 * 2)
        if len(accumulated_bytes) < vad_frame_size:
            return None

        vad_frame = accumulated_bytes[-vad_frame_size:]
        try:
            is_speech = self._vad.is_speech(vad_frame, self._target_sr)
        except Exception:
            is_speech = True

        if is_speech:
            if self.last_speech_time is not None:
                self.last_speech_time = None
            return None

        if self.last_speech_time is None:
            if len(accumulated_audio) >= self._target_sr * 0.5:
                self.last_speech_time = time.time()
            return None

        silence_duration = time.time() - self.last_speech_time
        if silence_duration >= self._silence_wait_sec:
            seg_audio = accumulated_audio.copy()
            self.arr_buffer = []
            self.last_speech_time = None

            seg_dur = len(seg_audio) / self._target_sr
            seg_rms = float(np.sqrt((seg_audio ** 2).mean()))
            log = logging.getLogger("realtime-backend")

            if seg_dur > self._min_voice_sec and seg_rms > self._min_rms:
                log.debug(
                    "[WS %s] Voice detected: dur=%.2fs (min %.2fs), rms=%.3f (min %.3f)",
                    self.session_id,
                    seg_dur,
                    self._min_voice_sec,
                    seg_rms,
                    self._min_rms,
                )
                return seg_audio
            log.debug(
                "[WS %s] Discarded noise: dur=%.2fs (min %.2fs), rms=%.3f (min %.3f)",
                self.session_id,
                seg_dur,
                self._min_voice_sec,
                seg_rms,
                self._min_rms,
            )
            return None

        return None

    def force_flush(self) -> Optional[np.ndarray]:
        """Fuerza la devolución del buffer actual (p. ej. al recibir __END__)."""
        if not self.arr_buffer:
            return None

        accumulated_audio = np.concatenate(self.arr_buffer)
        seg_audio = accumulated_audio.copy()
        self.arr_buffer = []
        self.last_speech_time = None

        seg_dur = len(seg_audio) / self._target_sr
        seg_rms = float(np.sqrt((seg_audio ** 2).mean()))
        if seg_dur > self._min_voice_sec and seg_rms > self._min_rms:
            return seg_audio
        return None

    def close(self) -> None:
        if self.continuous_sink:
            self.continuous_sink.close()
