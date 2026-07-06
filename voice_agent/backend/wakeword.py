import abc
import logging
import numpy as np
import os
import tempfile
import soundfile as sf
import asyncio
from typing import Optional

# Configuración de logging para este módulo
log = logging.getLogger("wakeword")

class WakeWordDetector(abc.ABC):
    """
    Clase base abstracta para detectores de palabra de activación.
    Permite intercambiar implementaciones (Whisper, OpenWakeWord, Porcupine)
    sin afectar la lógica principal del servidor.
    """
    
    @abc.abstractmethod
    async def detect(self, audio_data: np.ndarray, sample_rate: int) -> tuple[bool, str]:
        """
        Procesa el audio y determina si la palabra de activación está presente.
        
        Args:
            audio_data: Array de numpy con el audio (float32).
            sample_rate: Tasa de muestreo del audio.
            
        Returns:
            Tuple (detectado, resto_del_texto):
            - detectado: True si se detectó la palabra.
            - resto_del_texto: El texto que sigue a la palabra clave (si lo hay), limpio.
        """
        pass

class WhisperWakeWordDetector(WakeWordDetector):
    """
    Implementación de detección usando el modelo Whisper ya cargado.
    Transcribe el audio y busca la palabra clave en el texto resultante.
    """
    
    def __init__(self, model, keyword: str, language: str = "es", aliases: Optional[list[str]] = None):
        """
        Args:
            model: Instancia del modelo Whisper ya cargado (para reusar recursos).
            keyword: Palabra o frase de activación a detectar.
            language: Idioma para la transcripción (optimiza la detección).
            aliases: Lista de variantes fonéticas aceptadas (ej: ['marby', 'martin']).
        """
        self.model = model
        self.keyword = keyword.lower().strip()
        self.language = language
        
        # Construir lista de términos aceptados (keyword + alias)
        self.accepted_terms = [self.keyword]
        if aliases:
            self.accepted_terms.extend([a.lower().strip() for a in aliases])
            
        log.info(f"WhisperWakeWordDetector inicializado. Terms={self.accepted_terms}, Lang='{self.language}'")

    async def detect(self, audio_data: np.ndarray, sample_rate: int) -> tuple[bool, str]:
        if len(audio_data) == 0:
            return False, ""

        # Guardar audio a archivo temporal para Whisper (requiere path)
        # Nota: En implementaciones futuras con Whisper streaming real, esto podría evitarse.
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                sf.write(tmp.name, audio_data, sample_rate, subtype='PCM_16')
                tmp_path = tmp.name

            # Ejecutar transcripción en thread pool para no bloquear el event loop
            # Usamos parámetros optimizados para velocidad (beam_size=1, etc.)
            result = await asyncio.to_thread(
                self.model.transcribe,
                tmp_path,
                language=self.language,
                beam_size=1,      # Más rápido, menos preciso (suficiente para wake word)
                best_of=1,
                fp16=True
            )
            
            # Limpieza
            try:
                os.remove(tmp_path)
            except OSError:
                pass

            text = (result.get("text") or "").lower().strip()
            
            # Normalización básica para comparación
            text_clean = text.replace('.', '').replace(',', '').replace('!', '').replace('?', '')
            
            if not text_clean:
                return False, ""

            log.debug(f"WakeWord check: escuchado='{text_clean}' vs targets={self.accepted_terms}")
            
            # Verificación: ¿Alguna de las keywords está contenida en lo transcrito?
            for term in self.accepted_terms:
                if term in text_clean:
                    log.info(f"¡Wake Word detectada!: '{term}' en '{text}'")
                    
                    # Extraer el comando posterior usando el término específico encontrado
                    parts = text_clean.split(term, 1)
                    remainder = parts[1].strip() if len(parts) > 1 else ""
                    
                    return True, remainder
                
            return False, ""

        except Exception as e:
            log.error(f"Error en detección de Wake Word: {e}")
            return False, ""

