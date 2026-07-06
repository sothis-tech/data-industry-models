import os
import io
import wave
import logging

try:
    from piper import PiperVoice
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False
    PiperVoice = None

log = logging.getLogger("tts-service")


class TTSService:
    def __init__(self, model_path: str):
        self.model_path = os.path.abspath(model_path)
        self.config_path = f"{self.model_path}.json"
        self.voice = None

        if not PIPER_AVAILABLE:
            log.error("piper-tts no está instalado. Instala con: pip install piper-tts")
            return

        if not os.path.exists(self.model_path):
            log.error(f"Modelo TTS no encontrado: {self.model_path}")
            return

        try:
            log.info(f"Cargando modelo TTS desde: {self.model_path}")
            self.voice = PiperVoice.load(self.model_path, use_cuda=True)
            log.info("Servicio TTS inicializado correctamente.")
        except Exception as e:
            log.error(f"Error cargando modelo TTS: {e}")
            try:
                log.info("Reintentando carga sin CUDA...")
                self.voice = PiperVoice.load(self.model_path, use_cuda=False)
                log.info("Modelo TTS cargado (CPU Mode).")
            except Exception as e2:
                log.error(f"Error fatal cargando TTS: {e2}")
                self.voice = None

    def generate_audio(self, text: str) -> bytes:
        """
        Genera audio WAV a partir de texto usando la API oficial de Piper.
        Doc: https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md
        """
        if not text:
            log.warning("TTS solicitado con texto vacío")
            return b""

        if not self.voice:
            log.error("TTS solicitado pero el modelo no está cargado")
            return b""

        try:
            log.info(f"Sintetizando audio para: '{text[:20]}...'")
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                self.voice.synthesize_wav(text, wav_file)

            wav_buffer.seek(0)
            audio_bytes = wav_buffer.read()
            log.info(f"Audio generado exitosamente: {len(audio_bytes)} bytes")
            return audio_bytes

        except Exception as e:
            log.error(f"Excepción crítica generando audio TTS: {e}", exc_info=True)
            return b""
