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
import shutil
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
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from backend import list_models
from job_queue import OUTPUT_ROOT, Job, queue
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
    tmp = Path(tempfile.mkdtemp(prefix="uvr-upload-"))
    dest = tmp / (file.filename or f"input{ext}")
    size = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "File exceeds 1 GB limit")
            out.write(chunk)

    job = await queue.create(scene, model_id, file.filename or dest.name, opts, str(dest))
    return {"jobId": job.id, "status": job.status, "etaSec": job.eta_sec or 30}


@api.get("/jobs")
async def list_jobs() -> list[dict]:
    return queue.list()


@api.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job.to_dict()


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


@api.get("/jobs/{job_id}/stems/{stem_name}")
async def get_stem(job_id: str, stem_name: str) -> FileResponse:
    if job_id == "ensemble":
        path = _ensemble_dir / stem_name
        if not path.exists():
            raise HTTPException(404, "Stem not found")
        return FileResponse(path, filename=stem_name)
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    path = Path(job.output_dir or "") / stem_name
    if not path.exists():
        raise HTTPException(404, "Stem not found")
    return FileResponse(path, filename=stem_name)


@api.get("/jobs/{job_id}/download")
async def download_bundle(job_id: str, format: str = "zip", lossless: int = 0) -> FileResponse:
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    out_dir = Path(job.output_dir or "")
    if not out_dir.exists():
        raise HTTPException(410, "Output no longer available")

    if format == "zip":
        zip_path = out_dir / f"{job.id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(out_dir.iterdir()):
                if f.suffix in (".wav", ".flac", ".mp3"):
                    zf.write(f, f.name)
        return FileResponse(zip_path, filename=f"{job.id}.zip", media_type="application/zip")

    raise HTTPException(400, "Unsupported bundle format")


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