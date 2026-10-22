# feat: CPU mode — device selection, measured model subset, cancellable jobs

Adds a real CPU mode. The old CPU path ran the GPU code (float16 autocast, default chunk overlap, shifts/TTA on) and a 5 s clip never finished; disabling autocast and halving the overlap brought the same models to 8–52 s for the same clip.

## What changed

- **Device selection** — `UVR_DEVICE=auto|cuda|cpu`, resolved in one place. `cuda` fails loudly rather than silently falling back to CPU. CPU profile disables autocast/TF32, caps threads to the cgroup quota, and applies cheaper per-architecture inference params.
- **Measured model subset** — `cpuOk` flag in both catalogues, kept in sync by `verify-catalog.py`. Cutoff: ≤15 s per 5 s clip on the reference rig; **4 of 45 models** pass. Others are refused up front and shown as "No CPU".
- **Cancellable jobs** — separation runs in a child process, so cancel and the per-job timeout actually kill the work; a native crash takes down the child, not the API.
- **Progress + ETA** — progress comes from the library's tqdm loop; the ETA was computed from a 0–100 value treated as a fraction, so it always read 0.0 s.
- **Limits** — 120 s clip / 64 MB upload / 30 min job timeout on CPU, refused at submit with the limit quoted.
- **CPU container** — slim Python image with CPU torch wheels, compose override, `run-local.sh --cpu`, CI cpu job, CPU stage in `verify-all.sh`.
- **Catalogue fixes** — `bs_polarformer_vocals` and `mel_band_roformer_fv8b` marked `unsupported` (they fail to load on both devices).

## Measurements

- **Reference hardware** in the README: RTX 2060 + 16 vCPU / 8 physical cores + 38 GB. Minimum: 4 cores, 4 GB RAM.
- **4-core re-measurement** (`taskset -c 0-3` + `UVR_CPU_THREADS=4`): the 4 enabled models are 1.3–1.7× slower than on 16 vCPU; a 2-min clip still finishes in 4–8 min.
- **Audio Repair neural pass on CPU**: `mdx_dereverb` on a 118 s clip takes **593 s (9.9 min)**, inside the 30-min job timeout.
- **Timeout margin corrected**: ~5× (slowest enabled model ~5.3 min for a 2-min clip against the 30-min ceiling), not the 30× previously claimed.

## CI fix in this PR

The new `cpu` job's `requirements-cpu.txt` was broken: `torch==2.8.0+cpu` failed to resolve. The `+cpu` local version tag lives only on `download.pytorch.org`, and a **second `--index-url` line is silently ignored by pip** (only the last one wins), so the CPU index dropped out of the resolve entirely and pip saw only PyPI's plain builds.

Fixed by making the CPU index the **primary** `--index-url` and PyPI the **extra** `--extra-index-url`. Verified on Python 3.10 (the CI interpreter): the pinned triple `torch-2.8.0+cpu` / `torchvision-0.23.0+cpu` / `torchaudio-2.8.0+cpu` resolves from `manylinux_2_28_x86_64`, and **no CUDA packages** (`cuda-toolkit`, `nvidia-*`) are pulled in.

## Verification

`scripts/verify-all.sh` **ALL GREEN** (7/7). `scripts/verify-catalog.py` 15/15. `scripts/test-cpu-mode.py` 20/20. Browser session against the production build: health/notice/picker gating/limit errors, progress + ETA over the socket, playback with Range seeking, download bundle, cancel killing the child process, GPU mode unaffected, mobile viewport. Notes + screenshots in `docs/results/cpu-ui-check-2026-10-22.md`.

The `cpu` CI job in `.github/workflows/ci.yml` runs the CPU-mode test suite end to end on a CPU-only runner.
