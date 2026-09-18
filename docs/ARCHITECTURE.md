# Architecture

```
┌────────────────────────────────┐        ┌──────────────────────────────┐
│  Browser  (localhost:3000)     │        │  FastAPI worker (:8000)      │
│                                │        │                              │
│  Next.js 14 App Router         │  REST  │  /api/health  /api/models    │
│  ┌──────────────────────────┐  │ ─────► │  /api/jobs    /api/ensemble  │
│  │ route handlers /api/*    │  │        │  /api/models/storage         │
│  │  proxy + gzip + ETag     │  │ ◄───── │  /api/jobs/{id}/stems/{name} │
│  └──────────────────────────┘  │        │  /api/jobs/{id}/download     │
│  Zustand store + hooks         │   WS   │                              │
│  Radix UI + Tailwind           │ ─────► │  /ws/jobs (status broadcast) │
└────────────────────────────────┘        │                              │
                                          │  JobQueue — one job at once  │
                                          │    └─ backend.py             │
                                          │        ├─ audio-separator    │
                                          │        └─ vendor/msst        │
                                          └──────────────────────────────┘
```

There is **no database**. State lives in memory (`JobQueue`, `ModelManager`)
and is persisted as JSON + files on disk (`OUTPUT_ROOT/jobs.json`,
`MODEL_STORE/*/manifest.json`).

## Request flow

1. The user drops a file in the workbench (`components/scenes/file-upload-card`)
   → `createJob()` (XHR, upload progress) → `POST /api/jobs` (Next route handler)
   → forwards the multipart body to the worker.
2. The worker saves the upload under `OUTPUT_ROOT/uploads/`, enqueues a `Job`
   and returns `{ jobId, status, etaSec }`.
3. The browser adds the job to the Zustand store; `useJobs` subscribes to
   `/ws/jobs` for live progress and falls back to backoff polling (2s → 30s cap)
   while the socket is disconnected.
4. The worker processes jobs serially on the GPU, broadcasting status →
   `queued → processing(gpu) → ready`.
5. Ready jobs expose per-stem URLs (`/api/jobs/{id}/stems/{name}`, HTTP **Range**
   enabled so playback can seek) and a bundle download
   (`/api/jobs/{id}/download?format=zip|wav|flac|mp3`). `StemPlayer` decodes the
   audio in-browser to draw a waveform and syncs playback across stems via a
   shared sync group.

## Key modules

### Web (`web/src`)
- `lib/types.ts` — shared contracts (Model, Job, Scene, Ensemble)
- `lib/api.ts` — fetch wrappers, `friendlyApiError()`, WebSocket client
- `lib/http-json.ts` — `jsonResponse()`: gzip + weak ETag + `no-cache` revalidation for proxy GETs
- `lib/models-api.ts` — model store calls (list / download / cancel / delete)
- `lib/store.ts` — Zustand store, persisted to localStorage (`uvr-local-store`)
- `lib/models.ts` — seeded `MODEL_CATALOG` + scene metadata + `modelsForScene()`
- `lib/ensemble.ts`, `lib/licenses.ts` — ensemble presets, license metadata
- `components/ui/*` — Radix primitives (shadcn-style)
- `components/layout/*` — Header, Footer, AppShell, Hero, SceneTabs, WorkbenchSidebar
- `components/scenes/*` — the workbench: `file-upload-card`, `model-selection-card`, `results-card`
- `components/explore/*` — ModelMatrix, ComparisonPlayer, EnsembleBuilder
- `components/models/model-manager.tsx` — download / delete installed weights
- `app/api/*` — route handlers that proxy to the worker

⚠️ The UI renders models from the **static** `MODEL_CATALOG` in `lib/models.ts`,
not from the live `/api/models` response. Catalog flags such as `unsupported`
therefore have to be kept in sync in **both** `api/models.json` and
`lib/models.ts` — adding one only to the backend never reaches the picker.

### Worker (`api`)
- `main.py` — FastAPI app, `/api/*` routes, HTTP Range streaming, WebSocket, ensemble fusion
- `backend.py` — inference: weight resolution, `_AudioSeparatorBackend`, MSST fallback routing
- `model_manager.py` — model store: download / verify / delete, mtime-keyed JSON caches
- `job_queue.py` — serial GPU queue, status broadcaster, persists `OUTPUT_ROOT/jobs.json`
- `models.json` — seeded catalog (id-keyed) with `download` / `registry` specs
- `vendor/msst/` — vendored MSST-WebUI inference for HyperACE architectures

## Inference backends

`backend.get_backend()` returns the single `_AudioSeparatorBackend`. Separation
happens in two stages.

### 1. Resolving the weights

A catalog entry must supply one of:

- `download` — `{repo, revision, files: [{remote, dest, size}]}`, fetched from
  HuggingFace into `MODEL_STORE/<model_id>/`
- `registry` — a filename from `audio-separator`'s own
  `list_supported_model_files()` registry (VocalRemover / MDX / Demucs / MDXC),
  which downloads and configures the model itself into `MODEL_STORE/.registry/`
- `unsupported: true` — refused **before** any download, with a clear message

This matters because `Separator.load_model()` calls `download_model_files()`
first, and that only searches the library's curated registry — it never falls
back to a file already sitting in the model directory. For models we manage
ourselves, `backend.py` temporarily swaps `sep.download_model_files` for a stub
returning the tuple it would have computed, then restores it. That lets a raw
MSST-style RoFormer `config.yaml` load unchanged (the library just YAML-loads it
and sets `is_roformer=True`).

### 2. Choosing the engine

- If the config declares `use_mask_estimator_hyper_ace` / `hyperace_version`, or
  the **checkpoint contains `hyperace` weight keys**, `_separate_with_msst()`
  runs the vendored MSST `demix()` path. Detection has to inspect the weights,
  because the published HyperACE configs are plain BS-RoFormer configs that never
  declare the flag. `audio-separator`'s `BSRoformer` lacks those modules and
  calls `sys.exit(1)` on the resulting state-dict mismatch, so routing has to be
  decided *before* handing the model over.
- Otherwise the standard `audio-separator` path runs.

⚠️ `job_queue` catches `(Exception, SystemExit)` and wraps the worker loop in
`except BaseException` (re-raising `CancelledError`). Without that, a single bad
checkpoint would kill the uvicorn process and take the whole API down.

⚠️ Do **not** set `AUDIO_SEPARATOR_MODEL_DIR` — it globally overrides the
`model_file_dir` passed to `Separator()` and clobbers the local model store.

## Ensemble engine

`POST /ensemble` loads the stems of 2–6 ready jobs, aligns them, and fuses in
the frequency domain (`avg_fft`, `median_fft`, `max_fft`, `min_fft` — STFT with
overlap-add) or time domain (`avg_wave`, `median_wave`). Weights are normalized.