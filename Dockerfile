FROM python:3.11-slim

WORKDIR /app

# libgl1 / libglib2.0-0 : dépendances système requises par opencv/ultralytics
# même en version "headless", pour le décodage d'images.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=5000
EXPOSE 5000

# --workers 1 : un seul thread caméra/portail actif à la fois (voir MANUEL_TECHNIQUE.md).
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120"]
