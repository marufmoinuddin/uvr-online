"""
Async job queue + status broadcaster.

Jobs are processed serially on the GPU (one at a time) to keep VRAM
predictable. Status updates are pushed to WebSocket subscribers and
also readable via REST polling.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from backend import separate_file

logger = logging.getLogger("uvr.queue")

OUTPUT_ROOT = Path(
    os.environ.get("OUTPUT_ROOT", str(Path(__file__).resolve().parent / "output"))
)
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# Job metadata is persisted here so finished jobs (and their stems) stay
# reachable after a restart. Without this the queue is process-local and every
# result 404s the moment the container is recreated.
STATE_PATH = OUTPUT_ROOT / "jobs.json"

# Uploads are kept under the (mounted) output volume rather than /tmp, so
# "Re-run" still works after a restart.
UPLOAD_ROOT = OUTPUT_ROOT / "uploads"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

# Statuses that can no longer progress once the process has restarted.
_INTERRUPTED = ("queued", "processing")


@dataclass
class Job:
    id: str
    scene: str
    model_id: str
    file_name: str
    status: str = "queued"  # queued | processing | ready | error | cancelled
    stage: str = "queued"  # queued | uploading | gpu | assemble | done
    progress: float = 0.0
    eta_sec: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    result_stems: list[dict[str, Any]] = field(default_factory=list)
    download_urls: list[str] = field(default_factory=list)
    error: Optional[str] = None
    input_path: Optional[str] = None
    output_dir: Optional[str] = None
    options: dict[str, Any] = field(default_factory=dict)
    cancelled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "scene": self.scene,
            "modelId": self.model_id,
            "fileName": self.file_name,
            "progress": round(self.progress, 1),
            "stage": self.stage,
            "etaSec": self.eta_sec,
            "createdAt": int(self.created_at * 1000),
            "resultStems": self.result_stems,
            "downloadUrls": self.download_urls,
            "error": self.error,
            "cancelled": self.cancelled,
            # Persisted for restart recovery + "Re-run". Not part of the public
            # wire shape the UI depends on, but harmless to include.
            "inputPath": self.input_path,
            "outputDir": self.output_dir,
            "options": self.options,
        }


class JobQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._worker: Optional[asyncio.Task] = None
        self._wake = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._load()
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())

    # -- persistence --------------------------------------------------------

    def _save(self) -> None:
        """Atomically persist job metadata so results survive a restart.

        Written to a temp file and renamed, so a crash mid-write can never
        leave a truncated `jobs.json`.
        """
        try:
            payload = [self._jobs[i].to_dict() for i in self._order]
            tmp = STATE_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(STATE_PATH)
        except Exception as exc:  # pragma: no cover - never break a job for this
            logger.warning("Could not persist job state: %s", exc)

    def _load(self) -> None:
        """Restore persisted jobs, flagging any that were interrupted."""
        if not STATE_PATH.exists():
            return
        try:
            rows = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not read %s: %s", STATE_PATH, exc)
            return
        restored = 0
        for row in rows if isinstance(rows, list) else []:
            try:
                job = Job(
                    id=row["id"],
                    scene=row.get("scene", ""),
                    model_id=row.get("modelId", ""),
                    file_name=row.get("fileName", ""),
                    status=row.get("status", "error"),
                    stage=row.get("stage", "done"),
                    progress=float(row.get("progress") or 0.0),
                    created_at=float(row.get("createdAt") or 0) / 1000.0 or time.time(),
                    result_stems=row.get("resultStems") or [],
                    download_urls=row.get("downloadUrls") or [],
                    error=row.get("error"),
                    input_path=row.get("inputPath"),
                    output_dir=row.get("outputDir"),
                    options=row.get("options") or {},
                    cancelled=bool(row.get("cancelled")),
                )
            except Exception:  # pragma: no cover - skip malformed rows
                continue
            # A job that was mid-flight when the process died can never finish.
            if job.status in _INTERRUPTED:
                job.status = "error"
                job.stage = "done"
                job.error = "Interrupted by a worker restart — please run it again."
                job.progress = 0.0
                job.eta_sec = None
            self._jobs[job.id] = job
            self._order.append(job.id)
            restored += 1
        if restored:
            logger.info("Restored %d job(s) from %s", restored, STATE_PATH)

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass

    # -- public API ---------------------------------------------------------

    async def create(
        self,
        scene: str,
        model_id: str,
        file_name: str,
        options: dict[str, Any],
        input_path: str,
    ) -> Job:
        job_id = uuid.uuid4().hex[:12]
        job = Job(
            id=job_id,
            scene=scene,
            model_id=model_id,
            file_name=file_name,
            options=options,
            input_path=input_path,
            output_dir=str(OUTPUT_ROOT / job_id),
        )
        async with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
        self._save()
        await self._broadcast(job)
        self._wake.set()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    async def cancel(self, job_id: str) -> Optional[Job]:
        """Request cancellation. Queued jobs stop immediately; a running job
        is flagged and its result is discarded when the worker finishes."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.cancelled = True
            if job.status == "queued":
                job.status = "cancelled"
                job.stage = "done"
                job.progress = 0.0
                job.eta_sec = None
        self._save()
        await self._broadcast(job)
        return job

    def list(self) -> list[dict[str, Any]]:
        return [self._jobs[i].to_dict() for i in reversed(self._order)]

    def clear(self) -> int:
        """Drop all finished jobs (ready / error / cancelled) from the queue.
        Queued and processing jobs are kept so in-flight work is not lost.

        The stems of the dropped jobs are deleted too — otherwise "clear all"
        left every result on disk forever with no way to reach it again.
        Returns the number of jobs removed."""
        removed = 0
        for jid in list(self._order):
            job = self._jobs[jid]
            if job.status in ("ready", "error", "cancelled"):
                self._discard_output(job)
                del self._jobs[jid]
                self._order.remove(jid)
                removed += 1
        if removed:
            self._save()
        return removed

    def remove(self, job_id: str) -> bool:
        """Remove a single finished job (ready / error / cancelled) from the
        queue and delete its stems.
        Returns True if it was removed, False if it was not found or is
        still active."""
        job = self._jobs.get(job_id)
        if job is None or job.status not in ("ready", "error", "cancelled"):
            return False
        self._discard_output(job)
        del self._jobs[job_id]
        if job_id in self._order:
            self._order.remove(job_id)
        self._save()
        return True

    def queue_depth(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status == "queued")

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    # -- worker -------------------------------------------------------------

    async def _run(self) -> None:
        while True:
            job = await self._next_queued()
            if job is None:
                self._wake.clear()
                await self._wake.wait()
                continue
            try:
                await self._process(job)
            except asyncio.CancelledError:
                raise
            except BaseException:  # noqa: BLE001
                # Defence in depth: a single bad job must never kill the worker
                # loop. In particular libraries that call sys.exit() raise
                # SystemExit, which is a BaseException rather than an Exception.
                logger.exception("Unexpected failure processing job %s", job.id)
                job.status = "error"
                job.stage = "done"
                job.error = "Internal error while processing this job."

    async def _next_queued(self) -> Optional[Job]:
        async with self._lock:
            for jid in self._order:
                job = self._jobs[jid]
                if job.status == "queued" and not job.cancelled:
                    return job
        return None

    @staticmethod
    def _discard_output(job: Job) -> None:
        """Delete the stems a job wrote, for jobs whose results are gone.

        Used when a job is cancelled (separation cannot be interrupted
        mid-flight, so cancelling means "discard the result") and when a job is
        removed or cleared. Without it the audio stayed on disk — tens of MB per
        song — while nothing in the API could reach it any more.
        """
        if job.output_dir:
            shutil.rmtree(job.output_dir, ignore_errors=True)
        # Bundle archives are cached per job+format under OUTPUT_ROOT/.zips, so
        # they would otherwise outlive the stems they were built from and pile
        # up (36 MB of stale zips after a short test session).
        for stale in (OUTPUT_ROOT / ".zips").glob(f"{job.id}-*.zip"):
            stale.unlink(missing_ok=True)

    async def _process(self, job: Job) -> None:
        if job.cancelled:
            return
        job.status = "processing"
        job.stage = "gpu"
        job.eta_sec = 30.0
        await self._broadcast(job)
        try:
            stems = await asyncio.to_thread(
                separate_file,
                job.model_id,
                job.input_path,
                job.output_dir,
                job.options.get("outputFormat", "mp3"),
                job.options.get("useTTA", False),
                job.options.get("extractInstrumental", False),
                lambda p, s: self._on_progress(job, p, s),
            )
            if job.cancelled:
                self._discard_output(job)
                job.status = "cancelled"
                job.stage = "done"
                job.progress = 0.0
                job.eta_sec = None
                await self._broadcast(job)
                return
            # A run that produced no audio must not be reported as `ready` —
            # that hands the user a job with nothing to play or download and no
            # explanation. Fail loudly instead.
            if not stems:
                raise RuntimeError(
                    "The separation produced no audio. The model may be "
                    "incompatible with this backend, or the input had no "
                    "decodable audio stream."
                )
            job.result_stems = stems
            job.download_urls = [s["url"] for s in stems]
            job.stage = "done"
            job.status = "ready"
            job.progress = 100.0
            job.eta_sec = None
            self._save()
            await self._broadcast(job)
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            if job.cancelled:
                self._discard_output(job)
                job.status = "cancelled"
                job.stage = "done"
                job.progress = 0.0
                job.eta_sec = None
                await self._broadcast(job)
                return
            logger.exception("Job %s failed", job.id)
            if isinstance(exc, SystemExit):
                # audio-separator calls sys.exit(1) when a checkpoint will not
                # load (e.g. an architecture it does not implement). SystemExit
                # derives from BaseException, so a plain `except Exception`
                # misses it and it tears down the whole worker process. Report
                # it as a normal job failure instead.
                job.error = (
                    "This model could not be loaded — it may use an architecture "
                    "this backend does not support. See the worker log for the "
                    "state_dict mismatch."
                )
            else:
                job.error = str(exc) or exc.__class__.__name__
            job.status = "error"
            self._save()
            job.stage = "done"
            await self._broadcast(job)

    def _on_progress(self, job: Job, pct: float, stage: str) -> None:
        job.progress = pct
        if stage:
            job.stage = "gpu"
        loop = self._loop or asyncio.get_event_loop()
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self._broadcast(job))
        )

    async def _broadcast(self, job: Job) -> None:
        payload = json.dumps(job.to_dict())
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(payload)
                except asyncio.QueueEmpty:
                    pass


queue = JobQueue()