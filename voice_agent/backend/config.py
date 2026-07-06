"""
Configuración centralizada del backend: variables de entorno y constantes.
Carga config.env al importar.
"""
import os

from dotenv import load_dotenv

load_dotenv("config.env")


class Config:
    """Valores de configuración leídos de entorno (y constantes fijas)."""

    # --- Logging ---
    LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()

    # --- Debug audio ---
    DEBUG_AUDIO_SAVE = os.getenv("DEBUG_AUDIO_SAVE", "false").lower() == "true"
    DEBUG_AUDIO_SEND_BACK = os.getenv("DEBUG_AUDIO_SEND_BACK", "false").lower() == "true"
    DEBUG_SAVE_CONTINUOUS = os.getenv("DEBUG_SAVE_CONTINUOUS", "false").lower() == "true"
    DEBUG_AUDIO_DIR = os.getenv("DEBUG_AUDIO_DIR", "/tmp/audio_debug")

    # --- Audio / VAD ---
    TARGET_SR = 16000
    FRAME_MS = 20  # 20 ms frames -> 320 bytes @ 16 kHz mono int16
    SILENCE_FRAMES = 8  # reservado para compatibilidad

    MIN_RMS = float(os.getenv("MIN_RMS", "0.01"))
    MIN_VOICE_SEC = float(os.getenv("MIN_VOICE_SEC", "0.5"))
    WHISPER_LANG = os.getenv("WHISPER_LANG", "es")
    SILENCE_WAIT_MS = int(os.getenv("SILENCE_WAIT_MS", "2000"))
    VAD_MODE = int(os.getenv("VAD_MODE", "3"))

    # --- Wake word ---
    WAKE_WORD = os.getenv("WAKE_WORD", "marvin")
    _ALIASES_RAW = os.getenv("WAKE_WORD_ALIASES")  # None si no está definida
    _ALIASES_DEFAULT = "marby,martin,marlin,mar vi,marvín,marwin"
    ALIASES_FROM_ENV = _ALIASES_RAW is not None and _ALIASES_RAW.strip() != ""
    _ALIASES_STR = (_ALIASES_RAW or _ALIASES_DEFAULT).strip()
    WAKE_WORD_ALIASES = [a.strip() for a in _ALIASES_STR.split(",")] if _ALIASES_STR else []

    ACTIVE_TIMEOUT_SEC = float(os.getenv("ACTIVE_TIMEOUT_SEC", "8.0"))

    # --- Agente remoto ---
    AGENT_API_URL = os.getenv(
        "AGENT_API_URL", "http://localhost:8081/api/chat"
    )
    AGENT_TIMEOUT_TOTAL_SEC = float(os.getenv("AGENT_TIMEOUT_TOTAL_SEC", "30"))
    AGENT_TIMEOUT_CONNECT_SEC = float(os.getenv("AGENT_TIMEOUT_CONNECT_SEC", "10"))

    # --- Direct mode (gafas): estrategia cuando no hay voz valida ---
    # spoken: siempre "No se detecto voz."
    # silent: siempre ignored_noise
    # hybrid: ignored_noise al principio, y habla tras umbral de ruido/tiempo
    DIRECT_NO_VOICE_MODE = os.getenv("DIRECT_NO_VOICE_MODE", "hybrid").lower()
    DIRECT_IGNORED_NOISE_MAX_COUNT = int(os.getenv("DIRECT_IGNORED_NOISE_MAX_COUNT", "4"))
    DIRECT_IGNORED_NOISE_MAX_WINDOW_SEC = float(
        os.getenv("DIRECT_IGNORED_NOISE_MAX_WINDOW_SEC", "10.0")
    )

    # --- Rutas TTS (relativas al backend) ---
    @staticmethod
    def get_tts_models_dir() -> str:
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.abspath(os.path.join(backend_dir, "..", "tts_models"))


# Instancia única para importar: from backend.config import config
config = Config()
