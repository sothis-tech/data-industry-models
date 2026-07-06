import os
import requests
import logging

def download_model():
    """Descarga el modelo de voz es_ES-sharvard-medium.onnx y su config json si no existen."""
    # Rutas: script en scripts/ (o /app/scripts en Docker) → modelos en tts_models/ a nivel proyecto.
    # Así en Docker es /app/tts_models y no queda oculto por el volumen ./backend:/app/backend.
    current_dir = os.path.dirname(os.path.abspath(__file__))
    model_dir = os.path.join(current_dir, "..", "tts_models")
    model_dir = os.path.abspath(model_dir)
    
    os.makedirs(model_dir, exist_ok=True)
    
    files = {
        "es_ES-sharvard-medium.onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/sharvard/medium/es_ES-sharvard-medium.onnx?download=true",
        "es_ES-sharvard-medium.onnx.json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/sharvard/medium/es_ES-sharvard-medium.onnx.json?download=true"
    }

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("TTS-Downloader")
    logger.info(f"Directorio de modelos: {model_dir}")

    for filename, url in files.items():
        filepath = os.path.join(model_dir, filename)
        if not os.path.exists(filepath):
            logger.info(f"Descargando {filename}...")
            try:
                response = requests.get(url, stream=True)
                response.raise_for_status()
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                logger.info(f"{filename} descargado correctamente.")
            except Exception as e:
                logger.error(f"Error descargando {filename}: {e}")
                # Eliminar archivo corrupto/parcial si existe
                if os.path.exists(filepath):
                    os.remove(filepath)
                raise e
        else:
            logger.info(f"{filename} ya existe. Omitiendo descarga.")

if __name__ == "__main__":
    download_model()

