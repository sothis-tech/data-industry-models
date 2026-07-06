"""
Script de prueba para validar la detección de múltiples segmentos de audio.
Simula el envío de varios bloques de audio separados por silencios.
"""
import asyncio
import websockets
import json
import numpy as np
import struct
import time
import sys

# Configuración (debe coincidir con backend/server.py)
WS_URL = "ws://localhost:8000/ws/audio"
TARGET_SR = 16000
FRAME_SIZE = 320  # 20ms @ 16kHz = 320 bytes (int16)
LLM_TIMEOUT = 60.0  # Aumentar timeout para LLM (60 segundos)

def generate_tone(frequency=440, duration=1.0, sample_rate=16000, amplitude=0.3):
    """Genera un tono sinusoidal (simula voz)"""
    t = np.linspace(0, duration, int(sample_rate * duration))
    signal = amplitude * np.sin(2 * np.pi * frequency * t)
    return signal

def generate_silence(duration=1.0, sample_rate=16000):
    """Genera silencio"""
    return np.zeros(int(sample_rate * duration))

def float_to_int16(audio_float):
    """Convierte audio float32 a int16"""
    return (audio_float * 32768.0).astype(np.int16)

def int16_to_bytes(audio_int16):
    """Convierte int16 array a bytes"""
    return audio_int16.tobytes()

async def send_audio_segment(ws, audio_float, segment_name):
    """Envía un segmento de audio"""
    audio_int16 = float_to_int16(audio_float)
    audio_bytes = int16_to_bytes(audio_int16)
    
    print(f"📤 Enviando segmento '{segment_name}': {len(audio_bytes)} bytes ({len(audio_float)/TARGET_SR:.2f}s)", flush=True)
    
    # Enviar en chunks de FRAME_SIZE
    for i in range(0, len(audio_bytes), FRAME_SIZE):
        chunk = audio_bytes[i:i+FRAME_SIZE]
        await ws.send(chunk)
        await asyncio.sleep(0.02)  # Simular tiempo real (20ms por frame)

# Modificar la función test_multiple_segments para reconectar si se cierra la conexión
async def test_multiple_segments():
    """Prueba el procesamiento de múltiples segmentos de audio"""
    print("=" * 60, flush=True)
    print("🧪 PRUEBA: Múltiples segmentos de audio", flush=True)
    print("=" * 60, flush=True)
    print("⚠️  NOTA: Este script envía tonos sinusoidales (no voz real)", flush=True)
    print("   Whisper puede no transcribirlos correctamente.", flush=True)
    print("   Los tonos son: 440Hz, 550Hz, 660Hz (2s, 1.5s, 2.5s respectivamente)\n", flush=True)
    
    results = []
    
    # Generar segmentos de prueba
    segments = [
        ("Segmento 1 (440Hz)", generate_tone(440, 2.0), 1.0),
        ("Segmento 2 (550Hz)", generate_tone(550, 1.5), 1.0),
        ("Segmento 3 (660Hz)", generate_tone(660, 2.5), 0.5),
    ]
    
    ws = None
    segment_index = 0
    
    while segment_index < len(segments):
        try:
            # Conectar o reconectar
            if ws is None:
                print(f"🔌 Conectando a {WS_URL}...", flush=True)
            else:
                print(f"🔌 Reconectando a {WS_URL}...", flush=True)
            
            try:
                ws = await websockets.connect(
                    WS_URL,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=10
                )
                print("✅ Conectado al servidor WebSocket", flush=True)
            except Exception as e:
                print(f"❌ Error al conectar: {e}", flush=True)
                await asyncio.sleep(1)
                continue
            
            name, audio, silence_duration = segments[segment_index]
            print(f"\n--- {name} ---", flush=True)
            
            # Enviar audio
            start_time = time.time()
            await send_audio_segment(ws, audio, name)
            
            # Enviar silencio para activar el endpointing
            silence = generate_silence(silence_duration)
            await send_audio_segment(ws, silence, f"Silencio {segment_index + 1}")
            
            # Esperar respuesta
            transcript_received = False
            try:
                print(f"⏳ Esperando respuesta para {name}... (timeout: {LLM_TIMEOUT}s)", flush=True)
                response = await asyncio.wait_for(ws.recv(), timeout=LLM_TIMEOUT)
                elapsed = time.time() - start_time
                
                data = json.loads(response)
                transcript = data.get("transcript", "(vacío)")
                response_text = data.get("response", "")
                meta = data.get("meta", {})
                
                print(f"✅ Respuesta recibida en {elapsed:.2f}s", flush=True)
                print(f"   📝 Transcripción: {transcript}", flush=True)
                print(f"   ⏱️  Duración segmento: {meta.get('segment_duration_sec', 'N/A')}s", flush=True)
                print(f"   📊 RMS: {meta.get('segment_rms', 'N/A')}", flush=True)
                if len(response_text) > 100:
                    print(f"   🤖 Respuesta LLM: {response_text[:100]}...", flush=True)
                else:
                    print(f"   🤖 Respuesta LLM: {response_text}", flush=True)
                
                transcript_received = True
                results.append({
                    "segment": name,
                    "success": True,
                    "elapsed": elapsed,
                    "transcript": transcript,
                    "duration": meta.get("segment_duration_sec"),
                    "rms": meta.get("segment_rms")
                })
                segment_index += 1
                
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                print(f"⏰ TIMEOUT después de {elapsed:.2f}s", flush=True)
                # Intentar recibir respuesta aunque haya timeout
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(response)
                    transcript = data.get("transcript", "(vacío)")
                    print(f"   📝 Transcripción recibida después del timeout: {transcript}", flush=True)
                    results.append({
                        "segment": name,
                        "success": "partial",
                        "elapsed": elapsed,
                        "transcript": transcript,
                        "error": "Timeout en LLM pero transcripción recibida"
                    })
                    segment_index += 1
                except:
                    results.append({
                        "segment": name,
                        "success": False,
                        "elapsed": elapsed,
                        "error": "Timeout completo"
                    })
                    segment_index += 1
            
            except websockets.exceptions.ConnectionClosedError as e:
                print(f"⚠️  Conexión cerrada durante procesamiento: {e}", flush=True)
                print(f"   Reconectando y reintentando {name}...", flush=True)
                ws = None  # Forzar reconexión
                await asyncio.sleep(1)  # Esperar un poco antes de reconectar
                # No incrementar segment_index para reintentar
                
            except Exception as e:
                elapsed = time.time() - start_time
                print(f"❌ ERROR en {name} después de {elapsed:.2f}s: {e}", flush=True)
                import traceback
                traceback.print_exc()
                results.append({
                    "segment": name,
                    "success": False,
                    "elapsed": elapsed,
                    "error": str(e)
                })
                segment_index += 1
            
            # Pequeña pausa entre segmentos
            if segment_index < len(segments):
                await asyncio.sleep(0.5)
                
        except ConnectionRefusedError:
            print(f"❌ Error: No se pudo conectar a {WS_URL}", flush=True)
            print("   Asegúrate de que el servidor esté corriendo:", flush=True)
            print("   uvicorn backend.server:app --reload", flush=True)
            return 1
        except Exception as e:
            print(f"❌ Error de conexión: {e}", flush=True)
            import traceback
            traceback.print_exc()
            ws = None
            await asyncio.sleep(2)  # Esperar antes de reintentar
    
    # Cerrar conexión si está abierta
    if ws:
        try:
            print("\n📤 Enviando señal __END__", flush=True)
            await ws.send(json.dumps({"text": "__END__"}))
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=LLM_TIMEOUT)
                data = json.loads(response)
                transcript = data.get("transcript", "(vacío)")
                print(f"✅ Respuesta final después de __END__: {transcript}", flush=True)
                results.append({
                    "segment": "Final (__END__)",
                    "success": True,
                    "transcript": transcript
                })
            except:
                print("ℹ️  No hay audio pendiente para procesar", flush=True)
        except Exception:
            # La conexión ya está cerrada o hay un error
            pass
        finally:
            try:
                await ws.close()
            except:
                pass
    
    # Resumen (igual que antes)
    print("\n" + "=" * 60, flush=True)
    print("📊 RESUMEN DE RESULTADOS", flush=True)
    print("=" * 60, flush=True)
    for r in results:
        status = "✅" if r.get("success") == True else "⚠️" if r.get("success") == "partial" else "❌"
        if r.get("success"):
            elapsed = r.get("elapsed", 0)
            duration = r.get("duration", "N/A")
            transcript = r.get("transcript", "N/A")
            print(f"{status} {r['segment']}: {elapsed:.2f}s", flush=True)
            print(f"   📝 Transcripción: {transcript}", flush=True)
            if duration != "N/A":
                print(f"   ⏱️  Duración: {duration}s, RMS: {r.get('rms', 'N/A')}", flush=True)
        elif r.get("success") == "partial":
            elapsed = r.get("elapsed", 0)
            transcript = r.get("transcript", "N/A")
            print(f"{status} {r['segment']}: {elapsed:.2f}s (parcial)", flush=True)
            print(f"   📝 Transcripción: {transcript}", flush=True)
            print(f"   ⚠️  {r.get('error', '')}", flush=True)
        else:
            print(f"{status} {r['segment']}: {r.get('error', 'Error')}", flush=True)
    
    success_count = sum(1 for r in results if r.get("success") == True)
    partial_count = sum(1 for r in results if r.get("success") == "partial")
    total_count = len(results)
    print(f"\n✅ Éxito completo: {success_count}/{total_count}", flush=True)
    if partial_count > 0:
        print(f"⚠️  Parcial (transcripción OK, LLM timeout): {partial_count}/{total_count}", flush=True)
    
    if success_count == total_count:
        print("🎉 ¡Todas las pruebas pasaron!", flush=True)
        return 0
    else:
        print("⚠️  Algunas pruebas fallaron o tuvieron timeout", flush=True)
        return 1

if __name__ == "__main__":
    print("🚀 Iniciando prueba de segmentos de audio...", flush=True)
    print(f"📡 Conectando a {WS_URL}", flush=True)
    print("⚠️  Asegúrate de que el servidor esté corriendo en el puerto 8000\n", flush=True)
    
    try:
        exit_code = asyncio.run(test_multiple_segments())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Prueba interrumpida por el usuario", flush=True)
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error fatal: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)