FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY main.py .
ENV CHROMA_HOST=industrial-chromadb \
    CHROMA_PORT=8000 \
    CHROMA_COLLECTION=manuales_tecnicos \
    DOCS_PATH=/data/rag_docs \
    HF_HOME=/data/hf_cache \
    PORT=8300
EXPOSE 8300
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8300"]
