# UVR Local

A local-first clone of `uvrvocalremover.com`'s rich web UI — professional vocal
removal, karaoke making and stem splitting that runs **100% on your own GPU**.
No uploads, no watermarks, no usage caps.

- **Web:** Next.js 14 (App Router) + Tailwind CSS + Radix UI
- **Worker:** FastAPI + [audio-separator](https://github.com/nomadkaraoke/python-audio-separator) on CUDA, with vendored MSST modules for HyperACE checkpoints
- **Deploy:** Docker Compose with NVIDIA GPU passthrough

## Quick start (Docker)

```bash
cd ~/docker/uvr-stack
docker compose up -d --build
# optional: cp .env.example .env  — every value has a working default

# verify
docker compose ps
curl localhost:3000           # web UI
curl localhost:8000/api/health  # GPU worker → {"gpu":true,...}
```

The first build pulls the CUDA base image (~6 GB) and installs torch cu128, so
expect several minutes. Later rebuilds are much faster — but a change to
`requirements.txt` invalidates the pip layer and re-installs everything.

## Quick start (dev, no Docker)

```bash
# 1. API worker — uv provisions a matching interpreter + torch cu128 on first run
cd ~/docker/uvr-stack/api
./run-local.sh                # http://localhost:8000  (PORT=8001 to override)

# 2. Web
cd ~/docker/uvr-stack/web
npm install
npm run dev                   # http://localhost:3000
```

Use `run-local.sh` instead of rebuilding the image while iterating. It shares
`./models` with Docker (so weights are downloaded once) but writes results to
`./output-local`, because the container runs as root and a shared `./output`
would come back root-owned. There is no `--reload`; restart the process after
editing anything under `api/`.

## What's inside

| Area | Highlights |
|------|-----------|
| **Design system** | Exact tokens from the site: dual-theme CSS vars, glassmorphism, noise overlay, indigo glow, staggered entrance animations |
| **Components** | Radix-backed primitives (`components/ui/*`) composed into the workbench: file upload, model selection, results, stem player, ensemble builder, comparison player, model matrix, model manager |
| **Pages** | Landing, 9 tool scenes, explore/model matrix, pricing, FAQ |
| **API** | Next.js route handlers → FastAPI worker: jobs, models, health, ensemble, WebSocket live updates |
| **Inference** | Standalone `audio-separator` (RoFormer / Mel-Band RoFormer / MDXC / Demucs / VR) on CUDA, plus a vendored MSST path for HyperACE checkpoints that upstream cannot load; ensemble engine (avg/median/max/min FFT + wave) |

## Model catalog

Seeded from verified HuggingFace sources (BS-RoFormer, Mel-Band RoFormer,
MDX23C, HTDemucs): **14 runnable, 2 marked `unsupported`** (hidden by the
picker). A catalog entry resolves weights one of two ways:

- `download` — an explicit repo + file list, fetched into `./models/<id>/`
- `registry` — a filename in `audio-separator`'s own model registry, which
downloads and configures the checkpoint itself

`audio-separator` only ever searches **its own registry** — it never falls back
to a file already sitting in the model directory — so an entry needs one of
those two fields to be usable at all. Weights auto-download on first use and are
cached in `./models`.

## Docs

- [Architecture](docs/ARCHITECTURE.md)
- [Design tokens](docs/DESIGN_TOKENS.md)
- [Deployment](docs/DEPLOY.md)

## License

MIT — see [LICENSE](LICENSE).