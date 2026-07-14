FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglu1-mesa \
    libgomp1 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-import cadquery at build time so the first request isn't slow
RUN python3 -c "import cadquery; print('cadquery OK')"

COPY app.py .

EXPOSE 5001

CMD ["/bin/sh", "-c", "gunicorn app:app --workers 1 --timeout 300 --bind 0.0.0.0:${PORT:-5001} --log-level info"]
