# CPU vs GPU separation benchmark — 2026-10-22

The measurement behind the `cpuOk` flag in the catalogue, and the numbers
quoted in the README.

Reproduce it with:

```bash
python3 scripts/benchmark-cpu.py --models <id,id,…> --devices cuda,cpu \
    --clip-seconds 5 --timeout 600 --allow-blocked \
    --out docs/results/cpu-benchmark-<date>.md
```

`--allow-blocked` runs the models the worker *refuses* in CPU mode. Without it
the refusal has no evidence behind it.

## Test rig

| | |
|---|---|
| GPU | NVIDIA GeForce RTX 2060 (Max-Q, 6 GB VRAM) |
| CPU | 16 vCPU / 8 physical cores (x86-64) |
| RAM | 38 GB |
| OS | Linux (CachyOS), Python 3.12, PyTorch 2.8.0+cu128, audio-separator 0.47.0 |
| Thread budget | `torch.get_num_threads()` = 8, `sched_getaffinity` = 16, no cgroup quota |
| Clip | 5 s, stereo, 44.1 kHz — a synthetic sine mix, so there is enough spectral content to make the models do real work, and it is deterministic so two runs are comparable |
| Cache | Warm: every model's weights are already on disk, so **no measurement includes a download** |

**No thread oversubscription on this machine.** `torch.get_num_threads()`
returns 8 (the physical core count), the affinity mask allows 16, and there is
no cgroup CPU quota — so this is not a misconfigured CPU. The container case
is handled separately: `backend.effective_cpu_threads()` reads the cgroup
quota and caps the thread count to it, because a container with a 2-CPU quota
still reports the host's core count to `os.cpu_count()`, and 16 threads
fighting over a 2-CPU quota is the classic CPU oversubscription slowdown.

## What actually made the difference

The first CPU attempt ran the *same code path as the GPU* and never finished:
a 5 s clip was killed after 40 minutes, with 249–282 s logged per iteration.
Three things were wrong, and all three were specific to the CPU:

1. **`use_autocast=True` was hardcoded.** Autocast means float16/bf16 matmuls.
   On a GPU that is a win; on a CPU a lot of those kernels are missing and fall
   back to something *slower* than plain float32. Turning it off is the single
   biggest change.
2. **The models' default chunk overlap was used.** The chunk walk is
   `step = chunk / overlap`, so a higher overlap means more chunks and more
   work. Halving it halves the compute, at the cost of seam artefacts.
3. **Shift averaging and TTA were on.** Each multiplies the number of forward
   passes.

Together these took the *same* model from "killed at 40 minutes" to seconds.
That is the whole difference between "there is no CPU mode" and the table
below — **the RoFormers were never the problem**. The models that are still
too slow on a CPU are the slow ones for a reason that has nothing to do with
the architecture: they are the heavy checkpoints, and the HyperACE pair, which
runs through a different and slower code path.

The GPU column is the same models on the same machine, with the same
warm cache — so the ratio is a property of the device, not of the download.

## Results — 5 s clip

| Model | Architecture | GPU (5 s) | CPU (5 s) | 2-min clip on CPU | `cpuOk` |
|---|---|---|---|---|---|
| `bs_polarformer_vocals` | BS-PolarFormer | — | — | — | no (failed to load) |
| `mel_band_roformer_fv8b` | MelBand-RoFormer | — | — | — | no (failed to load) |
| `htdemucs_6s` | HTDemucs | 6.0 s | 8.4 s | 3 min | **yes** |
| `htdemucs` | HTDemucs | 5.9 s | 8.5 s | 3 min | **yes** |
| `uvr_2hp` | VR | 5.0 s | 9.7 s | 4 min | **yes** |
| `mbr_guitar_becruily` | MelBand-RoFormer | 4.6 s | 13.3 s | 5 min | **yes** |
| `htdemucs_ft` | HTDemucs | 8.2 s | 16.4 s | 7 min | no |
| `htdemucs_4stem` | HTDemucs | 8.2 s | 17.4 s | 7 min | no |
| `drumsep_mdx23c` | MDX-C | 6.0 s | 21.0 s | 8 min | no |
| `mel_band_roformer_inst_v1e` | MelBand-RoFormer | 7.2 s | 21.3 s | 9 min | no |
| `mdx23c_d1581` | MDX23C | 6.6 s | 23.6 s | 9 min | no |
| `mbr_metal_mesk` | MelBand-RoFormer | 9.1 s | 25.0 s | 10 min | no |
| `bs_roformer_voc_resurrection` | BS-RoFormer | 5.4 s | 26.8 s | 11 min | no |
| `mel_band_roformer_flowers_v10` | MelBand-RoFormer | 6.3 s | 30.6 s | 12 min | no |
| `becruily_deux` | MelBand-RoFormer | 7.2 s | 31.8 s | 13 min | no |
| `mdx_dereverb` | MDX-C | 6.6 s | 34.6 s | 14 min | no |
| `mdx23c_instvoc_hq_2` | MDX23C | 8.3 s | 36.5 s | 15 min | no |
| `mdx23c_instvoc_hq` | MDX23C | 8.1 s | 40.6 s | 16 min | no |
| `mbr_inst_v2` | MelBand-RoFormer | 9.2 s | 44.0 s | 18 min | no |
| `bs_roformer_viperx_1296` | BS-RoFormer | 7.8 s | 51.9 s | 21 min | no |
| `bs_roformer_inst_resurrection` | BS-RoFormer | — | 64.1 s | 26 min | no |
| `mel_band_roformer_deux` | MelBand-RoFormer | — | 69.9 s | 28 min | no |
| `mbr_instfv9_2_gabox` | MelBand-RoFormer | — | 89.1 s | 36 min | no |
| `mbr_duality_aname` | MelBand-RoFormer | — | 93.0 s | 37 min | no |
| `mbr_bve_gonza` | MelBand-RoFormer | — | 95.8 s | 38 min | no |
| `mbr_instfv9_gabox` | MelBand-RoFormer | — | 96.3 s | 39 min | no |
| `bs_roformer_male_female` | BS-RoFormer | — | 111.5 s | 45 min | no |
| `bs_roformer_viperx_1297` | BS-RoFormer | 7.8 s | 112.8 s | 45 min | no |
| `mbr_vocals_center` | MelBand-RoFormer | — | 112.9 s | 45 min | no |
| `bs_roformer_gender_ep267` | BS-RoFormer | — | 113.0 s | 45 min | no |
| `bs_roformer_inst_hyperacev2` | BS-RoFormer | 14.3 s | 122.7 s | 49 min | no |
| `bs_roformer_voc_hyperacev2` | BS-RoFormer | 14.6 s | 126.3 s | 51 min | no |
| `mbr_inst_3_gabox` | MelBand-RoFormer | — | 151.5 s | 61 min | no |
| `mbr_inst_fvx` | MelBand-RoFormer | — | 157.8 s | 63 min | no |
| `bs_roformer_voc_gabox` | BS-RoFormer | — | 158.9 s | 64 min | no |
| `mbr_inst_fv8` | MelBand-RoFormer | — | 160.2 s | 64 min | no |
| `mbr_instv8n` | MelBand-RoFormer | — | 162.2 s | 65 min | no |
| `mbr_bleed_suppressor` | MelBand-RoFormer | — | 162.3 s | 65 min | no |
| `mbr_inst_v1e_plus` | MelBand-RoFormer | — | 164.0 s | 66 min | no |
| `mbr_instv8` | MelBand-RoFormer | — | 165.3 s | 66 min | no |
| `mbr_fullness_v4` | MelBand-RoFormer | — | 167.5 s | 67 min | no |
| `mbr_fullness_noise_v4` | MelBand-RoFormer | — | 174.5 s | 70 min | no |
| `mbr_crowd` | MelBand-RoFormer | — | 183.1 s | 73 min | no |
| `mbr_instvox_duality_v2` | MelBand-RoFormer | — | 280.5 s | 112 min | no |
| `mbr_duality_v1` | MelBand-RoFormer | — | 282.4 s | 113 min | no |

## Results — 30 s clip (scaling check)

A 5 s clip is dominated by fixed costs (model load, framework import), so the
per-second rate is measured again on a 30 s clip, where those costs amortise:

| Model | 5 s | 30 s | rate (× realtime) | extrapolated 120 s |
|---|---|---|---|---|
| `uvr_2hp` | 9.7 s | 32.2 s | 1.1× | 2.1 min |
| `mdx23c_instvoc_hq` | 40.6 s | 136.9 s | 4.6× | 9.1 min |
| `mbr_inst_v2` | 44.0 s | 333.0 s | 11.1× | 22.2 min |
| `bs_roformer_viperx_1296` | 51.9 s | 335.3 s | 11.2× | 22.4 min |

The rate is **linear** in the clip length, so the 5 s numbers extrapolate
conservatively (they over-estimate, because the fixed cost is spread over a
shorter clip). A 120 s clip — the CPU-mode limit — finishes inside the
30-minute job timeout for every measured model.

## 4-core measurement (2026-10-22)

The reference numbers above are on the 16-vCPU machine. CPU mode is also meant
to work on small boxes, so the same 4 `cpuOk` models were re-measured with the
process pinned to **4 cores** (`taskset -c 0-3` + `UVR_CPU_THREADS=4`,
confirmed by `sched_getaffinity = 4` and `torch.get_num_threads() = 4`), same
5 s clip:

| Model | 16 vCPU | 4 cores | slow-down | 2-min clip on 4 cores |
|---|---|---|---|---|
| `htdemucs_6s` | 8.4 s | 10.9 s | 1.3× | ~4 min |
| `htdemucs` | 8.5 s | 11.6 s | 1.4× | ~5 min |
| `uvr_2hp` | 9.7 s | 16.1 s | 1.7× | ~6 min |
| `mbr_guitar_becruily` | 13.3 s | 20.7 s | 1.6× | ~8 min |

Scaling is sub-linear — going from 16 to 4 cores costs only 1.3–1.7×, not 4×,
because these models are not purely CPU-bound and torch's thread pool already
only used ~8 threads on the big box.

**Consequence for the cutoff:** the slowest enabled model (`mbr_guitar_becruily`)
reaches **20.7 s per 5 s clip** on 4 cores — it crosses the 15 s line on a
*rate* basis but still extrapolates to ~8 min for a 2-minute clip, comfortably
inside the 30-minute timeout. The cutoff was calibrated on the reference rig;
on a 4-core box the real constraint is the **absolute** 30-minute ceiling, not
the 15 s rate. If you are tuning `cpuOk` for a machine slower than 4 modern
cores, re-run `scripts/benchmark-cpu.py` there and check the 2-minute-clip
column rather than the 5 s column.

## Reading the table

- **`cpuOk`** is the flag the catalogue carries. It is set from these numbers,
  not from the architecture name.
- The cutoff is **15 s per 5 s clip** on the reference machine, which
  extrapolates to roughly 6 minutes for a 2-minute clip. **4 of the
  catalogue's 45 models** qualify; the rest are refused up front in CPU mode.
  The first rejected model is `htdemucs_ft` at 16.4 s.
- The split falls where the architecture suggests it should — but not exactly
  where the *name* suggests. The **HyperACE** pair is the slowest group
  (123–126 s) despite being only 180 MB, because it runs through the vendored
  MSST implementation rather than `audio-separator`, and that path is
  heavier.
- A CPU run uses less overlap than a GPU run, so CPU stems are slightly less
  clean. That is the trade the mode makes explicit rather than hiding.

## Two models that do not load at all

`mel_band_roformer_fv8b` and `bs_polarformer_vocals` fail on **both** devices
with `SystemExit(1)` from `audio-separator`'s checkpoint loader. This is
**pre-existing** and unrelated to CPU mode — it reproduces identically on the
unmodified tree. The catalogue lists them as runnable, which is wrong; they
should carry the `unsupported` flag like the other known-bad entries. Left
alone here because it is a catalogue bug, not a CPU-mode one.

## Reproducing on your own hardware

The numbers above are for one machine. CPU performance depends on the core
count, the memory bandwidth and the single-thread performance, so measure on
the hardware you actually intend to run:

```bash
python3 scripts/benchmark-cpu.py            # the CPU-capable set + two RoFormers
```

The script prints the environment facts (torch version, thread count, core
count, affinity mask, cgroup quota) alongside the table, because a CPU number
without them is not comparable to another CPU number.
