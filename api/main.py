"""
UVR Local — FastAPI GPU worker.

Endpoints:
  GET  /health                  GPU + queue status
  GET  /models                  model catalog (seeded + installed)
  POST /jobs                    create a separation job (multipart upload)
  GET  /jobs                    list jobs
  GET  /jobs/{id}               job status + result stems
  POST /jobs/{id}/reuse         ChainLess: same file, new model
  GET  /jobs/{id}/download      ZIP bundle (lossless / mp3 variants)
  GET  /jobs/{id}/stems/{name}  serve a result stem
  POST /ensemble                fuse multiple job stems
  WS   /ws/jobs                 live job updates
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import torch
from fastapi import (
    APIRouter,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)

from backend import list_models
from job_queue import OUTPUT_ROOT, UPLOAD_ROOT, Job, queue
from model_manager import manager as model_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("uvr.main")

app = FastAPI(title="UVR Local API", version="0.1.0")

# All REST endpoints live under /api (the web client calls these directly).
api = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = 1024 * 1024 * 1024  # 1 GB
ALLOWED_EXT = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma", ".aiff"}


@app.on_event("startup")
async def startup() -> None:
    queue.start()
    logger.info("Worker started. GPU available: %s", torch.cuda.is_available())


@app.on_event("shutdown")
async def shutdown() -> None:
    await queue.stop()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@api.get("/health")
async def health() -> dict:
    gpu = torch.cuda.is_available()
    vram_free = None
    gpu_name = None
    if gpu:
        gpu_name = torch.cuda.get_device_name(0)
        props = torch.cuda.get_device_properties(0)
        vram_free = round((props.total_memory - torch.cuda.memory_reserved(0)) / 1e6, 1)
    return {
        "gpu": gpu,
        "gpuName": gpu_name,
        "vramFreeMb": vram_free,
        "queueDepth": queue.queue_depth(),
        "device": f"cuda:{torch.cuda.current_device()}" if gpu else "cpu",
    }


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@api.get("/models")
async def models() -> list[dict]:
    """Catalog merged with live install status / download progress."""
    return list_models()


# --- Model management ------------------------------------------------------
# NOTE: the literal /models/storage route must be declared before the
# /models/{model_id} route, otherwise "storage" is captured as an id.

@api.get("/models/storage")
async def model_storage() -> dict:
    """Where models live on disk and how much space they use."""
    entries = list_models()
    installed = [m for m in entries if m.get("installed")]
    return {
        "storePath": str(model_manager.store),
        "installedCount": len(installed),
        "catalogCount": len(entries),
        "totalBytes": sum(int(m.get("sizeBytes") or 0) for m in installed),
    }


@api.get("/models/{model_id}")
async def model_status(model_id: str) -> dict:
    if model_manager.get(model_id) is None:
        raise HTTPException(404, f"Unknown model '{model_id}'")
    return model_manager.status(model_id)


@api.post("/models/{model_id}/download")
async def model_download(model_id: str) -> dict:
    """Start (or observe) an on-demand download. Idempotent: concurrent
    requests for the same model share one transfer."""
    try:
        return model_manager.download_async(model_id)
    except KeyError:
        raise HTTPException(404, f"Unknown model '{model_id}'")
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))


@api.post("/models/{model_id}/cancel")
async def model_cancel(model_id: str) -> dict:
    return {"id": model_id, "cancelled": model_manager.cancel(model_id)}


@api.delete("/models/{model_id}")
async def model_delete(model_id: str) -> dict:
    """Delete a model's files. Does not trigger a re-download."""
    try:
        return model_manager.delete(model_id)
    except KeyError:
        raise HTTPException(404, f"Unknown model '{model_id}'")


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

@api.post("/jobs")
async def create_job(
    file: UploadFile = File(...),
    scene: str = Form("vocal-remover"),
    model_id: str = Form(...),
    options: str = Form("{}"),
) -> dict:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported format '{ext}'. Allowed: {sorted(ALLOWED_EXT)}")

    opts = json.loads(options or "{}")
    # Keep the upload on the mounted output volume rather than /tmp: /tmp is
    # wiped when the container restarts, which would break "Re-run" for every
    # existing job. Also strip any client-supplied directory component.
    safe_name = Path(file.filename or f"input{ext}").name
    tmp = Path(tempfile.mkdtemp(prefix="upload-", dir=UPLOAD_ROOT))
    dest = tmp / safe_name
    size = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "File exceeds 1 GB limit")
            out.write(chunk)

    job = await queue.create(scene, model_id, safe_name, opts, str(dest))
    return {"jobId": job.id, "status": job.status, "etaSec": job.eta_sec or 30}


@api.get("/jobs")
async def list_jobs() -> list[dict]:
    return queue.list()


@api.delete("/jobs")
async def clear_jobs() -> dict:
    """Clear finished jobs (ready / error / cancelled) from the console.
    Queued and processing jobs are kept so in-flight work is not lost."""
    removed = queue.clear()
    return {"cleared": removed}


@api.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job.to_dict()


@api.delete("/jobs/{job_id}")
async def delete_job(job_id: str) -> dict:
    """Remove a single finished job from the console."""
    if not queue.remove(job_id):
        raise HTTPException(404, "Job not found or still active")
    return {"id": job_id, "deleted": True}


@api.post("/jobs/{job_id}/reuse")
async def reuse_job(job_id: str, payload: dict) -> dict:
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if not job.input_path or not Path(job.input_path).exists():
        raise HTTPException(410, "Original upload no longer available")

    model_id = payload.get("modelId") or job.model_id
    new_job = await queue.create(
        job.scene,
        model_id,
        job.file_name,
        job.options,
        job.input_path,
    )
    return {"jobId": new_job.id, "status": new_job.status, "etaSec": new_job.eta_sec or 30}


@api.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict:
    """Cancel a queued or running job. Queued jobs stop immediately; a running
    job is flagged and its result is discarded when the worker finishes."""
    job = await queue.cancel(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return {"id": job_id, "cancelled": True, "status": job.status}


def _safe_child_name(name: str) -> str:
    """Reject anything that could escape its directory.

    `stem_name` arrives straight from the URL, so without this a request like
    `../jobs.json` could read files outside the job's output directory.
    """
    if not name or name != Path(name).name or name in (".", ".."):
        raise HTTPException(400, "Invalid file name")
    return name


def _serve_audio(path: Path, name: str, request: Request) -> Response:
    """Serve an audio file with HTTP Range support.

    Starlette 0.38's FileResponse ignores `Range` entirely, so it always
    returns the whole file with 200. Audio players need 206 to seek, and some
    refuse to scrub at all without it — so range handling is implemented here.
    """
    size = path.stat().st_size
    media = mimetypes.guess_type(name)[0] or "application/octet-stream"
    base = {
        "accept-ranges": "bytes",
        "content-type": media,
        "cache-control": "private, max-age=3600",
    }

    raw = (request.headers.get("range") or "").strip()
    if not raw:
        return FileResponse(path, media_type=media, headers=base)

    match = re.fullmatch(r"bytes=(\d*)-(\d*)", raw)
    if not match:
        return FileResponse(path, media_type=media, headers=base)

    first, last = match.groups()
    if not first and not last:
        return Response(status_code=416, headers={**base, "content-range": f"bytes */{size}"})

    if first:
        start = int(first)
        end = int(last) if last else size - 1
    else:
        # Suffix range: last N bytes.
        start = max(size - int(last), 0)
        end = size - 1
    end = min(end, size - 1)

    if start >= size or start > end:
        return Response(status_code=416, headers={**base, "content-range": f"bytes */{size}"})

    def _iter():
        remaining = end - start + 1
        with path.open("rb") as fh:
            fh.seek(start)
            while remaining > 0:
                chunk = fh.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        **base,
        "content-range": f"bytes {start}-{end}/{size}",
        "content-length": str(end - start + 1),
    }
    return StreamingResponse(_iter(), status_code=206, headers=headers)


def _resolve_job_dir(job_id: str) -> Path:
    """Directory holding a job's stems.

    Normally the queue is the source of truth, but the queue is process-local
    while the stems are on disk. Falling back to `OUTPUT_ROOT/<job_id>` keeps
    results reachable after a restart instead of 404ing on files that exist.
    """
    job = queue.get(job_id)
    if job is not None and job.output_dir:
        return Path(job.output_dir)
    # Only accept plain tokens, so `job_id` cannot traverse the filesystem.
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", job_id):
        raise HTTPException(404, "Job not found")
    candidate = OUTPUT_ROOT / job_id
    if candidate.is_dir():
        return candidate
    raise HTTPException(404, "Job not found")


@api.get("/jobs/{job_id}/stems/{stem_name}")
async def get_stem(
    job_id: str, stem_name: str, request: Request
) -> Response:
    name = _safe_child_name(stem_name)
    if job_id == "ensemble":
        path = _ensemble_dir / name
        if not path.is_file():
            raise HTTPException(404, "Stem not found")
        return _serve_audio(path, name, request)
    path = _resolve_job_dir(job_id) / name
    if not path.is_file():
        raise HTTPException(404, "Stem not found")
    return _serve_audio(path, name, request)


@api.get("/jobs/{job_id}/download")
async def download_bundle(job_id: str, format: str = "zip", lossless: int = 0) -> FileResponse:
    """Bundle a job's stems into a zip.

    `format` selects what goes in the archive:
      - `zip`  : stems exactly as produced by the separation run
      - `wav` / `flac` / `mp3` : transcode every stem to that format first

    `lossless=1` is kept as an alias for `format=wav` so older client links
    keep working. Previously this parameter was accepted but ignored, which
    meant the "Lossless WAV" option silently returned whatever the job
    happened to produce.
    """
    target = "wav" if lossless else format.lower()
    if target not in ("zip", "mp3", "wav", "flac"):
        raise HTTPException(400, f"Unsupported bundle format '{format}'")

    out_dir = _resolve_job_dir(job_id)
    stems = [f for f in sorted(out_dir.iterdir()) if f.suffix in (".wav", ".flac", ".mp3")]
    if not stems:
        raise HTTPException(410, "No stems available for this job")

    # Build the archive OUTSIDE the output directory so it never pollutes the
    # stem list (and never gets re-zipped into a later bundle).
    zip_dir = OUTPUT_ROOT / ".zips"
    zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / f"{job_id}-{target}.zip"

    def _add(zf: zipfile.ZipFile, src: Path) -> None:
        if target == "zip" or src.suffix.lstrip(".").lower() == target:
            zf.write(src, src.name)
            return
        converted = zip_dir / src.with_suffix(f".{target}").name
        args = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src)]
        if target == "mp3":
            args += ["-b:a", "320k"]
        args.append(str(converted))
        try:
            subprocess.run(args, check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            detail = getattr(exc, "stderr", b"") or b""
            logger.warning("ffmpeg conversion failed for %s: %s", src.name, detail[-300:])
            raise HTTPException(500, f"Could not convert {src.name} to {target}")
        try:
            zf.write(converted, converted.name)
        finally:
            converted.unlink(missing_ok=True)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in stems:
            _add(zf, f)

    return FileResponse(
        zip_path,
        filename=f"{job_id}-{target}.zip",
        media_type="application/zip",
    )


# ---------------------------------------------------------------------------
# Ensemble
# ---------------------------------------------------------------------------

@api.post("/ensemble")
async def create_ensemble(payload: dict) -> dict:
    job_ids = payload.get("jobIds", [])
    mode = payload.get("mode", "avg_fft")
    weights = payload.get("weights")

    if len(job_ids) < 2:
        raise HTTPException(400, "Ensemble requires at least 2 jobs")

    jobs: list[Job] = []
    for jid in job_ids:
        job = queue.get(jid)
        if job is None or job.status != "ready":
            raise HTTPException(400, f"Job {jid} is not ready")
        jobs.append(job)

    # Fuse stems in the frequency/time domain (phase-aligned).
    fused = await asyncio.to_thread(_fuse_stems, jobs, mode, weights)
    return {"jobId": "ensemble", "status": "ready", "stems": fused}


def _fuse_stems(jobs: list[Job], mode: str, weights: list[float] | None) -> list[dict]:
    import numpy as np
    import soundfile as sf

    if weights is None:
        weights = [1.0 / len(jobs)] * len(jobs)
    weights = np.asarray(weights, dtype=np.float64)
    weights = weights / weights.sum()

    # Load the first stem of each job (vocals by convention) and fuse.
    fused_paths: list[dict] = []
    for stem_idx in range(len(jobs[0].result_stems)):
        arrays = []
        srs = []
        for job in jobs:
            stem = job.result_stems[stem_idx]
            path = Path(job.output_dir or "") / Path(stem["url"]).name
            data, sr = sf.read(path, dtype="float32", always_2d=True)
            arrays.append(data)
            srs.append(sr)
        sr = srs[0]
        length = min(a.shape[0] for a in arrays)
        arrays = [a[:length] for a in arrays]

        if mode.endswith("_fft"):
            fused = _fuse_fft(arrays, weights, mode)
        else:
            fused = _fuse_wave(arrays, weights, mode)

        out_dir = OUTPUT_ROOT / "ensemble"
        out_dir.mkdir(parents=True, exist_ok=True)
        name = f"ensemble_{mode}_{stem_idx}.wav"
        sf.write(out_dir / name, fused, sr)
        fused_paths.append(
            {
                "name": f"ensemble-{stem_idx}",
                "url": f"/api/jobs/ensemble/stems/{name}",
                "sizeBytes": (out_dir / name).stat().st_size,
                "format": "wav",
            }
        )
    return fused_paths


def _fuse_fft(arrays: list[np.ndarray], weights: np.ndarray, mode: str) -> np.ndarray:
    import numpy as np

    n = arrays[0].shape[0]
    nfft = 4096
    hop = nfft // 4
    win = np.hanning(nfft).astype(np.float32)
    out = np.zeros_like(arrays[0], dtype=np.float32)
    norm = np.zeros(n, dtype=np.float32)

    for start in range(0, n - nfft, hop):
        segs = []
        for a in arrays:
            seg = a[start : start + nfft]
            segs.append(np.fft.rfft(seg * win[:, None], axis=0))
        if mode == "avg_fft":
            fused = sum(w * s for w, s in zip(weights, segs))
        elif mode == "median_fft":
            fused = np.median(np.stack(segs), axis=0)
        elif mode == "max_fft":
            fused = np.max(np.stack(segs), axis=0)
        elif mode == "min_fft":
            fused = np.min(np.stack(segs), axis=0)
        else:
            fused = sum(w * s for w, s in zip(weights, segs))
        out[start : start + nfft] += np.fft.irfft(fused, n=nfft, axis=0) * win[:, None]
        norm[start : start + nfft] += win * win
    norm[norm < 1e-8] = 1.0
    return (out / norm[:, None]).astype(np.float32)


def _fuse_wave(arrays: list[np.ndarray], weights: np.ndarray, mode: str) -> np.ndarray:
    import numpy as np

    stack = np.stack(arrays)
    if mode == "avg_wave":
        fused = np.tensordot(weights, stack, axes=1)
    elif mode == "median_wave":
        fused = np.median(stack, axis=0)
    else:
        fused = np.tensordot(weights, stack, axes=1)
    return fused.astype(np.float32)


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

app.include_router(api)


@app.websocket("/ws/jobs")
async def ws_jobs(ws: WebSocket) -> None:
    await ws.accept()
    q = queue.subscribe()
    try:
        # Send current snapshot on connect
        for job in queue.list():
            await ws.send_text(json.dumps(job))
        while True:
            payload = await q.get()
            await ws.send_text(payload)
    except WebSocketDisconnect:
        pass
    finally:
        queue.unsubscribe(q)


# Ensemble stems are served via the get_stem route (job_id == "ensemble").
_ensemble_dir = OUTPUT_ROOT / "ensemble"
_ensemble_dir.mkdir(parents=True, exist_ok=True)