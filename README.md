# UVR Local

A local-first clone of `uvrvocalremover.com`'s rich web UI — professional vocal
removal, karaoke making and stem splitting that runs **100% on your own GPU**.
No uploads, no watermarks, no usage caps.

- **Web:** Next.js 14 (App Router) + Tailwind CSS + Radix UI
- **Worker:** FastAPI + the [MSST-WebUI](https://github.com/Anjok07/ultimatevocalremovergui) stack (with a `pymss` fallback)
- **Deploy:** Docker Compose with NVIDIA GPU passthrough

## Quick start (Docker)

```bash
cd ~/docker/uvr-stack
cp .env.example .env          # set MSST_ROOT to your MSST-WebUI checkout
docker compose up -d --build

# verify
docker ps
curl localhost:3000           # web UI
curl localhost:8000/health    # GPU worker
```

## Quick start (dev, no Docker)

```bash
# 1. API worker (uses the MSST venv already in this workspace)
cd ~/docker/uvr-stack/api
MSST_ROOT=/home/maruf/git/MSST-WebUI \
  uv run --project /home/maruf/git/MSST-WebUI uvicorn main:app --port 8000

# 2. Web
cd ~/docker/uvr-stack/web
npm install
npm run dev                   # http://localhost:3000
```

## What's inside

| Area | Highlights |
|------|-----------|
| **Design system** | Exact tokens from the site: dual-theme CSS vars, glassmorphism, noise overlay, indigo glow, staggered entrance animations |
| **Components** | 25+ Radix-backed primitives: `ModelCombobox`, `DropZone`, `StemPlayer` (waveform + synced seek), `JobConsole`, `DownloadBundle`, `ModelCard`, `PricingCard`, `EnsembleBuilder` |
| **Pages** | Landing, 9 tool scenes, explore/model matrix, pricing, FAQ |
| **API** | Next.js route handlers → FastAPI worker: jobs, models, health, ensemble, WebSocket live updates |
| **Inference** | MSST `MSSeparator` bridge (verified on RTX 2060) with `pymss` fallback; ensemble engine (avg/median/max/min FFT + wave) |

## Model catalog

Seeded from verified HF sources (BS-RoFormer, Mel-Band RoFormer, MDX23C,
HTDemucs) and merged at runtime with the models actually installed in your
MSST-WebUI checkout. Models auto-download on first use.

## Docs

- [Architecture](docs/ARCHITECTURE.md)
- [Design tokens](docs/DESIGN_TOKENS.md)
- [Deployment](docs/DEPLOY.md)

## License

MIT — see [LICENSE](LICENSE).