#!/usr/bin/env python3
"""
Repair-workflow tests: the combined DSP + neural repair path.

Stage 4 of verify-all.sh runs this alongside test-repair.py. The DSP-only
behaviour is covered there; this covers everything the coordinator added:

    plan validation · stem resolution by declared name, never position ·
    stage ordering · the one-file result contract · rejection paths

Every case that touches the GPU goes through the real job API, because the
point is to prove the shipped path works, not a unit-level stub.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

API = os.environ.get("UVR_API", "http://localhost:8000")
PROBE = Path("/tmp/probe")

_results: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> bool:
    _results.append((ok, name, detail))
    return ok


def submit(audio: Path, options: dict) -> tuple[int, dict]:
    """POST a repair job. Returns (http_status, body)."""
    boundary = "----uvrworkflow"
    buf = io.BytesIO()

    def field(name: str, value: str) -> None:
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        buf.write(f"{value}\r\n".encode())

    field("scene", "audio-repair")
    field("model_id", "x")  # ignored by the repair path
    field("options", json.dumps(options))
    buf.write(f"--{boundary}\r\n".encode())
    buf.write(
        f'Content-Disposition: form-data; name="file"; '
        f'filename="{audio.name}"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
    )
    buf.write(audio.read_bytes())
    buf.write(f"\r\n--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"{API}/api/jobs",
        data=buf.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"detail": raw.decode(errors="replace")[:200]}


def wait(job_id: str, timeout_s: int = 900) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with urllib.request.urlopen(f"{API}/api/jobs/{job_id}", timeout=30) as r:
            st = json.loads(r.read())
        if st["status"] in ("ready", "error", "cancelled"):
            return st
        time.sleep(2)
    return st


def fetch_stem(url: str) -> bytes:
    if not url.startswith("http"):
        url = API + urllib.parse.quote(url, safe="/")
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def wav_info(data: bytes) -> tuple[int, int, float]:
    p = Path(tempfile.mkdtemp()) / "s.wav"
    p.write_bytes(data)
    with wave.open(str(p), "rb") as w:
        n, ch, rate, sw = w.getnframes(), w.getnchannels(), w.getframerate(), w.getsampwidth()
        raw = w.readframes(n)
    if sw != 2:
        return rate, ch, 0.0
    import array
    a = array.array("h")
    a.frombytes(raw)
    peak = max((abs(x) for x in a), default=0) / 32768.0
    return rate, ch, peak


def _ensure_fixture(path: Path) -> bool:
    """Make sure the probe clip exists, generating it if it does not.

    The workflow test needs a decodable audio file to push through the API —
    it checks the workflow's stage order, stem resolution and the one-output
    contract, not the repair quality. Nothing in the repo generated this file,
    so on a clean machine the test could only ever report "missing /tmp/probe"
    and never actually test anything.

    A short sine mix is enough: the neural repair step runs on it, and the
    assertions are about the workflow, not about the audio.
    """
    if path.exists():
        return True
    try:
        import numpy as np

        path.parent.mkdir(parents=True, exist_ok=True)
        rate, seconds = 44100, 4
        t = np.arange(rate * seconds, dtype=np.float32) / rate
        mono = (
            0.30 * np.sin(2 * np.pi * 220.0 * t)
            + 0.20 * np.sin(2 * np.pi * 440.0 * t)
            + 0.15 * np.sin(2 * np.pi * 554.0 * t)
        ).astype(np.float32)
        pcm = (mono * 32767).astype("<i2").tobytes()
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(pcm)
    except Exception as exc:  # noqa: BLE001
        print(f"could not create the probe fixture: {exc}")
        return False
    return True


def main() -> int:
    if not _ensure_fixture(PROBE / "probe_clip.wav"):
        check(False, "probe fixtures present", f"missing {PROBE}")
        return 1
    clip = PROBE / "probe_clip.wav"

    # ---- capability contract ------------------------------------------
    try:
        with urllib.request.urlopen(f"{API}/api/repair/capabilities", timeout=30) as r:
            caps = json.loads(r.read())
    except Exception as exc:  # noqa: BLE001
        check(False, "capabilities endpoint reachable", str(exc)[:80])
        return 1

    ops = caps.get("operations", [])
    models = caps.get("models", [])
    cats = caps.get("categories", [])
    check(len(ops) > 0, "capabilities lists DSP operations", f"{len(ops)}")
    check(len(models) > 0, "capabilities lists neural repair models", f"{len(models)}")
    check(
        all(m.get("primaryStem") for m in models),
        "every neural model declares a primaryStem",
        ", ".join(m["id"] for m in models if not m.get("primaryStem")) or "all set",
    )
    check(
        all(m.get("categories") for m in models),
        "every neural model declares a category",
    )
    # Every id in a facet must also be in the model list, or the UI would
    # render a category whose cards cannot be found.
    facet_ids = {mid for c in cats for mid in c.get("models", [])}
    known = {m["id"] for m in models}
    check(
        facet_ids <= known,
        "facet members all resolve to listed models",
        f"orphans={sorted(facet_ids - known)}",
    )
    # A facet with zero models must not be emitted at all.
    check(
        all(c.get("models") for c in cats),
        "no empty facets emitted",
    )

    # ---- rejection paths: all BEFORE inference ------------------------
    rejects = [
        ("separation model is not a repair model",
         {"repairModel": "htdemucs_4stem"}, "separation model"),
        ("unknown repair model",
         {"repairModel": "definitely_not_a_model"}, "Unknown repair model"),
        ("unsupported model",
         {"repairModel": "hdemucs_mmi"}, "cannot be used"),
        ("empty plan",
         {}, "Nothing to do"),
        ("unknown operation",
         {"repairOps": ["not_an_op"]}, "Unknown repair operation"),
    ]
    for name, opts, needle in rejects:
        status, body = submit(clip, opts)
        detail = json.dumps(body)[:110]
        check(
            status == 400 and needle.lower() in detail.lower(),
            f"rejected: {name}",
            f"HTTP {status} {detail}",
        )

    # ---- every DSP op must work with NO neural model -------------------
    # Regression guard: an earlier version classified three ops as "post" and
    # then refused to run them without a model, which silently removed
    # capability the app had shipped. Placement must not become eligibility.
    ALL_OPS = [o["id"] for o in ops]
    for op in ALL_OPS:
        status, body = submit(clip, {"repairOps": [op], "outputFormat": "wav"})
        if status != 200:
            check(False, f"standalone DSP op accepted: {op}", f"HTTP {status}")
            continue
        st = wait(body["jobId"])
        stems = st.get("resultStems") or []
        ok = st["status"] == "ready" and len(stems) == 1
        detail = f"{st['status']} n={len(stems)}"
        if ok:
            _, _, peak = wav_info(fetch_stem(stems[0]["url"]))
            ok = peak > 0.001
            detail = f"peak={peak:.4f}"
        check(ok, f"standalone DSP op works: {op}", detail)

    # A mixed selection including POST ops must also work with no model.
    status, body = submit(
        clip, {"repairOps": ["declick", "denoise", "gate", "dehum"],
               "outputFormat": "wav"}
    )
    if status == 200:
        st = wait(body["jobId"])
        stems = st.get("resultStems") or []
        plan = (st.get("options") or {}).get("repairPlan") or {}
        check(st["status"] == "ready" and len(stems) == 1,
              "mixed pre/post DSP-only selection works",
              f"{st['status']} n={len(stems)}")
        check(
            plan.get("stages") == ["dsp-only"] and not plan.get("postOps"),
            "DSP-only records no staging (placement is not eligibility)",
            json.dumps({"stages": plan.get("stages"), "post": plan.get("postOps")}),
        )
    else:
        check(False, "mixed DSP-only submits", f"HTTP {status}")

    # ---- DSP only: unchanged one-file contract ------------------------
    status, body = submit(clip, {"repairOps": ["declick", "dehum"], "outputFormat": "wav"})
    if status == 200:
        st = wait(body["jobId"])
        stems = st.get("resultStems") or []
        check(st["status"] == "ready" and len(stems) == 1,
              "DSP-only returns exactly one file",
              f"{st['status']} n={len(stems)}")
        if stems:
            data = fetch_stem(stems[0]["url"])
            rate, ch, peak = wav_info(data)
            check(peak > 0.001, "DSP-only output is audible", f"peak={peak:.4f}")
            check(rate == 44100, "DSP-only keeps source sample rate", f"{rate}")
    else:
        check(False, "DSP-only submits", f"HTTP {status}")

    # ---- neural only --------------------------------------------------
    status, body = submit(clip, {"repairModel": "mdx_dereverb", "outputFormat": "wav"})
    if status == 200:
        st = wait(body["jobId"])
        stems = st.get("resultStems") or []
        check(st["status"] == "ready" and len(stems) == 1,
              "neural-only returns exactly one file",
              f"{st['status']} n={len(stems)}")
        if stems:
            data = fetch_stem(stems[0]["url"])
            rate, ch, peak = wav_info(data)
            check(peak > 0.001, "neural-only output is audible", f"peak={peak:.4f}")
        # The plan is recorded on the JOB, not in the submit response, so a
        # re-run reproduces the same model, stem and ordering.
        plan = (st.get("options") or {}).get("repairPlan") or {}
        check(
            plan.get("stages") == ["neural"] and plan.get("primaryStem") == "Dry",
            "neural-only records the declared stage and stem",
            json.dumps(plan)[:90],
        )
    else:
        check(False, "neural-only submits", f"HTTP {status}")

    # ---- combined: stage order recorded, one file ----------------------
    status, body = submit(
        clip, {"repairOps": ["dehum", "gate"], "repairModel": "mdx_dereverb",
               "outputFormat": "wav"}
    )
    if status == 200:
        st = wait(body["jobId"])
        plan = (st.get("options") or {}).get("repairPlan") or {}
        check(
            plan.get("stages") == ["dsp-pre", "neural", "dsp-post"],
            "combined job records the stage order",
            json.dumps(plan.get("stages")),
        )
        check(
            plan.get("preOps") == ["dehum"] and plan.get("postOps") == ["gate"],
            "operations are split into pre and post stages",
            json.dumps({"pre": plan.get("preOps"), "post": plan.get("postOps")}),
        )
        stems = st.get("resultStems") or []
        check(st["status"] == "ready" and len(stems) == 1,
              "combined job returns exactly one file",
              f"{st['status']} n={len(stems)}")
        if stems:
            rate, ch, peak = wav_info(fetch_stem(stems[0]["url"]))
            check(peak > 0.001, "combined output is audible", f"peak={peak:.4f}")
    else:
        check(False, "combined job submits", f"HTTP {status}")

    # ---- encode once: mp3 delivery from a lossless intermediate --------
    status, body = submit(clip, {"repairOps": ["declick"], "outputFormat": "mp3"})
    if status == 200:
        st = wait(body["jobId"])
        stems = st.get("resultStems") or []
        ok = stems and stems[0].get("format") == "mp3"
        check(ok, "mp3 delivery format applied once at the end",
              str(stems[0].get("format") if stems else st["status"]))
    else:
        check(False, "mp3 job submits", f"HTTP {status}")

    # ---- stem resolution never falls back to outputs[0] ----------------
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
    try:
        import repair_workflow as rw

        try:
            rw.resolve_repair_output(
                [{"name": "Bleed", "url": "/x/bleed.wav"},
                 {"name": "Instrumental", "url": "/x/inst.wav"}],
                "No Such Stem", "test-model",
            )
            check(False, "missing declared stem is rejected, not guessed")
        except rw.RepairPlanError as exc:
            check("did not produce" in str(exc),
                  "missing declared stem is rejected, not guessed",
                  str(exc)[:70])
        got = rw.resolve_repair_output(
            [{"name": "bleed", "url": "/x/a.wav"},
             {"name": "INSTRUMENTAL", "url": "/x/b.wav"}],
            "Instrumental", "test-model")
        check(got["name"] == "INSTRUMENTAL",
              "declared stem matched case-insensitively, not by position")
    except ImportError as exc:
        check(False, "repair_workflow importable", str(exc)[:60])

    ok = sum(1 for c, _, _ in _results if c)
    for c, name, detail in _results:
        print(f"{'PASS' if c else 'FAIL'}  {name}" + (f"    {detail}" if detail else ""))
    print(f"\n{'OK' if ok == len(_results) else 'FAILED'} — "
          f"{ok}/{len(_results)} workflow checks passed")
    return 0 if ok == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())