# UVR Local GPU worker
FROM nvidia/cuda:12.8.0-cudnn-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3.10-venv python3-pip ffmpeg libsndfile1 \
    build-essential libsamplerate0-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python 3.10 venv
RUN python3.10 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# App code
COPY . .

# Self-contained inference — no MSST-WebUI checkout is mounted or required.
# NOTE: deliberately do NOT set AUDIO_SEPARATOR_MODEL_DIR. It globally
# overrides the model_file_dir passed to Separator(), which would clobber the
# local model-store path. The registry cache location is chosen per-call in
# backend.py instead.
ENV OUTPUT_ROOT=/data/output \
    MODEL_CATALOG=/app/models.json \
    MODEL_STORE=/data/models

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]