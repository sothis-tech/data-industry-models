# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Build SPA (Vite/React)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /build

# Instalación tolerante si package-lock está desfasado respecto al registry en CI
COPY frontend/ ./
RUN npm install --no-audit --no-fund \
    && npm run build

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API + estáticos (misma origen para / y /api; ver backend/main.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

WORKDIR /app

# Solo dependencias runtime (pytest opcional fuera del contenedor prod)
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip wheel \
    && grep -Ev '^(pytest|pytest-asyncio)' /app/backend/requirements.txt > /tmp/req-runtime.txt \
    && pip install --no-cache-dir -r /tmp/req-runtime.txt

COPY backend/ /app/backend/
COPY --from=frontend-builder /build/dist /app/frontend/dist

WORKDIR /app/backend

EXPOSE 8844

# FastAPI sirve openapi.json siempre → buen health cheap
HEALTHCHECK --interval=30s --timeout=8s --start-period=25s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8844/openapi.json')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8844"]
