# UVR Stack

A local-first audio workbench — professional vocal removal, karaoke, stem
splitting and corrective audio repair that runs **entirely on your own
hardware**. No uploads, no watermarks, no usage caps, no API keys.

A from-scratch reimplementation of the workflow at `uvrvocalremover.com`: the UI
was rebuilt feature-for-feature against the reference, and the inference engine
was rebuilt on [`audio-separator`](https://github.com/nomadkaraoke/python-audio-separator)
plus a vendored copy of MSST-WebUI's model code for the HyperACE architectures
upstream cannot load.

| | |
|---|---|
| **Web** | Next.js 14 (App Router) · React 18 · TypeScript · Tailwind · Radix UI · Zustand |
| **Worker** | FastAPI · audio-separator · PyTorch 2.8 (CUDA 12.8 or CPU) · vendored MSST |
| **Deploy** | Docker Compose — with NVIDIA GPU passthrough, or CPU-only |

---

## Requirements

| | |
|---|---|
| **GPU** | **Optional.** NVIDIA GPU with the CUDA Container Toolkit. 4 GB VRAM is a practical starting point for smaller models. |
| **CPU** | **Optional.** x86-64 CPU with at least 4 cores and 4 GB RAM. See [CPU mode](#cpu-mode) for limits and supported models. |
| **Disk** | ~10 GB for the CUDA base image and torch wheels, plus ~4 GB of model weights as you use them. ~4 GB for the CPU image. |
| **Tooling** | Docker + NVIDIA Container Toolkit (GPU), or just Docker (CPU), or `uv` + Node 20 for dev mode. |

### CPU mode

CPU mode is **supported**, not a fallback that happens to exist. It was not
always: the first CPU attempt ran with float16 autocast enabled and the
models' default chunk overlap, and a **5-second** clip took over 40 minutes.
Turning autocast off and halving the overlap brought the same job down to
seconds.

**Benchmark baseline:** a modern x86-64 Linux host with 8 physical cores and
ample RAM, PyTorch 2.8. Every number in this section comes from that baseline,
on a **5-second** stereo clip at 44.1 kHz. **Minimum hardware: 4 cores, 4 GB
RAM** (8 GB if you want the Demucs models, which are the memory-hungry ones).
The same 4 enabled models were re-measured pinned to 4 cores: they take
1.3–1.7× longer than on the baseline, so a 2-minute clip still finishes in
**4–8 minutes** on 4 cores. CPU performance is machine-dependent — re-run
`scripts/benchmark-cpu.py` on your own host before changing which models are
enabled.

| Model | Architecture | GPU | CPU | CPU vs GPU | 2-min clip on CPU |
|---|---|---|---|---|---|
| `htdemucs_6s` | HTDemucs | 6.0 s | 8.4 s | 1.4× | ~3 min |
| `htdemucs` | HTDemucs | 5.9 s | 8.5 s | 1.4× | ~3 min |
| `uvr_2hp` | VR | 5.0 s | 9.7 s | 1.9× | ~4 min |
| `mbr_guitar_becruily` | MelBand-RoFormer | 4.6 s | 13.3 s | 2.9× | ~5 min |

**CPU mode supports a limited set of models. Others are disabled because they
are too slow.** Exactly **4 of the catalogue's 45 models** are marked
`cpuOk: true`; the picker shows the rest as "No CPU" and the worker refuses
them before anything is uploaded.

The cutoff, written down so it can be re-derived: **at most 15 s per 5 s clip**
on the reference machine — which extrapolates to roughly 6 minutes for a
2-minute clip, about **5× inside the 30-minute job timeout** (the slowest
enabled model, `mbr_guitar_becruily`, takes ~5.3 min for a 2-minute clip;
the 30-minute ceiling is a backstop, not the working limit). The first
rejected model, `htdemucs_ft`, takes 16.4 s for the same clip; the heaviest
models (`mbr_duality_v1`, `mbr_instvox_duality_v2`) need 280 s, and the
HyperACE pair — which runs through the vendored MSST path, a different and
slower code path — needs 123–126 s.

> The full table, with every model measured, is in
> [docs/results/cpu-benchmark-2026-10-22.md](docs/results/cpu-benchmark-2026-10-22.md).
> Reproduce it with `python3 scripts/benchmark-cpu.py`. The cutoff is one
> constant in that file; raising it re-admits models from the measured table.

CPU mode is bounded in two more ways:

| Limit | Default | Env var |
|---|---|---|
| Longest clip | 120 s | `UVR_CPU_MAX_SECONDS` |
| Largest upload | 64 MB | `UVR_CPU_MAX_BYTES` |
| Job wall clock | 30 min | `UVR_CPU_JOB_TIMEOUT` |

Over-long submissions are **refused up front**, with the limit quoted — not
accepted and then left stalling the queue. Models that were measured to be too
slow are refused the same way, and the picker marks them "No CPU" so you never
have to discover it after uploading.

---

## Quick start (prebuilt Docker images)

```bash
cd /path/to/uvr-online
docker compose pull
docker compose up -d

# optional — every value already has a working default
cp .env.example .env

# verify
curl localhost:3000/api/health   # web  → proxied to the worker
curl localhost:8000/api/health   # worker → {"gpu":true,"device":"cuda",...}
```

The default images are published to GHCR. Set `UVR_WEB_IMAGE` and
`UVR_API_IMAGE` if you use a mirror or a different image tag.

Results land in `./output`, model weights in `./models`, and input audio is read
read-only from `~/music`.

### Quick start (Docker, CPU-only)

No NVIDIA GPU? Use the CPU override — a slim Python base image with the CPU
torch wheels, roughly a gigabyte smaller and no CUDA runtime at all:

```bash
docker compose -f docker-compose.yml -f docker-compose.cpu.yml pull
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d
curl localhost:8000/api/health   # → {"gpu":false,"device":"cpu","cpuMode":true,...}
```

The override replaces the `api` service rather than adding a second one: the
GPU reservation is cleared, the image is `api/Dockerfile.cpu`, and `UVR_DEVICE`
is pinned to `cpu`. Everything else — the web container, the volumes, the
model store — is inherited, so the two stacks behave identically.

## Optional: build images locally

Use local builds when developing the image, testing unreleased changes, or
running from a fork that does not publish the default GHCR images.

```bash
cd /path/to/uvr-online
docker compose up -d --build

# CPU-only
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d --build
```

The first GPU build pulls the CUDA base image (~6 GB) and installs torch cu128,
so budget 15–20 minutes. Later rebuilds are faster, but editing
`api/requirements.txt` invalidates the pip layer and reinstalls everything.

## Quick start (dev, no Docker)

Use this while iterating — editing a `.py` file then takes effect on the next
process start instead of a ~15 minute image rebuild.

```bash
# 1. worker — uv provisions a matching interpreter + torch cu128 on first run
cd /path/to/uvr-online/api
./run-local.sh                 # http://localhost:8000  (PORT=8001 to override)

# ... or CPU-only, in a separate venv with the CPU torch wheels:
./run-local.sh --cpu

# 2. web
cd /path/to/uvr-online/web
npm install
npm run dev                    # http://localhost:3000
```

`run-local.sh` shares `./models` with Docker, so a weight is downloaded once
whichever side needs it. It deliberately does **not** share `./output`: the
container runs as root, so its output comes back root-owned and the host user
then cannot create the next job's upload directory. Dev writes to
`./output-local` instead. There is no `--reload` — restart the process after
editing anything under `api/`.

`--cpu` uses its own `.venv-cpu` rather than re-syncing `.venv`: the CUDA and
CPU wheels are different builds of the same torch version, and swapping one for
the other in place means re-downloading ~3 GB every time you switch.

> Both stacks claim ports 3000 and 8000. If `./run-local.sh` exits with a bind
> error, a compose container already holds the port: `docker compose stop`.

## Features

### 10 scenes

Routes are `/tools/<scene>`.

| Scene | Route | What it does |
|---|---|---|
| Vocal Remover | `/tools/vocal-remover` | Strip vocals, keep the instrumental |
| Extract Vocals | `/tools/extract-vocals` | Isolate the vocal track |
| Karaoke | `/tools/karaoke` | Turn a song into a karaoke track |
| Stem Splitter | `/tools/stem-splitter` | Split into drums / bass / vocals / other |
| Instrument Extractor | `/tools/instrument-extractor` | Pull one instrument out of a full mix |
| Audio Repair | `/tools/audio-repair` | Fix clicks, clipping, hum, hiss, uneven levels |
| Acapella | `/tools/acapella` | Pure acapella vocals |
| Vocal Tools | `/tools/vocal-tools` | Dereverb, male/female split, crowd removal |
| Production | `/tools/production` | Pitch shift, time stretch, alignment |
| Full Model Picker | `/tools/model-picker` | Every architecture in the catalogue |

**Instrument Extractor** exposes 10 targets — Bass, Drums, Guitar, Piano, Kick,
Snare, Toms, Hi-Hat, Ride, Crash. The six drum-family targets all come from a
single model, `drumsep_mdx23c`, discovered by observing what it actually emits
rather than by trusting its filename or checkpoint claims. The target list is
derived from each model's `instrumentTargets` in `api/models.json` and served by
`GET /api/instruments`.

### Ensembles

Pick 2–6 finished jobs, set per-model weights, and fuse them: `avg_fft`,
`median_fft`, `max_fft`, `min_fft` (STFT with overlap-add), or `avg_wave` and
`median_wave` in the time domain.

### Comparison player

Runs 2–4 models over **one** file and plays the results side by side on a shared
sync group. There is a single code path — a file goes to every selected model
sequentially and results stream in.

### Audio repair

Repair is corrective DSP, not separation. It never loads a checkpoint into VRAM,
so it stays fast and does not contend with a running separation job.

**7 ffmpeg DSP operations** — `declick`, `declip`, `dehum`, `depop`, `denoise`,
`gate`, `normalize`. They run in a fixed canonical order regardless of the order
you select them, and unknown operations are rejected rather than ignored.

**3 neural models**, each with a measured `primaryStem` — the bleed suppressor
returns `Instrumental`, the dereverb model returns `Dry`, the crowd model returns
`Other`. *Which* output is the repair is decided by declared metadata, never by
`outputs[0]`; if the declared stem is missing, the job fails with a message
naming what the model actually produced.

A plan is validated before a byte is uploaded, and output is rejected and deleted
if mean volume falls below −60 dBFS (a chain that silenced the signal) or if
duration drifts more than 0.5 s from the source.

> **Status: shipped, but quality unverified.** The pipeline is implemented and
> tested end-to-end against real ffmpeg. What has *not* been established is that
> it audibly improves anything — measured gains over a degraded fixture were
> de-reverb **+0.014**, bleed suppressor **+0.020**, crowd **+0.000**. Those
> correlations prove *stem routing*, not repair quality. Reference parity is not
> claimed. See [docs/AUDIO-REPAIR-GAP.md](docs/AUDIO-REPAIR-GAP.md).

---

## Model catalogue

**48 entries, 45 runnable, 3 marked `unsupported`** (hidden by the picker).
Available to the UI as 56 model ids — the extra 8 are ensemble presets with no
weights of their own.

| Architecture | Count |
|---|---|
| MelBand-RoFormer | 26 |
| BS-RoFormer | 10 |
| HTDemucs | 4 |
| MDX23C | 3 |
| MDX-C | 2 |
| BS-PolarFormer, HybridDemucs, VR | 1 each |

Every runnable entry resolves its weights exactly one of two ways:

- **`download`** (12 entries) — an explicit HuggingFace repo pinned to a commit
  SHA, with the exact `size` and `sha256` of every file, fetched into
  `./models/<id>/` and verified on load by `model_manager._verify()`.
- **`registry`** (34 entries) — a filename in audio-separator's own model
  registry, which downloads and configures the checkpoint itself into a shared
  `models/.registry/` cache.

This distinction is not cosmetic. `Separator.load_model()` calls
`download_model_files()` first, and that **only** searches the library's curated
registry — it will never fall back to a file already sitting in the model
directory. An entry with neither field is unfetchable, full stop. Weights
auto-download on first use and are cached in `./models`.

### The 3 unsupported entries

| id | Why |
|---|---|
| `hdemucs_mmi` | Inference completes but the **write** fails: `Audio data must contain only finite values`. Reproduced on 3 recordings; the checkpoint re-downloaded byte-for-byte identical, so it is not corruption. |
| `bs_roformer_inst_hyperacev2_ckpt` | Uses the proprietary HyperACE architecture the standalone backend does not implement. |
| `mel_band_roformer_fv9` | No download source or registry equivalent configured. |

### Provenance is pinned

`scripts/pin-provenance.py` resolves each HuggingFace repo's `main` to a commit
SHA and writes `revision` plus exact `size` and `sha256` per file into
`api/models.json`. 12/12 specs and 24/24 files are pinned, so a re-download that
returns different bytes is caught rather than silently used.

---

## Architecture

```
┌────────────────────────────────┐        ┌──────────────────────────────┐
│  Browser  (localhost:3000)     │        │  FastAPI worker (:8000)      │
│  Next.js 14 App Router         │  REST  │  /api/jobs  /api/models      │
│  route handlers /api/* proxy   │ ─────► │  /api/health /api/instruments│
│  Zustand + Radix + Tailwind    │        │  /api/repair/* /api/ensemble  │
│                                │   WS   │                              │
│  polls every ~10s, live socket │ ─────► │  JobQueue — one job at once   │
└────────────────────────────────┘        │    └─ backend.py             │
                                          │        ├─ audio-separator     │
                                          │        └─ vendor/msst         │
                                          └──────────────────────────────┘
```

**There is no database.** State lives in memory (`JobQueue`, `ModelManager`) and
is persisted as JSON and files on disk (`OUTPUT_ROOT/jobs.json`,
`MODEL_STORE/*/manifest.json`).

Jobs are processed **serially**, one at a time, on whichever device the worker
is configured for. The browser subscribes to `/ws/jobs` for live progress and
falls back to backoff polling (2 s → 30 s) while the socket is down. Ready jobs
expose per-stem URLs with HTTP **Range** enabled so playback can seek, plus a
bundle download as `zip` / `wav` / `flac` / `mp3`.

Each separation runs in its own **child process**, so a cancelled or timed-out
job is genuinely stopped rather than left burning CPU in the background — and a
native crash inside torch takes down the child, not the API.

Full detail — including why HyperACE routing has to be decided *before* a model
is handed to audio-separator — is in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## API

23 REST routes and one WebSocket, all under `/api` on port 8000.

| | |
|---|---|
| `GET /api/health` | GPU name, free VRAM, queue depth, **active device**, CPU thread budget, CPU model list and limits |
| `GET /api/instruments` | Instrument targets, derived from each model's own metadata |
| `GET /api/models` · `/api/models/storage` · `/api/models/{id}` | Catalogue, live install status, on-disk size |
| `POST /api/models/{id}/download` · `/cancel` · `DELETE /api/models/{id}` | Manage weights |
| `POST /api/jobs` | Create a job (multipart, 1 GB cap) |
| `GET` / `DELETE /api/jobs[/{id}]` | List, inspect, delete |
| `POST /api/jobs/{id}/reuse` · `/cancel` | Re-run the same file against another model |
| `GET /api/jobs/{id}/stems/{name}` | One stem, Range enabled |
| `GET /api/jobs/{id}/download` | Bundle, `?format=zip\|wav\|flac\|mp3` |
| `POST /api/ensemble` | Fuse ≥ 2 jobs |
| `GET /api/repair/ops` · `/capabilities` | What repair may offer, derived from the worker |
| `WS /ws/jobs` | Full snapshot on connect, then one message per event |

> ⚠️ The catalogue exists in **two** places — `api/models.json` and the static
> `MODEL_CATALOG` in `web/src/lib/models.ts` — and the UI renders the static one.
> Adding a model or flipping `unsupported` in only the backend never reaches the
> picker. `scripts/verify-catalog.py` exists to catch exactly this drift.

---

## Tooling

```bash
./scripts/verify-all.sh          # the full 6-stage pre-flight gate
./scripts/verify-all.sh --quick  # skips the production build
```

Stages: catalogue integrity → verifier/writer/gate-lifecycle tests → backend
`py_compile` → repair pipeline against real ffmpeg → stem naming and VRAM
release → typecheck, lint, build and a browser smoke test.

| Script | Purpose |
|---|---|
| `verify-catalog.py` | Cross-checks the two catalogues; exits non-zero on drift |
| `probe-registry-model.py` | Can a registry model be fetched, loaded and run *here*? |
| `probe-sandbox-models.py` | Probes non-registry models through the real worker path |
| `pin-provenance.py` | Pins each HF repo to a commit SHA plus per-file hashes |
| `test-repair*.py` | Repair DSP, coordinator and neural-model acceptance tests |
| `restart-worker.sh` | Restarts the worker with no orphans and no leaked VRAM |
| `start-web.sh` | Start/restart Next.js on :3000 |

> **The gate never stops a process it did not start.** It builds into
> `.next-verify` on port 3100 under its own process group, because `next build`
> and a running server share `.next`. The consequence: a green gate does **not**
> mean the server on :3000 is serving your latest frontend code — rebuild before
> testing by hand. Never use `pkill next` in a gate.

---

## Docker images

`.github/workflows/docker.yml` builds all three images on every push and pushes
them to GHCR using the automatic `GITHUB_TOKEN`, so there is no registry secret
to configure.

| Image | Context | Base |
|---|---|---|
| `uvr-api` | `./api` | `nvidia/cuda:12.8.0-cudnn-devel-ubuntu22.04` |
| `uvr-api-cpu` | `./api` (`Dockerfile.cpu`) | `python:3.10-slim-bookworm` — CPU torch wheels, no CUDA runtime |
| `uvr-web` | `./web` | `node:20-alpine` |

Tagged with the long commit SHA on every commit, plus `<branch>` and `latest` on
the default branch only. `.github/workflows/ci.yml` separately runs lint,
typecheck and build on pushes to `main` and on every pull request, builds both
worker images, and runs the CPU-mode test suite end to end.

---

## Known limitations

- **CPU mode is slower and more limited.** A CPU run is 1.5–7× slower than a
  GPU run, so CPU mode caps the clip length, the upload size and the job
  wall clock, and refuses the models that were measured to be too slow. See
  [CPU mode](#cpu-mode). It is a real mode, not a token one.
- **Audio repair quality is unverified.** The code ships and works; whether it
  improves audio is unproven. See
  [docs/AUDIO-REPAIR-GAP.md](docs/AUDIO-REPAIR-GAP.md).
- **One job at a time.** The queue is serial by design — concurrent GPU jobs
  starve VRAM, which then masquerades as checkpoint corruption.
- **`NEXT_PUBLIC_*` values are inlined at build time.** Setting them at runtime
  has no effect; changing one means a rebuild.
- **Speech separation is out of scope.** SpeechBrain's `sepformer-wsj02mix` is a
  two-speaker *speech* model, not a singing-voice tool, so it is not offered.
- **Two catalogues must stay in sync.** See [API](#api).

## Docs

- [Architecture](docs/ARCHITECTURE.md) — request flow, backends, ensemble engine, gate isolation
- [Audio repair gap analysis](docs/AUDIO-REPAIR-GAP.md) — what is built vs. what is proven
- [Design tokens](docs/DESIGN_TOKENS.md)
- [Deployment](docs/DEPLOY.md)

## License

MIT — see [LICENSE](LICENSE).

Third-party model weights carry their own licenses, shown per model in the UI.