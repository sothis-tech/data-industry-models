# Experimentos de Evaluación

Este directorio contiene scripts para ejecutar evaluaciones de transcripción con tracking de experimentos usando MLflow.

## Instalación

```bash
pip install -r requirements-dev.txt
```

## Uso

### Ejecutar evaluación con MLflow

```bash
# Baseline (sin mejoras)
python experiments/run_evaluation_with_mlflow.py --experiment-name baseline

# Con reducción de ruido
python experiments/run_evaluation_with_mlflow.py --experiment-name noise_reduction_v1 --noise-reduction

# Con filtro paso banda
python experiments/run_evaluation_with_mlflow.py --experiment-name bandpass_filter_v1 --bandpass-filter

# Con ambos
python experiments/run_evaluation_with_mlflow.py --experiment-name full_pipeline_v1 --noise-reduction --bandpass-filter

# Prueba rápida (solo 50 muestras)
python experiments/run_evaluation_with_mlflow.py --experiment-name quick_test --max-samples 50
```

### Ver resultados en MLflow UI

```bash
mlflow ui
```

Luego abre http://localhost:5000 en tu navegador.

## Comparar experimentos

En la UI de MLflow puedes:
- Ver todas las métricas (WER, CER, tiempos)
- Comparar diferentes experimentos lado a lado
- Ver los parámetros de cada experimento
- Descargar los resultados detallados (CSV)

## Estructura

- `run_evaluation_with_mlflow.py`: Script principal para ejecutar evaluaciones con tracking
- `mlruns/`: Directorio donde MLflow guarda los experimentos (en .gitignore)