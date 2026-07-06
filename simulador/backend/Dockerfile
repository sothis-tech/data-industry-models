# backend/Dockerfile
FROM python:3.11-slim

# Evita que Python escriba archivos .pyc y fuerza salida por consola
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalamos dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el código
COPY . .

# Exponemos el puerto de la API (8000) y el de OPC UA (5679)
EXPOSE 8000
EXPOSE 5679

# Arrancamos con Uvicorn (Para producción masiva cambiaríamos a Gunicorn)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]