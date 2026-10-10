#!/usr/bin/env python3
"""
Acceptance test for neural repair models: WHICH stem is the repaired one?

A model that emits two files does not tell you which is "clean". Guessing is the
single easiest way to ship a repair that silently returns the residue instead of
the repair — the exact failure this project exists to eliminate.

Method
------
1. Build a degraded fixture: CLEAN + artifact (reverb tail, low rumble, crowd-ish
   noise), where CLEAN is a real music excerpt we keep on disk.
2. Run the model on the degraded fixture through the real job API.
3. Correlate every returned stem against CLEAN.
     - the repaired stem  -> high correlation (it is mostly the clean signal)
     - the residue stem   -> low correlation (it is mostly the artifact)

The stem that wins is the one we declare as `repair.primaryStem` in the catalog.
This script is how that value is chosen — the answer is measured, never assumed.

Usage: python3 scripts/test-repair-models.py [--api http://localhost:8000]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PROBE = Path("/tmp/probe")
API = "http://localhost:8000"

# (model_id, fixture, clean_reference, human name)
# The clean reference is PER CASE on purpose: for a bleed fixture the correct
# answer is the instrumental, not the full mix, so correlating every model
# against one global reference would score a correct repair as a bad one.
CASES = [
    ("mdx_dereverb", "fx_reverb", "probe_clip", "De-Reverb"),
    ("mbr_bleed_suppressor", "fx_bleed", "clean_inst", "Bleed Suppressor"),
    ("mbr_crowd", "fx_bleed", "clean_inst", "Crowd removal"),
]

# A stem is only trustworthy as "the repaired one" if it is clearly closer to
# the clean signal than its sibling. The absolute floor is deliberately not
# ~1.0: a real dereverb model approximates an inverse reverb, so a perfect
# correlation is not the expectation. DISCRIMINATION (the margin) is the
# meaningful signal; the floor only rejects "nothing here matches anything".
DECISIVE_MARGIN = 0.25
DECISIVE_FLOOR = 0.60


def read_wav_info(path: Path) -> tuple[np.ndarray, int, int]:
    """(mono signal, sample rate, channel count)."""
    with wave.open(str(path), "rb") as w:
        n, sw, ch, rate = w.getnframes(), w.getsampwidth(), w.getnchannels(), w.getframerate()
        raw = w.readframes(n)
    if sw != 2:
        raise SystemExit(f"{path}: only PCM16 supported (got {sw * 8}-bit)")
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, rate, ch


def correlate(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation over the overlapping region, peak-normalised first.

    Peak normalisation matters: the repair may legitimately be quieter or louder
    than the clean reference, and we are asking 'is this the same signal', not
    'is this the same level'.
    """
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    a = a - a.mean()
    b = b - b.mean()
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def run_job(model_id: str, audio: Path, api: str) -> dict:
    """Submit through the public API so we exercise the real path.

    Uses a separation scene on purpose: `audio-repair` is still DSP-only, so a
    job there never runs a model. This test needs the model's RAW stems, which is
    exactly what a plain separation returns.
    """
    import io

    boundary = "----uvraccept"
    buf = io.BytesIO()

    def field(name: str, value: str) -> None:
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        buf.write(f"{value}\r\n".encode())

    field("model_id", model_id)
    field("scene", "stem-splitter")
    field("options", json.dumps({"outputFormat": "wav"}))
    buf.write(f"--{boundary}\r\n".encode())
    buf.write(f'Content-Disposition: form-data; name="file"; filename="{audio.name}"\r\n'.encode())
    buf.write("Content-Type: audio/wav\r\n\r\n".encode())
    buf.write(audio.read_bytes())
    buf.write(f"\r\n--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"{api}/api/jobs", data=buf.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        job = json.loads(r.read())
    jid = job["jobId"]

    for _ in range(240):
        with urllib.request.urlopen(f"{api}/api/jobs/{jid}", timeout=30) as r:
            st = json.loads(r.read())
        if st["status"] in ("ready", "error", "cancelled"):
            return st
        time.sleep(2)
    raise SystemExit(f"{model_id}: job {jid} never finished")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=API)
    args = ap.parse_args()

    if not PROBE.is_dir():
        print(f"missing {PROBE}; cannot score without the clean references")
        return 2

    failures: list[str] = []
    rows: list[tuple[str, str, str, float, bool]] = []

    for model_id, fixture, clean_ref, label in CASES:
        fx = PROBE / f"{fixture}.wav"
        clean_path = PROBE / f"{clean_ref}.wav"
        if not fx.exists() or not clean_path.exists():
            print(f"! missing fixture {fx} or clean reference {clean_path}")
            failures.append(f"{model_id}: missing fixture")
            continue
        clean, rate, _ = read_wav_info(clean_path)
        src_ch = read_wav_info(fx)[2]
        fixture_sig, _, _ = read_wav_info(fx)

        print(f"\n── {label} ({model_id}) on {fx.name} vs {clean_ref}.wav")
        st = run_job(model_id, fx, args.api)
        if st["status"] != "ready":
            msg = (st.get("error") or st["status"])[:80]
            print(f"   job {st['status']}: {msg}")
            failures.append(f"{model_id}: job {st['status']}")
            continue

        stems = st.get("resultStems") or []
        if len(stems) < 2:
            print(f"   expected >=2 stems to disambiguate, got {len(stems)}")
            failures.append(f"{model_id}: not a disambiguation case")
            continue

        scored = []
        for s in stems:
            # The worker returns a raw filesystem path, which may contain spaces
            # (MDX De-Reverb writes a stem literally called "No dry"), so the
            # path has to be percent-encoded before it can be requested.
            url = s["url"] if s["url"].startswith("http") else args.api + urllib.parse.quote(s["url"], safe="/")
            with urllib.request.urlopen(url, timeout=120) as r:
                data = r.read()
            tmp = Path(tempfile.mkdtemp()) / "stem.wav"
            tmp.write_bytes(data)
            sig, srate, ch = read_wav_info(tmp)
            if srate != rate:
                print(f"   ! {s['name']}: sample rate {srate} != source {rate}")
            if ch != src_ch:
                print(f"   ! {s['name']}: {ch} channel(s), source has {src_ch}"
                      f"  -> preservesChannels=false")
            if len(sig) < int(clean.shape[0] * 0.9):
                print(f"   ! {s['name']}: truncated ({len(sig)} vs {len(clean)} frames)")
            scored.append((s["name"], correlate(sig, clean), ch))

        scored.sort(key=lambda x: -x[1])
        for name, score, ch in scored:
            print(f"     {name:<14} r={score:+.3f}  ({ch}ch)")

        # Three numbers, not one. The winner-vs-residue margin answers "which
        # output is the retained signal?" — a stem-routing question. It does
        # NOT answer "did processing improve the degraded signal?", which needs
        # the degraded input's own similarity as the baseline. Without it a
        # model that changed nothing at all would look like a perfect repair.
        degraded_r = correlate(fixture_sig, clean)
        print(f"     {'[input]':<14} r={degraded_r:+.3f}  <- baseline, not an output")

        best, best_score = scored[0][0], scored[0][1]
        margin = best_score - scored[1][1] if len(scored) > 1 else 0.0
        decisive = best_score >= DECISIVE_FLOOR and margin >= DECISIVE_MARGIN
        gain = best_score - degraded_r
        print(f"   -> primaryStem = {best!r}  (r={best_score:+.3f}, margin={margin:+.3f})"
              f"  {'DECISIVE' if decisive else 'AMBIGUOUS'}")
        # Reported, never asserted. This is the number that would show a repair
        # actually improving the signal rather than merely picking the right
        # file out of the model's outputs. A gain near zero means the fixture
        # did not exercise the defect — see the per-capability fixture table in
        # docs/AUDIO-REPAIR-GAP.md before concluding the model does nothing.
        print(f"      improvement over degraded input: {gain:+.3f}"
              f"{'   <-- NO measurable improvement on this fixture' if gain < 0.02 else ''}")
        if not decisive:
            failures.append(f"{model_id}: ambiguous (best r={best_score:+.3f}, margin={margin:+.3f})")
        rows.append((model_id, label, best, best_score, decisive))

    print("\n" + "=" * 64)
    for model_id, label, stem, score, ok in rows:
        print(f"{'PASS' if ok else 'FAIL'}  {model_id:<22} {label:<18} -> {stem}")
    if failures:
        print("\nFAILED:")
        for f in failures:
            print("  -", f)
        return 1
    print(f"\nOK — {len(rows)} repair model(s) resolved to a single unambiguous stem")
    return 0


if __name__ == "__main__":
    sys.exit(main())