# Deployment

## Prerequisites

- Docker with the **NVIDIA Container Toolkit** (`nvidia-ctk runtime configure`)
- An NVIDIA GPU (≥ 4 GB VRAM recommended; verified on RTX 2060)
- A checkout of [MSST-WebUI](https://github.com/Anjok07/ultimatevocalremovergui)
  (primary inference backend) — or rely on the `pymss` fallback

## Docker Compose

```bash
cd ~/docker/uvr-stack
cp .env.example .env
# .env: MSST_ROOT=/home/maruf/git/MSST-WebUI

docker compose up -d --build
```

Services:

| Service | Port | Notes |
|---------|------|-------|
| `web` | 3000 | Next.js standalone build |
| `api` | 8000 | FastAPI worker, `--gpus all` reservation |
| `model_weights` | — | named volume for auto-downloaded checkpoints |

The worker mounts your MSST checkout at `/msst` (read-only) and keeps
auto-downloaded weights in the `model_weights` volume. Input music can be
dropped into `~/music` (mounted at `/data/input`).

## Smoke test

```bash
curl -s localhost:8000/health        # {"gpu":true,"gpuName":"NVIDIA GeForce RTX 2060 ..."}
curl -s localhost:8000/models | head
curl -s localhost:3000 | head        # HTML
```

## Bare-metal (no Docker)

The worker runs inside the MSST venv (torch + CUDA already configured):

```bash
cd ~/docker/uvr-stack/api
MSST_ROOT=/home/maruf/git/MSST-WebUI \
  uv run --project /home/maruf/git/MSST-WebUI uvicorn main:app --host 0.0.0.0 --port 8000
```

Web:

```bash
cd ~/docker/uvr-stack/web
npm install
npm run dev        # or: npm run build && npm start
```

## Adding models

1. Download a checkpoint + config into the MSST checkout
   (`pretrain/vocal_models/…` + `configs/vocal_models/….yaml`).
2. Register it in `data/models_info.json` (see the MSST-WebUI README).
3. Restart the worker — the model appears in `/api/models` and the combobox.

## CI

`.github/workflows/ci.yml` runs lint, typecheck, build and `docker compose build`
on every push. See the repo root for the workflow file.