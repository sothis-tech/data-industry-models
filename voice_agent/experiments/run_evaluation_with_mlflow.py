"""
Script para ejecutar evaluación de transcripción con tracking MLflow.

Uso:
    python experiments/run_evaluation_with_mlflow.py --experiment-name "baseline"
    python experiments/run_evaluation_with_mlflow.py --experiment-name "noise_reduction_v1" --noise-reduction
    python experiments/run_evaluation_with_mlflow.py --experiment-name "bandpass_filter_v1" --bandpass-filter

Ver resultados:
    mlflow ui
    # Abre http://localhost:5000
"""
import sys
import os
import argparse
import importlib
from pathlib import Path
from datetime import datetime

# Agregar raíz del proyecto al path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import mlflow
# Importar el módulo (no la función directamente) para poder recargarlo
import scripts.test_transcription_accuracy as transcription_module

def track_experiment(experiment_name: str, config_params: dict):
    """
    Ejecuta evaluación y trackea resultados en MLflow.
    
    Args:
        experiment_name: Nombre del experimento (ej: "baseline", "noise_reduction_v1")
        config_params: Diccionario con parámetros de configuración
    """
    # Configurar experimento (MLflow crea el experimento si no existe)
    mlflow.set_experiment(experiment_name)

    # Crear nombre del run con timestamp para que sea único
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = f"{experiment_name}_{timestamp}"

    # Crear directorio de salida único para este experimento
    # Esto evita que use el cache de experimentos anteriores
    experiment_output_dir = project_root / "output" / "experiments" / experiment_name / timestamp
    experiment_output_dir.mkdir(parents=True, exist_ok=True)
    
    # Establecer variables de entorno ANTES de recargar el módulo
    os.environ["OUTPUT_DIR"] = str(experiment_output_dir)
    if config_params.get("max_samples") is not None:
        os.environ["MAX_SAMPLES"] = str(config_params.get("max_samples"))
    else:
        # Asegurarse de que no haya un valor previo
        os.environ.pop("MAX_SAMPLES", None)
    
    # Recargar el módulo para que lea las nuevas variables de entorno
    importlib.reload(transcription_module)

    # Iniciar run (el run_id se genera automáticamente)
    with mlflow.start_run(run_name=run_name):
        # Loggear parámetros de configuración
        mlflow.log_params({
            "whisper_model": config_params.get("whisper_model", "medium"),
            "whisper_lang": config_params.get("whisper_lang", "es"),
            "llm_model": config_params.get("llm_model", "phi3:mini"),
            "min_rms": config_params.get("min_rms", 0.001),
            "silence_wait_ms": config_params.get("silence_wait_ms", 2000),
            "vad_mode": config_params.get("vad_mode", 3),
            "noise_reduction": config_params.get("noise_reduction", False),
            "bandpass_filter": config_params.get("bandpass_filter", False),
            "max_samples": config_params.get("max_samples", None),
        })
        
        # Ejecutar evaluación (usar la función recargada)
        print(f"\n🚀 Ejecutando evaluación para experimento: {experiment_name}")
        print(f"📁 Directorio de salida: {experiment_output_dir}")
        if config_params.get("max_samples"):
            print(f"📊 Limitando a {config_params.get('max_samples')} muestras")
        print("=" * 60)
        results = transcription_module.main()
        
        if results is None:
            print("❌ Error: La evaluación no retornó resultados")
            # Limpiar variables de entorno
            os.environ.pop("OUTPUT_DIR", None)
            os.environ.pop("MAX_SAMPLES", None)
            return
        
        # Loggear métricas principales
        stats = results["stats"]
        mlflow.log_metrics({
            "wer_mean": stats.get("wer_mean", 0),
            "wer_median": stats.get("wer_median", 0),
            "wer_std": stats.get("wer_std", 0),
            "wer_min": stats.get("wer_min", 0),
            "wer_max": stats.get("wer_max", 0),
            "cer_mean": stats.get("cer_mean", 0),
            "cer_median": stats.get("cer_median", 0),
            "cer_std": stats.get("cer_std", 0),
            "cer_min": stats.get("cer_min", 0),
            "cer_max": stats.get("cer_max", 0),
            "time_mean": stats.get("time_mean", 0),
            "time_total": stats.get("time_total", 0),
            "time_total_script": stats.get("time_total_script", 0),
            "total_samples": stats.get("total_samples", 0),
            "valid_samples": stats.get("valid_samples", 0),
            "failed_samples": stats.get("failed_samples", 0),
        })
        
        # Loggear artefactos (CSV con resultados detallados)
        if results.get("output_csv") and Path(results["output_csv"]).exists():
            mlflow.log_artifact(results["output_csv"], "results")
        
        if results.get("output_stats") and Path(results["output_stats"]).exists():
            mlflow.log_artifact(results["output_stats"], "results")
        
        # Loggear tags para facilitar búsqueda
        mlflow.set_tags({
            "experiment_type": "transcription_evaluation",
            "whisper_model": config_params.get("whisper_model", "medium"),
            "has_noise_reduction": config_params.get("noise_reduction", False),
            "has_bandpass_filter": config_params.get("bandpass_filter", False),
        })
        
        # Loggear también el directorio de salida como tag para referencia
        mlflow.set_tag("output_dir", str(experiment_output_dir))
        
        # Obtener run_id después de iniciar el run
        run_id = mlflow.active_run().info.run_id
        
        print("\n" + "=" * 60)
        print(f"✅ Experimento '{experiment_name}' trackeado en MLflow")
        print(f"   Run ID: {run_id}")
        print(f"   WER promedio: {stats.get('wer_mean', 0):.2f}%")
        print(f"   CER promedio: {stats.get('cer_mean', 0):.2f}%")
        print(f"   Muestras válidas: {stats.get('valid_samples', 0)}/{stats.get('total_samples', 0)}")
        print(f"   📁 Resultados guardados en: {experiment_output_dir}")
        print("=" * 60)
        print("\n💡 Para ver los resultados:")
        print("   mlflow ui")
        print("   # Abre http://localhost:5000 en el navegador")
        
        # Limpiar variables de entorno al finalizar
        os.environ.pop("OUTPUT_DIR", None)
        os.environ.pop("MAX_SAMPLES", None)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ejecutar evaluación de transcripción con MLflow tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Baseline
  python experiments/run_evaluation_with_mlflow.py --experiment-name baseline

  # Con reducción de ruido
  python experiments/run_evaluation_with_mlflow.py --experiment-name noise_reduction_v1 --noise-reduction

  # Con filtro paso banda
  python experiments/run_evaluation_with_mlflow.py --experiment-name bandpass_filter_v1 --bandpass-filter

  # Con ambos
  python experiments/run_evaluation_with_mlflow.py --experiment-name full_pipeline_v1 --noise-reduction --bandpass-filter

  # Limitar muestras para prueba rápida
  python experiments/run_evaluation_with_mlflow.py --experiment-name quick_test --max-samples 50
        """
    )
    
    parser.add_argument("--experiment-name", required=True, 
                       help="Nombre del experimento (ej: 'baseline', 'noise_reduction_v1')")
    parser.add_argument("--whisper-model", default="medium", 
                       help="Modelo Whisper (tiny, base, small, medium, large)")
    parser.add_argument("--whisper-lang", default="es", 
                       help="Idioma para Whisper")
    parser.add_argument("--llm-model", default="phi3:mini", 
                       help="Modelo LLM (no usado en evaluación, solo para tracking)")
    parser.add_argument("--min-rms", type=float, default=0.001, 
                       help="MIN_RMS (no usado en evaluación, solo para tracking)")
    parser.add_argument("--silence-wait-ms", type=int, default=2000, 
                       help="SILENCE_WAIT_MS (no usado en evaluación, solo para tracking)")
    parser.add_argument("--vad-mode", type=int, default=3, 
                       help="VAD mode (0-3, no usado en evaluación, solo para tracking)")
    parser.add_argument("--noise-reduction", action="store_true", 
                       help="Indica si se usó reducción de ruido (para tracking)")
    parser.add_argument("--bandpass-filter", action="store_true", 
                       help="Indica si se usó filtro paso banda (para tracking)")
    parser.add_argument("--max-samples", type=int, default=None, 
                       help="Limitar número de muestras para prueba rápida")
    
    args = parser.parse_args()
    
    config = {
        "whisper_model": args.whisper_model,
        "whisper_lang": args.whisper_lang,
        "llm_model": args.llm_model,
        "min_rms": args.min_rms,
        "silence_wait_ms": args.silence_wait_ms,
        "vad_mode": args.vad_mode,
        "noise_reduction": args.noise_reduction,
        "bandpass_filter": args.bandpass_filter,
        "max_samples": args.max_samples,
    }
    
    track_experiment(args.experiment_name, config)
