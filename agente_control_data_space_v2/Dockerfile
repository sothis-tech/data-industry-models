FROM python:3.12-slim

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar uv (gestor de paquetes rápido, compatible con pyproject.toml)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copiar ficheros de dependencias primero (mejor cache de capas)
COPY pyproject.toml uv.lock* ./

# Instalar dependencias sin el proyecto en sí
RUN uv sync --frozen --no-install-project --no-dev

# Copiar el código fuente (src/, config/, tests/, …)
COPY . .

# Instalar dependencias del proyecto
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# El código vive en src/; lo ponemos en el PYTHONPATH para imports 'engine.*',
# 'project.*', 'interfaces.*', 'servers.*' sin el prefijo 'src.'.
ENV PYTHONPATH=/app/src

EXPOSE 8081

# El entrypoint de la API vive ahora en src/interfaces/api.py.
# Se arranca desde /app para que los servidores MCP (src/servers/*.py) y la
# config (config/*.yaml) se resuelvan por ruta relativa.
CMD ["sh", "-c", "uvicorn interfaces.api:app --host 0.0.0.0 --port ${API_PORT:-8081}"]
