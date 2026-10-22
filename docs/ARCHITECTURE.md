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

## Device selection

`backend.resolve_device()` is the **single** source of truth for where
inference runs. The worker, the health endpoint, the queue and the model guard
all ask it, so they cannot disagree — a job labelled "GPU" that actually ran on
the CPU is exactly the kind of lie this project exists to eliminate.

| `UVR_DEVICE` | Behaviour |
|---|---|
| `auto` (default) | CUDA when a usable GPU is present, otherwise CPU |
| `cuda` | CUDA or **fail loudly** — never a silent fallback |
| `cpu` | CPU, even on a machine that has a GPU |

`cuda` failing rather than falling back is deliberate: a silent fallback turns
"I asked for the GPU" into a CPU job that runs for an hour, and the user only
finds out from the elapsed time.

### The CPU profile

On the CPU, `backend.configure_runtime()` and the per-architecture parameter
overrides turn off every fast-but-approximate path:

- **autocast off.** `use_autocast=True` means float16/bf16 matmuls. On a GPU
  that is a win; on a CPU many of those kernels are missing and fall back to
  something *slower* than plain float32. This one setting was the difference
  between "never finishes" and "finishes in seconds".
- **TF32 off**, float32 matmul at `highest` precision.
- **Thread budget.** `effective_cpu_threads()` takes the smallest of the CPU
  affinity mask, the cgroup quota and the host core count — and only ever
  *reduces* torch's own default. A container with a 2-CPU quota still reports
  the host's 16 cores to `os.cpu_count()`, and 16 threads fighting over a
  2-CPU quota is the classic CPU oversubscription slowdown.
- **Cheaper inference.** `mdx_params` / `vr_params` / `demucs_params` /
  `mdxc_params` get a lower overlap, batch size 1, and no shifts or TTA. The
  vendored MSST path gets the same treatment through `CPU_PROFILE`
  (`batch_size` 1, `num_overlap` 2).

These are a **separate profile**, not inline conditionals, so tuning the GPU
settings can never quietly change the CPU ones.

⚠️ The parameter names above are the ones `audio-separator` actually reads
(verified against 0.47). An unknown key is silently ignored — a typo would
cost an order of magnitude in time and say nothing.

### The CPU model subset

Each catalog entry carries `cpuOk: true|false`, set from **measurement**
(`scripts/benchmark-cpu.py`), not from the architecture name. In CPU mode the
worker refuses the others before any weight is downloaded, with an error that
names the model and says what to do instead. The flag exists in **both**
catalogs and `scripts/verify-catalog.py` fails the build if they drift.

The cutoff is a single number — **15 s per 5 s clip** on the reference
machine — currently admitting 4 of 45 models. The measurement behind it is
in `docs/results/cpu-benchmark-2026-10-22.md`.

## Job execution

Separation runs in a **child process** (`api/sep_worker.py`), not in a thread:

- A Python thread cannot be killed. A cancelled or timed-out CPU job would
  keep burning every core for the remaining (possibly hours-long) inference
  while the queue reported it as cancelled, and every job behind it would
  wait. Killing the process is the only way to actually stop the work.
- A native crash — a CUDA OOM inside torch used to abort the whole worker
  with an uncatchable SIGSEGV — now takes down the child, not the API.

The parent polls a `multiprocessing.Queue` for `("progress", …)` /
`("result", …)` / `("error", …)` messages, enforces a per-job wall-clock
ceiling (`backend.job_timeout()`), and terminates the child on cancel or
timeout. Audio Repair stays on a thread: it is ffmpeg DSP, which is fast and
cancels cleanly.

## Ensemble engine

`POST /ensemble` loads the stems of 2–6 ready jobs, aligns them, and fuses in
the frequency domain (`avg_fft`, `median_fft`, `max_fft`, `min_fft` — STFT with
overlap-add) or time domain (`avg_wave`, `median_wave`). Weights are normalized.
---

## Verification gate — process ownership

`scripts/verify-all.sh` must never stop a process it did not start.

Historically it did. The frontend stage ran
`pkill -f 'next dev|next-server|next start'` so its build could not collide with
a running server, because `next build` and a running server share the `.next`
directory. The visible symptom was a **production server on :3000 dying every
time the gate ran** — the gate terminated the application, it did not leave a
stale one behind. (`next build` was blamed; the `pkill` in the old
`verify-web.sh` was the actual cause.)

The fix is isolation rather than killing:

| | Application | Verification |
|---|---|---|
| Build directory | `.next` | `.next-verify` (`UVR_NEXT_DIST_DIR`) |
| Port | 3000 | 3100 (`UVR_VERIFY_PORT`) |
| Shutdown | operator | the gate's own process group only |

`scripts/verify-web.sh` registers `EXIT`/`INT`/`TERM` traps **before** starting
anything, starts the temporary server under `setsid` so it has its own process
group, and signals that group on the way out. `cleanup()` preserves `$?` so a
failing gate cannot be turned green by its own teardown. A listener already on
the verification port is reported as a failure, never killed.

`scripts/test-gate-lifecycle.sh` (gate stage 2) asserts all of this: success and
failure both release the port, SIGINT/SIGTERM release it, an app on :3000 keeps
its exact PID across a full gate run, a squatter on :3100 is reported not killed,
and the exit code survives cleanup.

### Consequence: the gate no longer refreshes the app build

Because verification builds into `.next-verify`, running `./scripts/verify-all.sh`
no longer updates `.next`. That is the point — the gate must not touch the
application's build — but it means a green gate does **not** mean the server on
:3000 is serving your latest frontend code.

```bash
# after changing web/ and before testing by hand:
cd web && ./node_modules/.bin/next build && <restart next start>
```

`scripts/start-web.sh` should grow a build step so this cannot be forgotten.
