# Scripts de Testing y Utilidad

## download_tts_model.py

Descarga el modelo TTS (Piper, español) usado por el backend. Se ejecuta automáticamente durante el build del Docker del backend. Para ejecutarlo a mano (por ejemplo dentro del contenedor):

```bash
python scripts/download_tts_model.py
```

## mock_agent.py

Servidor mock del agente externo para pruebas locales. Responde en el puerto 8081 con el contrato esperado por el backend (request con `input_text`, response con `speech`/`text`).

**Uso:**
```bash
python scripts/mock_agent.py
```

Luego en `config.env`: `AGENT_API_URL=http://localhost:8081/api/chat` (o `http://host.docker.internal:8081/api/chat` si el backend corre en Docker).

## test_audio_segments.py

Prueba el backend enviando múltiples segmentos de audio sintéticos.

**Uso:**
```bash
python scripts/test_audio_segments.py
```

Configuración: edita `MAX_SAMPLES` para limitar muestras; los resultados se guardan en `output/test_results/`.

## test_transcription_accuracy.py

Evaluación de precisión de transcripción con Whisper (dataset Common Voice, WER/CER). Ejecutar desde la raíz del proyecto.