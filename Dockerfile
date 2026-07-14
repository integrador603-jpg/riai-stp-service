# Imagen base con Python 3.11 y dependencias de OpenCASCADE precompiladas
FROM python:3.11-slim

# Dependencias del sistema que necesita cadquery/OCC
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglu1-mesa \
    libgomp1 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY app.py .

# Puerto
EXPOSE 5001

CMD ["/bin/sh", "-c", "gunicorn app:app --workers 2 --timeout 120 --bind 0.0.0.0:${PORT:-5001}"]
