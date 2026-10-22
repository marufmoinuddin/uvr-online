# CPU mode — web UI verification (2026-10-22)

Manual browser session against the production build (`next build` + `next
start`, port 3000) with the worker on `:8000`. Screenshots for this session
are in `docs/results/cpu-ui-check/`.

Stack under test:

- worker: `UVR_DEVICE=cpu` (and `auto` for the GPU-mode pass), catalogue and
  model store from the checkout
- web: built with `NEXT_PUBLIC_WS_URL=ws://localhost:8000` (the compose
  default), so the browser opens the job socket directly

## Checks performed

| Check | Result |
|---|---|
| Health through the web proxy shows `device: "cpu"`, `cpuMode: true`, 4 `cpuModels`, limits 120 s / 64 MB / 1800 s | ✅ |
| CPU-mode notice rendered in the model picker, quotes the real limits | ✅ (`uicheck-1-cpu-picker.png`) |
| Picker: enabled rows = the scene's `cpuOk` models; every other row shows **No CPU**, is disabled, and its accessible label reads "… — not available in CPU mode" (36 rows in Vocal Remover) | ✅ |
| Short clip (6 s) through `uvr_2hp`: job reaches `processing`, stage shows **CPU inference**, ETA is a real moving number (`ETA 25s`), job reaches `ready` | ✅ (`uicheck-3-processing.png`) |
| Stems play with seeking: `currentTime` advances, seek to 3 s lands at 4.1 s, stem URL answers **206 Partial Content** with `content-range` | ✅ |
| Download bundle returns a valid zip (`PK\x03\x04` magic) | ✅ |
| Over-length upload (130 s) refused at submit time with the limit quoted: *"CPU mode accepts clips up to 120 seconds. This one is 130.0 seconds…"* | ✅ (`uicheck-2-limit.png`) |
| A CPU-blocked model is refused with a clear message even when selected (server-side guard) | ✅ |
| Cancel from the UI: job shows `cancelled`, and the worker has **0 child processes** afterwards | ✅ |
| GPU mode (`UVR_DEVICE=auto`): no CPU notice, **0** "No CPU" labels, all 38 rows enabled, header reads "Unlimited · local" | ✅ (`uicheck-4-gpu-mode.png`) |
| Mobile viewport (390×844): no horizontal overflow, hamburger menu present, CPU notice fits (375 px) | ✅ (`uicheck-5-mobile.png`, `uicheck-6-mobile-cpu.png`) |
| Audio Repair (DSP + neural `mdx_dereverb`) completes on the CPU worker — 33/33 workflow checks | ✅ |
| Console: no errors after the socket targets `ws://localhost:8000`; only benign Next.js font-preload warnings and router-prefetch aborts | ✅ |

## Fixes this session produced

1. **The ETA was always 0.0.** `_on_progress` treated the 0-100 percentage as
   a fraction, so `(1.0 - pct)` was negative for every value above 1% and the
   ETA collapsed to zero for the whole run. Fixed in `api/job_queue.py`.

2. **Real per-chunk progress.** `audio-separator` has no callback; the worker
   reported a fake 10% and the bar sat still for the whole run. `tqdm` is
   now hooked (and restored after the run) so the bar moves per chunk and the
   ETA has something honest to derive from (`_install_progress_hook` in
   `api/backend.py`).

3. **Submit gate for stale selections.** The picker disables CPU-blocked rows,
   but a selection persisted from a GPU session could still submit one — the
   worker then refused the job *after* the upload. The submit button now uses
   the same rule as the picker (`file-upload-card.tsx`), so it is disabled
   with an explanatory tooltip instead. Audio Repair is exempt: it is
   CPU-friendly by design.

4. **The CPU speed guard broke Audio Repair on CPU workers.** The gate caught
   this: the backend refused the repair workflow's neural model (`mdx_dereverb`
   is not `cpuOk`) and both neural-repair jobs errored. Repair runs one light
   pass wrapped in DSP and is exempt by design — `separate_file` now takes
   `allow_cpu_blocked=True` from the repair workflow (the `unsupported` guard
   still applies), with a regression check in `scripts/test-cpu-mode.py`.

## Row counts in the picker: why 36 "No CPU" vs 38 rows

Reconciled against `api/models.json` (48 catalogue entries). The catalogue
itself has 4 `cpuOk` models and 5 `unsupported` (hidden), so 43 selectable
models globally, of which 39 are "No CPU". The per-scene numbers are smaller
because `modelsForScene()` filters by `target`.

In the **Vocal Remover** scene (`allowedTargets: ["instrumental", "dual"]`)
the picker renders **30 model cards**, of which **2 are enabled** (`uvr_2hp`,
target `dual`, and `mbr_guitar_becruily`, target `instrumental`) and **28 are
"No CPU"**.

The earlier 38/36 reading came from two counting mistakes, now corrected:

- The **36 "No CPU" badges** = 28 real model cards **+ 8 Ensemble presets**.
  The presets are fused-job shortcuts, not single models, but they render in
  the same grid and the label logic does not exempt them — so they carry the
  badge too. Cosmetically noisy, not incorrect.
- The **"38 enabled rows"** figure came from a **GPU-mode** count of a
  *different* scene (Stem Splitter). In GPU mode `cpuCapable()` returns `true`
  for every model, so every row is enabled regardless of `cpuOk` — that number
  says nothing about the CPU-capable set. Correct comparison in the same
  Vocal Remover scene: **2 enabled in CPU mode vs 30 in GPU mode**.

The 4 `cpuOk` models are `uvr_2hp` (dual), `mbr_guitar_becruily`
(instrumental), `htdemucs` (4-stem) and `htdemucs_6s` (multi); only the first
two fall in the Vocal Remover scene's target filter, which is why that scene
shows 2, not 4.

## Audio Repair neural pass on CPU (near the clip limit)

Timed the exempt repair path directly — `execute_repair_job` with a
neural-only `mdx_dereverb` plan on a **118 s** clip (just under the 120 s
separation-mode ceiling), CPU worker:

| | |
|---|---|
| Wall time | **593 s (9.9 min)** |
| Load model | 2.5 s |
| Inference | ~589 s (≈5.0× realtime) |
| Output | 118.0 s, rms 0.27, all samples finite |

Well inside the 30-minute job timeout — a near-limit repair clip on CPU
finishes in about ten minutes. Note the guard exemption is what allows this at
all: `mdx_dereverb` is **not** `cpuOk` and would be refused as a separation,
but the repair pipeline is exempt (`allow_cpu_blocked=True`), since its neural
model runs as one light pass wrapped in DSP.

**One bug this surfaced:** the progress bar sat at **1.0% for the entire
589 s** of inference (log shows `t=3.7s … t=592.4s` all at `1.0%`), then
jumped to "Saved" at the end. The dereverb model's inner loop never feeds the
`tqdm` hook the worker installed, so CPU-mode ETA for repair jobs is
meaningless. It still completes correctly — the ETA just reads "estimating…"
until the last second.

## Environment notes

- The web app was served by `next start`; an earlier pass served a **stale
  build** because `pkill -f "next start"` does not match the `next-server`
  process name — worth remembering when re-testing by hand.
- The first WS attempt went to `ws://localhost:3000` because the running
  server predated the rebuild that inlines `NEXT_PUBLIC_WS_URL`. With the
  shipped compose value the socket connects directly to the worker and the
  console is clean; without it the UI falls back to polling (which works).
