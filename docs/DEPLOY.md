# Deployment

## Prerequisites

- Docker with the **NVIDIA Container Toolkit** (`nvidia-ctk runtime configure`)
- An NVIDIA GPU (≥ 4 GB VRAM recommended; verified on RTX 2060)
- ~10 GB free disk for the CUDA base image and the torch cu128 wheels

Inference is self-contained — there is no MSST-WebUI checkout to install or mount.

## Docker Compose

```bash
cd ~/docker/uvr-stack
docker compose up -d --build

# optional — every value already has a working default
cp .env.example .env
```

Services:

| Service | Port | Notes |
|---------|------|-------|
| `web` | 3000 | Next.js standalone build, runs `node server.js` |
| `api` | 8000 | FastAPI worker, NVIDIA device reservation |

Host bind mounts (no named volumes):

| Host path | Container | Notes |
|-----------|-----------|-------|
| `./api` | `/app` | worker code — restart to pick up edits (`uvicorn` has no `--reload`) |
| `./models` | `/data/models` | weight cache; inspectable, and seedable by hand |
| `./output` | `/data/output` | results, `jobs.json`, and uploads |
| `~/music` | `/data/input:ro` | optional input drop folder |

⚠️ The `api` container runs as **root**, so anything it writes under `./output`
is root-owned and the host user can no longer create per-job upload directories
there. For development prefer `./run-local.sh`, which writes to `./output-local`.
The clean fix is a `user: "${UID}:${GID}"` entry on the service plus a one-time
`sudo chown -R $USER output`.

## Smoke test

```bash
curl -s localhost:8000/api/health    # {"gpu":true,"gpuName":"NVIDIA GeForce RTX 2060 ..."}
curl -s localhost:8000/api/models | head -c 200
curl -s localhost:3000 | head        # HTML
```

## Bare metal (no Docker)

`uv` provisions its own interpreter: the host Python may be newer than the CUDA
wheels support (torch cu128 has no 3.13+ builds).

```bash
cd ~/docker/uvr-stack/api
./run-local.sh          # first run does `uv sync`; then http://localhost:8000
```

`run-local.sh` exports `MODEL_CATALOG`, `MODEL_STORE` (`../models`) and
`OUTPUT_ROOT` (`../output-local`), and honours `PORT` and env overrides.

Web:

```bash
cd ~/docker/uvr-stack/web
npm install
npm run dev        # or: npm run build && npm start
```

Point the web build at the local worker with
`NEXT_PUBLIC_WS_URL=ws://localhost:8000` — the browser opens the job socket
itself. The `/api/*` proxy needs no configuration because it already defaults to
`http://localhost:8000`.

## Adding models

Add the entry to **both** `api/models.json` (id-keyed) and
`web/src/lib/models.ts` (`MODEL_CATALOG`) — the UI filters on its own static copy,
so a flag present only in the backend never reaches the picker. See
[Architecture](ARCHITECTURE.md).

Weight resolution needs one of:

1. `"download"` — an explicit HuggingFace file list:

   ```json
   "download": {
     "repo": "<org>/<repo>",
     "revision": "main",
     "files": [
       { "remote": "mel_band_roformer/foo.ckpt", "dest": "foo.ckpt" },
       { "remote": "mel_band_roformer/foo_config.yaml", "dest": "config.yaml" }
     ]
   }
   ```

   List the real filenames first with
   `curl -s https://huggingface.co/api/models/<repo> | jq '.siblings[].rfilename'`.
   A RoFormer needs **both** the `.ckpt` and its matching config YAML — a
   checkpoint without its own config cannot be loaded, and substituting a
   different config silently loads the wrong architecture.
2. `"registry": "<filename>"` — an exact name from
   `Separator().list_supported_model_files()`.
3. `"unsupported": true` — when neither exists, so the picker hides the entry
   instead of failing at runtime.

Restart the worker; the model then appears in `/api/models` and the picker.

## CI

`.github/workflows/ci.yml` runs web lint + typecheck + build, an API
`py_compile` and `docker compose build` on every push. See the repo root for the
workflow file.