"""
Script de prueba para evaluar la precisión de transcripción de Whisper
comparando con las transcripciones originales del corpus Common Voice.
"""
import os
import csv
import time
import logging
from pathlib import Path
from typing import Dict, List, Tuple
import whisper
import numpy as np

# Configuración
# Obtener el directorio raíz del proyecto (dos niveles arriba de scripts/)
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "cv-corpus-22.0-delta-2025-06-20" / "es"
# Permitir override del OUTPUT_DIR mediante variable de entorno
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(PROJECT_ROOT / "output")))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CLIPS_DIR = DATA_DIR / "clips"
TSV_FILE = DATA_DIR / "other.tsv"
WHISPER_MODEL = "medium"
WHISPER_LANG = "es"
# Permitir override de MAX_SAMPLES mediante variable de entorno
MAX_SAMPLES_ENV = os.getenv("MAX_SAMPLES")
MAX_SAMPLES = int(MAX_SAMPLES_ENV) if MAX_SAMPLES_ENV else None  # None para procesar todos, o un número para limitar (ej: 100)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("transcription-test")

def load_whisper_model():
    """Carga el modelo Whisper"""
    log.info(f"Cargando modelo Whisper '{WHISPER_MODEL}'...")
    model = whisper.load_model(WHISPER_MODEL, device="cuda")
    log.info("Modelo Whisper cargado.")
    return model

def load_tsv_data(tsv_path: Path) -> List[Dict]:
    """Carga los datos del archivo TSV"""
    log.info(f"Cargando datos de {tsv_path}...")
    data = []
    with open(tsv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            data.append(row)
    log.info(f"Cargados {len(data)} registros del TSV.")
    return data

def normalize_text(text: str) -> str:
    """
    Normalización mejorada del texto para comparación:
    - Convertir a minúsculas
    - Remover puntuación al final de palabras (puntos, comas, etc.)
    - Normalizar espacios múltiples
    - Remover caracteres especiales innecesarios
    """
    import re
    if not text:
        return ""
    
    text = str(text)
    
    # Convertir a minúsculas
    text = text.lower()
    
    # Remover puntuación al final de palabras (pero mantener dentro de palabras)
    # Esto quita puntos, comas, punto y coma, dos puntos, etc. al final de palabras
    text = re.sub(r'([a-záéíóúñü])([.,;:!?¡¿]+)(?=\s|$)', r'\1', text)
    
    # Remover puntuación al inicio de palabras (como comillas de apertura)
    text = re.sub(r'(^|\s)([¡¿"\'«»]+)([a-záéíóúñü])', r'\1\3', text)
    
    # Remover puntuación al final de la frase completa
    text = re.sub(r'[.,;:!?¡¿]+$', '', text)
    
    # Normalizar comillas y guiones
    text = text.replace('"', '').replace("'", '').replace('«', '').replace('»', '')
    text = text.replace('—', ' ').replace('–', ' ').replace('-', ' ')
    
    # Remover espacios múltiples y normalizar
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def calculate_wer(reference: str, hypothesis: str) -> Tuple[float, int, int, int]:
    """
    Calcula Word Error Rate (WER)
    Returns: (WER, substitutions, insertions, deletions)
    """
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    
    # Algoritmo de Levenshtein para palabras
    n, m = len(ref_words), len(hyp_words)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    
    # Inicializar primera fila y columna
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    
    # Llenar la matriz
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_words[i-1] == hyp_words[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(
                    dp[i-1][j],      # deletion
                    dp[i][j-1],      # insertion
                    dp[i-1][j-1]     # substitution
                )
    
    # Calcular errores
    substitutions = insertions = deletions = 0
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref_words[i-1] == hyp_words[j-1]:
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i-1][j-1] + 1:
            substitutions += 1
            i -= 1
            j -= 1
        elif j > 0 and dp[i][j] == dp[i][j-1] + 1:
            insertions += 1
            j -= 1
        else:
            deletions += 1
            i -= 1
    
    total_words = len(ref_words)
    wer = (dp[n][m] / total_words * 100) if total_words > 0 else 0.0
    
    return wer, substitutions, insertions, deletions

def calculate_cer(reference: str, hypothesis: str) -> float:
    """
    Calcula Character Error Rate (CER)
    """
    ref_chars = list(reference.replace(' ', ''))
    hyp_chars = list(hypothesis.replace(' ', ''))
    
    n, m = len(ref_chars), len(hyp_chars)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_chars[i-1] == hyp_chars[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
    
    total_chars = len(ref_chars)
    cer = (dp[n][m] / total_chars * 100) if total_chars > 0 else 0.0
    
    return cer

def transcribe_audio(model, audio_path: Path) -> str:
    """Transcribe un archivo de audio usando Whisper"""
    try:
        result = model.transcribe(
            str(audio_path),
            language=WHISPER_LANG,
            task="transcribe",
            fp16=True
        )
        return (result.get("text") or "").strip()
    except Exception as e:
        log.error(f"Error transcribiendo {audio_path}: {e}")
        return ""

def load_existing_results(results_file: Path) -> Dict[str, Dict]:
    """Carga resultados existentes para evitar reprocesar"""
    existing = {}
    if results_file.exists():
        try:
            with open(results_file, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing[row['audio_file']] = row
            log.info(f"Cargados {len(existing)} resultados existentes de {results_file}")
        except Exception as e:
            log.warning(f"Error cargando resultados existentes: {e}")
    return existing

def append_result_to_csv(result: Dict, results_file: Path, fieldnames: List[str]):
    """Añade un resultado al CSV (modo append)"""
    file_exists = results_file.exists()
    
    with open(results_file, 'a', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(result)

def update_statistics_file(stats: Dict, stats_file: Path, processed_count: int, total_count: int):
    """Actualiza el archivo de estadísticas"""
    with open(stats_file, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("ESTADÍSTICAS DE TRANSCRIPCIÓN\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Progreso: {processed_count}/{total_count} muestras procesadas\n")
        f.write(f"Total de muestras: {stats.get('total_samples', 0)}\n")
        f.write(f"Muestras válidas: {stats.get('valid_samples', 0)}\n")
        f.write(f"Muestras fallidas: {stats.get('failed_samples', 0)}\n\n")
        
        if stats.get('valid_samples', 0) > 0:
            f.write("Word Error Rate (WER):\n")
            f.write(f"  Media: {stats.get('wer_mean', 0):.2f}%\n")
            f.write(f"  Mediana: {stats.get('wer_median', 0):.2f}%\n")
            f.write(f"  Desviación estándar: {stats.get('wer_std', 0):.2f}%\n")
            f.write(f"  Mínimo: {stats.get('wer_min', 0):.2f}%\n")
            f.write(f"  Máximo: {stats.get('wer_max', 0):.2f}%\n\n")
            f.write("Character Error Rate (CER):\n")
            f.write(f"  Media: {stats.get('cer_mean', 0):.2f}%\n")
            f.write(f"  Mediana: {stats.get('cer_median', 0):.2f}%\n")
            f.write(f"  Desviación estándar: {stats.get('cer_std', 0):.2f}%\n")
            f.write(f"  Mínimo: {stats.get('cer_min', 0):.2f}%\n")
            f.write(f"  Máximo: {stats.get('cer_max', 0):.2f}%\n\n")
        
        f.write("Tiempo:\n")
        f.write(f"  Media por muestra: {stats.get('time_mean', 0):.2f}s\n")
        f.write(f"  Tiempo total: {stats.get('time_total', 0):.2f}s\n")

def process_samples(model, data: List[Dict], max_samples: int = None, output_dir: Path = None) -> List[Dict]:
    """Procesa los audios y genera métricas, guardando progresivamente"""
    results = []
    total = len(data) if max_samples is None else min(max_samples, len(data))
    
    # Configurar archivos de salida
    if output_dir is None:
        output_dir = Path(OUTPUT_DIR / "test_results")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results_file = output_dir / "transcription_results.csv"
    stats_file = output_dir / "transcription_stats.txt"
    
    # Cargar resultados existentes
    existing_results = load_existing_results(results_file)
    
    # Definir fieldnames una vez
    fieldnames = [
        'audio_file', 'reference', 'reference_normalized', 'transcribed', 
        'transcribed_normalized', 'wer', 'cer', 'substitutions', 'insertions', 
        'deletions', 'time', 'error'
    ]
    
    log.info(f"Procesando {total} muestras...")
    log.info(f"Resultados se guardarán progresivamente en {results_file}")
    
    for idx, row in enumerate(data[:total] if max_samples else data):
        audio_file = row['path']
        reference_text = row['sentence']
        audio_path = CLIPS_DIR / audio_file
        
        # Saltar si ya está procesado
        if audio_file in existing_results:
            log.info(f"[{idx+1}/{total}] Ya procesado (saltando): {audio_file}")
            # Cargar resultado existente
            existing = existing_results[audio_file]
            # Convertir valores numéricos
            result = {
                'audio_file': existing['audio_file'],
                'reference': existing['reference'],
                'reference_normalized': existing.get('reference_normalized', ''),
                'transcribed': existing['transcribed'],
                'transcribed_normalized': existing.get('transcribed_normalized', ''),
                'wer': float(existing['wer']) if existing['wer'] and existing['wer'] != 'None' else None,
                'cer': float(existing['cer']) if existing['cer'] and existing['cer'] != 'None' else None,
                'substitutions': int(existing.get('substitutions', 0)) if existing.get('substitutions') else 0,
                'insertions': int(existing.get('insertions', 0)) if existing.get('insertions') else 0,
                'deletions': int(existing.get('deletions', 0)) if existing.get('deletions') else 0,
                'time': float(existing.get('time', 0)) if existing.get('time') else 0,
                'error': existing.get('error') if existing.get('error') else None
            }
            results.append(result)
            continue
        
        if not audio_path.exists():
            log.warning(f"Audio no encontrado: {audio_path}")
            continue
        
        log.info(f"[{idx+1}/{total}] Procesando: {audio_file}")
        
        # Transcribir
        start_time = time.time()
        transcribed_text = transcribe_audio(model, audio_path)
        transcription_time = time.time() - start_time
        
        if not transcribed_text:
            log.warning(f"Transcripción vacía para {audio_file}")
            result = {
                'audio_file': audio_file,
                'reference': reference_text,
                'reference_normalized': '',
                'transcribed': transcribed_text,
                'transcribed_normalized': '',
                'wer': None,
                'cer': None,
                'substitutions': 0,
                'insertions': 0,
                'deletions': 0,
                'time': transcription_time,
                'error': 'empty_transcription'
            }
            results.append(result)
            # Guardar inmediatamente
            append_result_to_csv(result, results_file, fieldnames)
            continue
        
        # Normalizar textos para comparación
        ref_norm = normalize_text(reference_text)
        hyp_norm = normalize_text(transcribed_text)
        
        # Calcular métricas
        wer, subs, ins, dels = calculate_wer(ref_norm, hyp_norm)
        cer = calculate_cer(ref_norm, hyp_norm)
        
        result = {
            'audio_file': audio_file,
            'reference': reference_text,
            'reference_normalized': ref_norm,
            'transcribed': transcribed_text,
            'transcribed_normalized': hyp_norm,
            'wer': wer,
            'cer': cer,
            'substitutions': subs,
            'insertions': ins,
            'deletions': dels,
            'time': transcription_time,
            'error': None
        }
        
        results.append(result)
        
        # Guardar inmediatamente
        append_result_to_csv(result, results_file, fieldnames)
        
        log.info(f"  Referencia: {reference_text[:60]}...")
        log.info(f"  Transcrito: {transcribed_text[:60]}...")
        log.info(f"  WER: {wer:.2f}%, CER: {cer:.2f}%, Tiempo: {transcription_time:.2f}s")
        log.info(f"  ✅ Guardado en {results_file}")
        
        # Actualizar estadísticas cada 10 muestras o al final
        if (idx + 1) % 10 == 0 or (idx + 1) == total:
            stats = calculate_statistics(results)
            update_statistics_file(stats, stats_file, idx + 1, total)
            log.info(f"  📊 Estadísticas actualizadas ({idx+1}/{total})")
    
    return results

def calculate_statistics(results: List[Dict]) -> Dict:
    """Calcula estadísticas generales"""
    valid_results = [r for r in results if r['wer'] is not None]
    
    if not valid_results:
        return {
            'total_samples': len(results),
            'valid_samples': 0,
            'failed_samples': len(results)
        }
    
    wers = [r['wer'] for r in valid_results]
    cers = [r['cer'] for r in valid_results]
    times = [r['time'] for r in valid_results]
    
    stats = {
        'total_samples': len(results),
        'valid_samples': len(valid_results),
        'failed_samples': len(results) - len(valid_results),
        'wer_mean': np.mean(wers),
        'wer_median': np.median(wers),
        'wer_std': np.std(wers),
        'wer_min': np.min(wers),
        'wer_max': np.max(wers),
        'cer_mean': np.mean(cers),
        'cer_median': np.median(cers),
        'cer_std': np.std(cers),
        'cer_min': np.min(cers),
        'cer_max': np.max(cers),
        'time_mean': np.mean(times),
        'time_total': np.sum(times),
    }
    
    return stats

def main():
    """Función principal"""
    log.info("=" * 60)
    log.info("SCRIPT DE PRUEBA DE TRANSCRIPCIÓN")
    log.info("=" * 60)
    
    # Leer variables de entorno (se pueden sobrescribir desde MLflow)
    # Estas se leen en tiempo de ejecución, no al importar el módulo
    output_dir_env = os.getenv("OUTPUT_DIR")
    max_samples_env = os.getenv("MAX_SAMPLES")
    
    # Usar variables de entorno o defaults
    output_dir_base = Path(output_dir_env) if output_dir_env else OUTPUT_DIR
    max_samples = int(max_samples_env) if max_samples_env else MAX_SAMPLES
    
    # Verificar que existen los directorios
    if not CLIPS_DIR.exists():
        log.error(f"Directorio de clips no encontrado: {CLIPS_DIR}")
        return None
    
    if not TSV_FILE.exists():
        log.error(f"Archivo TSV no encontrado: {TSV_FILE}")
        return None
    
    # Cargar modelo
    model = load_whisper_model()
    
    # Cargar datos
    data = load_tsv_data(TSV_FILE)
    
    if max_samples:
        log.info(f"Limitando a {max_samples} muestras para prueba rápida")
    else:
        log.info(f"Procesando todas las muestras disponibles ({len(data)} total)")
    
    # Configurar directorio de salida
    # Si OUTPUT_DIR fue modificado por variable de entorno, usar ese directamente
    # Si no, usar el subdirectorio test_results por defecto
    if output_dir_env:
        # Si se especificó OUTPUT_DIR, usarlo directamente (experimento MLflow)
        output_dir = output_dir_base
        log.info(f"📁 Usando directorio de experimento: {output_dir}")
    else:
        # Comportamiento por defecto (ejecución directa del script)
        output_dir = output_dir_base / "test_results"
        log.info(f"📁 Usando directorio por defecto: {output_dir}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Procesar muestras (con guardado progresivo)
    start_time = time.time()
    results = process_samples(model, data, max_samples, output_dir)
    total_time = time.time() - start_time
    
    # Calcular estadísticas finales
    stats = calculate_statistics(results)
    stats['time_total_script'] = total_time
    
    # Actualizar estadísticas finales
    stats_file = output_dir / "transcription_stats.txt"
    results_csv = output_dir / "transcription_results.csv"
    total_count = len(data) if max_samples is None else min(max_samples, len(data))
    update_statistics_file(stats, stats_file, len(results), total_count)
    
    # Mostrar resumen
    log.info("\n" + "=" * 60)
    log.info("RESUMEN FINAL")
    log.info("=" * 60)
    log.info(f"Total procesado: {stats.get('total_samples', 0)}")
    log.info(f"Válidos: {stats.get('valid_samples', 0)}")
    log.info(f"Fallidos: {stats.get('failed_samples', 0)}")
    if stats.get('valid_samples', 0) > 0:
        log.info(f"WER promedio: {stats.get('wer_mean', 0):.2f}%")
        log.info(f"CER promedio: {stats.get('cer_mean', 0):.2f}%")
    log.info(f"Tiempo total: {total_time:.2f}s")
    log.info(f"\n✅ Resultados guardados en {output_dir}")
    
    # Retornar resultados para MLflow
    return {
        "stats": stats,
        "results": results,
        "total_files": len(data),
        "valid_files": stats.get('valid_samples', 0),
        "output_csv": str(results_csv),
        "output_stats": str(stats_file),
        "output_dir": str(output_dir)
    }

if __name__ == "__main__":
    main()
