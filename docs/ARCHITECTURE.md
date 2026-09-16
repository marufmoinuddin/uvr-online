# Architecture

```
┌──────────────────────────────┐        ┌──────────────────────────────┐
│  Browser (localhost:3000)    │        │  FastAPI worker (:8000)      │
│                              │        │                              │
│  Next.js 14 (App Router)     │  REST  │  /health  /models  /jobs     │
│  ┌────────────────────────┐  │ ─────► │  /jobs/{id}/reuse  /ensemble │
│  │ Route handlers (/api/*)│  │        │  /ws/jobs (WebSocket)        │
│  └────────────────────────┘  │ ◄───── │                              │
│  Zustand store + hooks       │  WS    │  JobQueue (serial GPU)       │
│  Radix UI + Tailwind         │        │  └─ inference.py             │
└──────────────────────────────┘        │     ├─ MSST MSSeparator ◄── MSST-WebUI checkout
                                        │     └─ pymss (fallback)      │
                                        └──────────────────────────────┘
```

## Request flow

1. User drops a file in `DropZone` → `ScenePanel` calls `createJob()` (XHR with
   upload progress) → `POST /api/jobs` (Next route handler) → forwards multipart
   to the worker.
2. Worker saves the upload, enqueues a `Job`, returns `{ jobId, status, etaSec }`.
3. The browser adds the job to the Zustand store; `useJobs` subscribes to
   `/ws/jobs` for live progress (falls back to 2s polling).
4. The worker processes jobs serially on the GPU, broadcasting status →
   `queued → processing(gpu) → ready`.
5. Ready jobs expose per-stem URLs (`/jobs/{id}/stems/{name}`) and a ZIP bundle
   (`/jobs/{id}/download`). `StemPlayer` decodes the audio in-browser to draw a
   waveform and syncs playback across stems via a shared sync group.

## Key modules

### Web (`web/src`)
- `lib/types.ts` — shared contracts (Model, Job, Scene, Ensemble)
- `lib/api.ts` — fetch wrappers + WebSocket client
- `lib/store.ts` — Zustand store, persisted to localStorage
- `lib/models.ts` — seeded catalog + scene metadata
- `components/ui/*` — Radix primitives (shadcn-style)
- `components/layout/*` — Header, Footer, AppShell, Hero, SceneTabs
- `components/scenes/*` — `ScenePanel` (dropzone + model + options + submit)
- `components/explore/*` — ModelMatrix, ComparisonPlayer, EnsembleBuilder
- `app/api/*` — route handlers that forward to the worker

### Worker (`api`)
- `main.py` — FastAPI app, endpoints, WebSocket, ensemble fusion
- `inference.py` — backend resolution (MSST → pymss) + `separate_file()`
- `job_queue.py` — async serial queue + status broadcaster
- `models.json` — seeded catalog with checkpoint mappings

## Inference backends

`inference.get_backend()` resolves in order:

1. **MSST-WebUI** — if `MSST_ROOT/inference/msst_infer.py` exists, wraps
   `MSSeparator`. Model resolution reads `data/models_info.json` to map catalog
   ids → installed checkpoints. This is the verified stack (RTX 2060, torch 2.7.1+cu128).
2. **pymss** — `Separator(model_id=..., device="cuda")` drop-in fallback.

## Ensemble engine

`POST /ensemble` loads the stems of 2–6 ready jobs, aligns them, and fuses in
the frequency domain (`avg_fft`, `median_fft`, `max_fft`, `min_fft` — STFT with
overlap-add) or time domain (`avg_wave`, `median_wave`). Weights are normalized.