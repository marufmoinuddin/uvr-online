# Audio Repair — reference comparison, candidate manifest, and status

**Last updated:** 2026-10-10
**Reference:** <https://uvrvocalremover.com/workbench/audio-repair>
**Ours:** <http://localhost:3000/tools/audio-repair>

---

## 0. Correction to the previous version of this document

An earlier revision classified several reference models as *permanently
unobtainable* because they returned zero hits in audio-separator's registry.
**That was wrong.** Zero registry hits only means "not reachable through our
current fetch path" — it says nothing about whether public weights exist.

The correct classification for every one of them is:

```
Public implementation/checkpoint available.
Reference identity unverified.
Local integration and hardware compatibility not yet verified.
```

These are kept separate from genuinely proprietary checkpoints, which have no
public weights at all.

### Reopened by public source

| Family | Public source | Establishes |
|---|---|---|
| Apollo | [JusperLee/Apollo](https://github.com/JusperLee/Apollo) · [HF](https://huggingface.co/JusperLee/Apollo) | Official checkpoint + CLI exist. **License CC BY-SA 4.0, not MIT.** |
| AudioSR | [haoheliu/versatile_audio_super_resolution](https://github.com/haoheliu/versatile_audio_super_resolution) | `audiosr_basic`, `audiosr_speech`; outputs 48 kHz |
| FlashSR | [jakeoneijk/FlashSR_Inference](https://github.com/jakeoneijk/FlashSR_Inference) · [HF](https://huggingface.co/laion/FlashSR_One-step_Versatile_Audio_Super-resolution) | 3 required checkpoints |
| BandIt v2 | [kwatcharasupat/bandit-v2](https://github.com/kwatcharasupat/bandit-v2) | Weights on Zenodo |
| Anvuew SDR 22 | [anvuew/dereverb_bs_roformer](https://huggingface.co/anvuew/dereverb_bs_roformer) | `dereverb_bs_roformer_anvuew_sdr_22.5050.ckpt` |

**These sources do NOT establish** that the reference uses exactly these
checkpoints, that Apollo's public checkpoint equals "Apollo v2", that anything
fits 6 GB of VRAM, or that it is compatible with our Python environment.

> **FlashSR naming trap.** Unrelated projects share the name. Use the audio
> super-resolution implementation by Jaekwon Im and Juhan Nam. Do not
> substitute Hierspeech++ just because the name matches.

---

## 1. What shipped in this change

The immediate user-facing gap is closed: Audio Repair now offers neural models.

| | Before | Now |
|---|---|---|
| Repair choices | 7 ffmpeg ops, 0 models | 7 ops **+ 3 neural models** |
| Facets | none | Denoise, Dereverb, Live cleanup |
| Eligibility | — | explicit `repair` capability metadata |
| Result | 1 file | 1 file (unchanged) |

### 1.1 Explicit repair capabilities (not a `target` filter)

`target` is deliberately **not** used. Being `dual` or `instrumental` says
nothing about whether a model performs a repair, and widening `target` would put
every separation model on a page that promises to repair something.

```jsonc
"repair": {
  "categories": ["dereverb"],
  "primaryStem": "Dry",
  "inputScope": "full-mix",
  "preservesChannels": true
}
```

```
eligible = not unsupported
           and has a verified fetch path
           and declares `repair`
```

### 1.2 `primaryStem` is measured, never guessed

A model emitting two files does not say which is the repair.
`scripts/test-repair-models.py` builds a degraded fixture, runs the model, and
correlates each output against the known-clean signal:

| Model | Fixture | Clean ref | Winner | r | Residue r | **Input baseline** | **Gain** |
|---|---|---|---|---|---|---|---|
| `mdx_dereverb` | reverb | `probe_clip` | **Dry** | +0.826 | 0.208 | +0.812 | **+0.014** |
| `mbr_bleed_suppressor` | instrumental + 30 % vocals | `clean_inst` | **Instrumental** | +0.992 | 0.105 | +0.972 | **+0.020** |
| `mbr_crowd` | same | `clean_inst` | **Other** | +0.972 | 0.070 | +0.972 | **+0.000** |

All three preserve 2 channels and the source sample rate. Decision rule: margin
≥ 0.25 **and** floor ≥ 0.60 — discrimination, not perfection, is the signal.

#### What this table does and does not establish

The **winner-vs-residue margin** answers one question only:

> Which output is the retained signal?

It is a **stem-routing** check. It is **not** evidence of repair quality.

The **gain** column — repaired output similarity minus the degraded input's own
similarity — is the question that matters for effectiveness:

> Did processing improve the degraded signal?

Read honestly, the current numbers say **effectiveness is essentially unproven**:

- De-reverb: +0.014
- Bleed suppressor: +0.020
- Crowd: **+0.000**

The crowd result is the clearest: its fixture contains **no crowd material at
all** (instrumental + vocal bleed), so the model correctly found nothing to
remove and returned essentially its input. That validates execution and output
routing. It proves **nothing** about crowd removal.

> The first bleed fixture (brown rumble) gave an ambiguous result. That was a bad
> fixture, not a bad model: rumble is not bleed. Rebuilt from real stems.

### 1.3 One-output coordinator

`api/repair_workflow.py` sits **above** `repair.py`, which stays DSP-only and
keeps its one-element result contract.

```
1. ffmpeg pre-ops      (lossless intermediate)
2. neural repair model (optional, exactly one)
3. ffmpeg post-ops     (optional)
4. encode ONCE to the delivery format
5. publish exactly one file
```

Every op is classified `PRE` or `POST`, and an import-time assertion fails if
`repair.py` gains an operation nobody classified — otherwise it would be
silently dropped from every plan.

**Stem resolution never falls back to `outputs[0]`.** A missing declared stem
fails the job with a message naming what the model actually produced.

### 1.4 Runtime-derived UI

`GET /api/repair/capabilities` returns operations, models, facets and counts.
DSP and neural are **visually distinct**, and the processing summary reflects the
*actual* stages that will run.

---

## 2. Candidate manifest

### Counts and their basis

- Locally probe-verified and selectable on Audio Repair: **3 models**.
- DSP operations available: **7**.
- Registry candidates identified: **16 entries**, pending identity deduplication.
- Remaining unprobed registry entries: **13**, *if* the 16 include the 3 shipped
  models.
- Distinct reference model identities: **not yet reconciled**.
- Reference facet counts are **memberships**, not a unique-model total.
- Public-source availability does **not** establish reference-checkpoint
  equivalence.

**No reference-parity total is claimed** until the manifest is deduplicated by
reference identity *and* checkpoint identity. Counting rows, checkpoints and
reference cards interchangeably produces misleading totals — one reference row
can map to several candidate checkpoints, and a single open-source family
(Apollo) covers several distinct reference identities.

### Manifest (reference identity and checkpoint identity kept distinct)

| Reference identity | Facet | Paid? | Candidate checkpoint | Local id | Confidence | Probe | Hardware |
|---|---|---|---|---|---|---|---|
| Denoise Aufr33 | Denoise | free | `denoise_mel_band_roformer_aufr33_sdr_27.9959.ckpt` | — | medium | not run | not measured |
| Kimmel UNWA FT2 | Denoise | free | `mel_band_roformer_kim_ft2_unwa.ckpt` | — | medium | not run | not measured |
| Bleed Suppressor | Denoise | free | `mel_band_roformer_bleed_suppressor_v1.ckpt` | `mbr_bleed_suppressor` | high | **verified** | verified |
| Denoise DeBleed | Denoise | free | `mel_band_roformer_denoise_debleed_gabox.ckpt` | — | medium | not run | not measured |
| Instrumental Bleedless v3 | Denoise | free | `mel_band_roformer_instrumental_bleedless_v3_gabox.ckpt` | — | medium | not run | not measured |
| Big Reverb | Dereverb | free | `dereverb_big_mbr_ep_362.ckpt` | — | medium | not run | not measured |
| Super Big Reverb | Dereverb | free | `dereverb_super_big_mbr_ep_346.ckpt` | — | medium | not run | not measured |
| Anvuew SDR 19 | Dereverb | free | `dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt` | — | medium | not run | not measured |
| Anvuew SDR 22 | Dereverb | free | `dereverb_bs_roformer_anvuew_sdr_22.5050.ckpt` (HF) | — | medium | not run | not measured |
| Echo + Reverb | Dereverb | free | `dereverb_echo_mbr_fused.ckpt`, `dereverb-echo_..._sdr_13.4843_v2.ckpt` | — | medium | not run | not measured |
| Less Aggressive | Dereverb | free | `dereverb_..._less_aggressive_anvuew_sdr_18.8050.ckpt` | — | medium | not run | not measured |
| MDX23C Aufr33 | Dereverb | free | `MDX23C-De-Reverb-aufr33-jarredou.ckpt` | `mdx_dereverb` | high | **verified** | verified |
| Aspiration Gentle | Enhance | free | `aspiration_..._less_aggr_sdr_18.1201.ckpt` | — | medium | not run | not measured |
| Aspiration SDR 18 | Enhance | free | `aspiration_mel_band_roformer_sdr_18.9845.ckpt` | — | medium | not run | not measured |
| Crowd Aufr33 | Live cleanup | free | `mel_band_roformer_crowd_aufr33_viperx_sdr_8.7144.ckpt` | `mbr_crowd` | high | **verified** | verified |
| Crowd Removal | Live cleanup | **Paid** | none found | — | — | — | — |
| **Apollo LQ MP3** | Enhance | free | public (HF) | — | **unverified** | not run | not measured |
| **Apollo v2** | Enhance | free | public (HF) | — | **unverified** | not run | not measured |
| **Apollo Vocals EP 54** | Enhance | free | public (HF) | — | **unverified** | not run | not measured |
| AudioSR | Enhance | **Paid** on ref | public (HF/GitHub) | — | **unverified** | not run | not measured |
| FlashSR | Enhance | **Paid** on ref | public (HF/GitHub) | — | **unverified** | not run | not measured |
| BandIt v2 | Enhance | **Paid** on ref | Zenodo via GitHub | — | **unverified** | not run | not measured |

The three Apollo identities are listed separately on purpose: one open-source
family covers three distinct reference models, and **none of the mappings is
verified** — a public checkpoint existing does not make it "Apollo v2".

> **Name collision.** The reference lists a *Paid* MVS model called "DeNoise"
> under Enhance. That is **not** the free MelBand denoise models under Denoise.
> Identify by registry filename, never by title.

---

## 3. Next integration candidates, in order

1. **The 13 remaining registry-backed denoise/dereverb candidates** — same
   stack, already proven here. Highest value per unit of risk.
2. **Apollo** — run in a **separate sandbox** first.
   ```
   python inference.py --in_wav=... --out_wav=... --device=cuda \
     --chunk-seconds=6 --overlap-seconds=1 --chunk-pad-seconds=1 --chunk-batch-size=1
   ```
   Chunk size 1 is the documented minimum-memory start, not a guarantee it fits.
   Upstream warns chunking can introduce seam artifacts. Label it
   **"Apollo — Codec Artifact Restoration"**; do not claim bit-perfect recovery.
   Record **CC BY-SA 4.0** separately from the MIT entries.
3. **FlashSR** and 4. **AudioSR** — super-resolution, not separation. They need a
   different acceptance test: sample rate, duration, channel handling,
   window-boundary behaviour, determinism/seed, peak VRAM, long-track completion.
   FlashSR's example processes exactly 245,760 samples (5.12 s at 48 kHz), so
   full-song use needs deliberate windowing. **An output that becomes 48 kHz does
   not by itself demonstrate successful restoration.**

---

## 4. Deliberately unchanged

- **All 7 ffmpeg operations.** None of the reference's 23 repair models targets
  clicks, clipping, hum, gating or levelling. Complementary, not a subset.
- **The "no download, no GPU" property for fix-ups.** Preserved and stated in
  the UI rather than hidden behind a model grid.
- **`repair_file()` stays DSP-only** and keeps its one-element contract.
- **No `15min` quota chip, no `Login`.**

---

## 5. Evidence, by level

One green gate does **not** mean every row below has been tested.

| Evidence | What it establishes | Status |
|---|---|---|
| Catalogue negative tests (15 injected bug classes) | Metadata drift and invalid capability declarations are detected | **automated** |
| Catalogue writer regression tests | Idempotent reruns; nested metadata is formatted safely; misaligned specs rejected | **automated** |
| Workflow tests (33 checks) | Plan validation, stage ordering, output selection, one-file delivery contract, standalone DSP | **automated** |
| Full gate (`verify-all.sh`, 6 stages) | Backend compiles; repair audio is audible and full length; frontend builds | **automated** |
| Real-model fixture runs (`test-repair-models.py`) | Models execute locally and the configured output **can be identified** | **automated** — routing only |
| Browser interaction checks | Selection, gating, and the processing summary reflect the actual stages | **manual** |
| **Defect-specific listening / quality tests** | **Advertised repair capability on relevant material** | **not measured** |
| Long-track and repeated-job runs | Operational behaviour beyond 20 s probes | **not measured** |
| Reference-parity totals | Whether we match the reference catalogue | **not claimed** |

### Required fixtures per capability

| Capability | Fixture required | Available? |
|---|---|---|
| Dereverb | Actual reverberant material, ideally with a dry reference | **no** — synthetic `aecho` only |
| Bleed suppression | Controlled unwanted-source mixture with a known retained reference | **pseudo** — Demucs-derived stems, not isolated ground truth |
| Crowd cleanup | Actual applause, cheering, or crowd-containing audio | **no** |
| Codec restoration | Compressed audio plus its pre-compression reference | **no** |

The Demucs-derived fixture is useful but must be described as a **pseudo-reference
generated by another separator**, not original isolated ground truth.

For unpaired recordings, record a **listening assessment and its limitations**
rather than inventing a numerical "quality pass".

Stage 4 of `./scripts/verify-all.sh` now runs `scripts/test-repair-workflow.py`
(33 checks) alongside `test-repair.py`. Stage 2 additionally runs
`test-add-verified-models.py` for the catalogue writer.

| Test | Result |
|---|---|
| Each of the 7 operations standalone, no model | one file, audible |
| Mixed pre/post DSP-only selection | works; records `dsp-only`, no staging |
| Empty plan | rejected |
| Separation model / unknown model / unsupported model | rejected before inference |
| Neural-only job | one cleaned file, declared stem |
| Combined job | recorded stage order `dsp-pre → neural → dsp-post` |
| Missing expected output | fails, no silent fallback |
| Encode-once delivery | mp3 applied once, at the end |

Catalogue parity is 13 checks with **4 negative cases** for repair metadata:
`primaryStem` drift, whole-block removal, category drift, capability with no
`primaryStem`.

### Corrected during review

An earlier revision rejected a finishing operation when no neural model was
selected. That was a **regression**: it silently removed capability the app had
always shipped, on the strength of a staging label. Placement is not
eligibility — `PRE`/`POST` only decide *where* an op runs once a model is
involved. All 7 operations now work standalone, and there are 7 explicit
regression tests for that.

**Known gap:** see §5. Fixture quality, long-track behaviour and defect-specific
listening tests are **not measured**.