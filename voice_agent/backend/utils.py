"""Utilidades genéricas del backend."""
import io
import time
import logging
from contextlib import contextmanager
from typing import Optional

import numpy as np
import soundfile as sf

from backend.config import config


@contextmanager
def timed(section: str, extra: Optional[dict] = None, log: Optional[logging.Logger] = None):
    """Context manager que mide tiempo y lo registra en log."""
    logger = log or logging.getLogger("realtime-backend")
    t0 = time.perf_counter()
    try:
        yield
    finally:
        dt = (time.perf_counter() - t0) * 1000
        if extra:
            logger.info("[TIMER] %s: %.1f ms | %s", section, dt, extra)
        else:
            logger.info("[TIMER] %s: %.1f ms", section, dt)


def float_to_wav_bytes(arr: np.ndarray, sr: int = config.TARGET_SR) -> bytes:
    """Convierte un array float32 de audio en bytes WAV (16-bit PCM)."""
    buf = io.BytesIO()
    sf.write(buf, arr, sr, subtype="PCM_16", format="WAV")
    return buf.getvalue()
