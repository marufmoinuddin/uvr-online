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
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())

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
        await self._broadcast(job)
        return job

    def list(self) -> list[dict[str, Any]]:
        return [self._jobs[i].to_dict() for i in reversed(self._order)]

    def clear(self) -> int:
        """Drop all finished jobs (ready / error / cancelled) from the queue.
        Queued and processing jobs are kept so in-flight work is not lost.
        Returns the number of jobs removed."""
        removed = 0
        for jid in list(self._order):
            job = self._jobs[jid]
            if job.status in ("ready", "error", "cancelled"):
                del self._jobs[jid]
                self._order.remove(jid)
                removed += 1
        return removed

    def remove(self, job_id: str) -> bool:
        """Remove a single finished job (ready / error / cancelled) from the
        queue. Returns True if it was removed, False if it was not found or is
        still active."""
        job = self._jobs.get(job_id)
        if job is None or job.status not in ("ready", "error", "cancelled"):
            return False
        del self._jobs[job_id]
        if job_id in self._order:
            self._order.remove(job_id)
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
            await self._process(job)

    async def _next_queued(self) -> Optional[Job]:
        async with self._lock:
            for jid in self._order:
                job = self._jobs[jid]
                if job.status == "queued" and not job.cancelled:
                    return job
        return None

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
                job.status = "cancelled"
                job.stage = "done"
                job.progress = 0.0
                job.eta_sec = None
                await self._broadcast(job)
                return
            job.result_stems = stems
            job.download_urls = [s["url"] for s in stems]
            job.stage = "done"
            job.status = "ready"
            job.progress = 100.0
            job.eta_sec = None
            await self._broadcast(job)
        except Exception as exc:  # noqa: BLE001
            if job.cancelled:
                job.status = "cancelled"
                job.stage = "done"
                job.progress = 0.0
                job.eta_sec = None
                await self._broadcast(job)
                return
            logger.exception("Job %s failed", job.id)
            job.status = "error"
            job.stage = "done"
            job.error = str(exc)
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