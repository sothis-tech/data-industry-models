"""
Prueba de WebSocket en modo direct (gafas AR).

Qué hace:
- Conecta a ws://localhost:8000/ws/audio
- Envía primero (texto) {"mode":"direct"}
- Envía audio sintético (tono) en chunks de 20ms (PCM int16 little-endian)
- Envía "__END__" como texto plano para forzar flush del VAD
- Imprime los mensajes JSON que devuelve el backend

Uso (dentro del contenedor backend):
  docker compose exec backend python /app/scripts/test_direct_mode_ws.py
"""

import asyncio
import json
import time

import numpy as np
import websockets


# Puede sobreescribirse con el primer argumento de línea de comandos:
#   python test_direct_mode_ws.py ws://voice-agent-backend:8000/ws/audio
import sys as _sys
WS_URL = _sys.argv[1] if len(_sys.argv) > 1 else "ws://localhost:8000/ws/audio"
TARGET_SR = 16000
FRAME_SIZE = 320  # 20ms @ 16kHz = 320 muestras (int16) -> 640 bytes por frame
LLM_TIMEOUT = 120.0


def generate_tone(frequency=440.0, duration=1.5, sample_rate=16000, amplitude=0.4):
    """Genera un tono sinusoidal (simula voz con energía suficiente para el VAD)."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    signal = amplitude * np.sin(2 * np.pi * frequency * t)
    return signal.astype(np.float32)


def float_to_int16(audio_float: np.ndarray) -> np.ndarray:
    return (np.clip(audio_float, -1.0, 1.0) * 32767.0).astype(np.int16)


def int16_to_bytes(audio_int16: np.ndarray) -> bytes:
    return audio_int16.tobytes(order="C")


async def send_audio(ws, audio_float: np.ndarray, segment_name: str):
    audio_int16 = float_to_int16(audio_float)
    audio_bytes = int16_to_bytes(audio_int16)

    print(f"\n📤 Enviando audio '{segment_name}': {len(audio_bytes)} bytes", flush=True)

    # Enviar en chunks de 20ms para simular streaming real
    for i in range(0, len(audio_bytes), FRAME_SIZE * 2):
        chunk = audio_bytes[i : i + FRAME_SIZE * 2]
        await ws.send(chunk)
        await asyncio.sleep(0.02)


async def main():
    print("=" * 60, flush=True)
    print("🧪 TEST: WebSocket modo direct", flush=True)
    print(f"📡 Conectando a {WS_URL}", flush=True)
    print("=" * 60, flush=True)

    start_time = time.time()
    ws = None
    try:
        ws = await websockets.connect(WS_URL, ping_interval=None, ping_timeout=None, close_timeout=10)
        print("✅ Conectado", flush=True)

        # 1) Primer mensaje: modo direct (texto JSON)
        await ws.send(json.dumps({"mode": "direct"}))
        print("➡️ Enviado: {\"mode\":\"direct\"}", flush=True)

        # 2) Audio: tono (para que el VAD genere segmento)
        tone = generate_tone(440.0, duration=1.6, sample_rate=TARGET_SR, amplitude=0.4)
        await send_audio(ws, tone, "Tono 440Hz (simulado voz)")

        # 3) Fin de frase: texto plano __END__
        print("\n📨 Enviando fin de frase: __END__", flush=True)
        await ws.send("__END__")

        # 4) Recibir mensajes: puede llegar status_change, transcript, response, etc.
        # Vamos a leer hasta tener transcript con response o un timeout.
        seen_final_response = False
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=LLM_TIMEOUT)
            try:
                data = json.loads(msg)
            except Exception:
                print("⚠️ Mensaje no-JSON:", msg, flush=True)
                continue

            print("⬅️ Mensaje:", data, flush=True)

            # Criterio: respuesta completa tiene audio y response string (aunque audio pueda ser null)
            if isinstance(data, dict) and "transcript" in data and "response" in data:
                # Puede haber dos: una con response=null y otra final. La final tendrá response string.
                if data.get("response") is not None:
                    seen_final_response = True

            if seen_final_response:
                break

    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}", flush=True)
        raise
    finally:
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

        print(f"\n⏱️ Duración total: {time.time() - start_time:.2f}s", flush=True)


if __name__ == "__main__":
    asyncio.run(main())

