"""
Centralized model manager — on-demand download, verification, caching,
loading and deletion for every model the app can run.

Design
------
    Registry (models.json)
          ↓
    ModelManager
      ├── is_installed(id)
      ├── ensure(id)        — download if missing, then return local paths
      ├── download(id)      — start/observe a background download
      ├── cancel(id)
      ├── delete(id)
      ├── status(id)        — progress, bytes, speed, error
      └── list()            — catalog merged with install state
          ↓
    Persistent store:  ~/.local/share/uvr-local/models/<model_id>/

Guarantees
----------
* Nothing is downloaded at import/startup — only on `ensure()`.
* Each model lives in its own directory and can be deleted independently.
* Downloads go to a temp dir and are atomically promoted only after the
  bytes are verified, so a partial file is never treated as installed.
* Concurrent requests for the same model share one download (single-flight).
* Already-installed models are reused; nothing is re-downloaded.
* After `delete()`, the model is NOT auto-restored until a feature needs it.

Uses only the Python standard library — no extra dependency stack.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("uvr.models")

# --------------------------------------------------------------------------
# Storage location (XDG app-data, overridable via MODEL_STORE)
# --------------------------------------------------------------------------

def _default_store() -> Path:
    env = os.environ.get("MODEL_STORE")
    if env:
        return Path(env).expanduser()
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base / "uvr-local" / "models"


MODEL_STORE: Path = _default_store()
TMP_DIR: Path = MODEL_STORE / ".tmp"
CATALOG_PATH = Path(os.environ.get("MODEL_CATALOG", "./models.json"))

CHUNK = 1 << 20  # 1 MiB
MAX_RETRIES = 3


# --------------------------------------------------------------------------
# Registry types
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FileSpec:
    """One file to fetch from a Hugging Face repo."""
    remote: str            # path inside the repo
    dest: str              # filename inside the model dir
    size: Optional[int] = None
    sha256: Optional[str] = None


@dataclass(frozen=True)
class DownloadSpec:
    repo: str
    revision: str = "main"
    files: tuple[FileSpec, ...] = ()

    def url(self, remote: str) -> str:
        return f"https://huggingface.co/{self.repo}/resolve/{self.revision}/{remote}"


@dataclass
class ModelRecord:
    id: str
    name: str
    arch: str
    target: str
    tags: list[str]
    license: str
    source: str
    model_type: str
    speculative_mb: float = 0.0
    installed_hint: bool = False
    download: Optional[DownloadSpec] = None
    stems: list[str] = field(default_factory=list)
    sdr: Optional[float] = None
    trait: Optional[str] = None
    usage: Optional[str] = None
    recommended: bool = False
    ensemble: bool = False

    @property
    def downloadable(self) -> bool:
        return self.download is not None and len(self.download.files) > 0


# --------------------------------------------------------------------------
# Per-model live state
# --------------------------------------------------------------------------

class ModelState:
    def __init__(self, model_id: str) -> None:
        self.id = model_id
        self.status = "idle"       # idle|downloading|verifying|installed|error
        self.error: Optional[str] = None
        self.received = 0
        self.total = 0
        self.speed_bps = 0.0
        self.started_at: Optional[float] = None
        self.retries = 0
        self.current_file: Optional[str] = None
        self._last_bytes = 0
        self._last_t = 0.0

    def tick(self, received: int) -> None:
        now = time.time()
        dt = now - self._last_t
        if dt >= 0.5:
            inst = (received - self._last_bytes) / dt
            # exponential moving average to keep the readout stable
            self.speed_bps = inst if self.speed_bps == 0 else 0.7 * self.speed_bps + 0.3 * inst
            self._last_bytes = received
            self._last_t = now
        self.received = received

    def to_dict(self) -> dict[str, Any]:
        pct = (self.received / self.total * 100) if self.total else 0.0
        return {
            "status": self.status,
            "error": self.error,
            "receivedBytes": self.received,
            "totalBytes": self.total,
            "percent": round(min(pct, 100.0), 1),
            "speedBps": round(self.speed_bps),
            "etaSec": (
                round((self.total - self.received) / self.speed_bps)
                if self.speed_bps > 0 and self.total > self.received
                else None
            ),
            "retries": self.retries,
            "currentFile": self.current_file,
        }


# --------------------------------------------------------------------------
# Manager
# --------------------------------------------------------------------------

class ModelManager:
    def __init__(self, catalog_path: Path = CATALOG_PATH, store: Path = MODEL_STORE) -> None:
        self.catalog_path = Path(catalog_path)
        self.store = Path(store)
        self.tmp = self.store / ".tmp"
        self.store.mkdir(parents=True, exist_ok=True)
        self.tmp.mkdir(parents=True, exist_ok=True)

        self._registry: dict[str, ModelRecord] = {}
        self._states: dict[str, ModelState] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        # Reentrant: some helpers acquire the guard while it is already held.
        self._guard = threading.RLock()
        self._subscribers: list[Callable[[str], None]] = []

        self.reload()

    # -- registry ---------------------------------------------------------

    def reload(self) -> None:
        try:
            raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover
            logger.error("Could not read catalog %s: %s", self.catalog_path, exc)
            raw = {}

        registry: dict[str, ModelRecord] = {}
        for mid, e in raw.items():
            spec = None
            d = e.get("download")
            if d and d.get("files"):
                spec = DownloadSpec(
                    repo=d["repo"],
                    revision=d.get("revision", "main"),
                    files=tuple(
                        FileSpec(
                            remote=f["remote"],
                            dest=f.get("dest", Path(f["remote"]).name),
                            size=f.get("size"),
                            sha256=f.get("sha256"),
                        )
                        for f in d["files"]
                    ),
                )
            registry[mid] = ModelRecord(
                id=mid,
                name=e.get("name", mid),
                arch=e.get("arch", "?"),
                target=e.get("target", "dual"),
                tags=e.get("tags", []),
                license=e.get("license", "UNSPECIFIED"),
                source=e.get("source", ""),
                model_type=e.get("model_type", "vocal_models"),
                speculative_mb=float(e.get("sizeMB", 0) or 0),
                installed_hint=bool(e.get("installed")),
                download=spec,
                stems=e.get("stems", []),
                sdr=e.get("sdr"),
                trait=e.get("trait"),
                usage=e.get("usage"),
                recommended=bool(e.get("recommended")),
                ensemble=bool(e.get("ensemble")),
            )
        self._registry = registry
        logger.info("Model registry loaded: %d entries", len(registry))

    def get(self, model_id: str) -> Optional[ModelRecord]:
        return self._registry.get(model_id)

    def all(self) -> list[ModelRecord]:
        return list(self._registry.values())

    # -- paths ------------------------------------------------------------

    def model_dir(self, model_id: str) -> Path:
        return self.store / model_id

    def manifest_path(self, model_id: str) -> Path:
        return self.model_dir(model_id) / "manifest.json"

    def paths(self, model_id: str) -> Optional[dict[str, str]]:
        """Resolved local paths for an installed model (None if missing)."""
        rec = self._registry.get(model_id)
        if rec is None or not rec.downloadable:
            return None
        d = self.model_dir(model_id)
        if not (d / "manifest.json").exists():
            return None
        ckpt = next(
            (f.dest for f in rec.download.files if f.dest.endswith((".ckpt", ".pth", ".safetensors", ".th"))),
            None,
        )
        cfg = next((f.dest for f in rec.download.files if f.dest.endswith((".yaml", ".yml"))), None)
        if not ckpt or not cfg:
            return None
        ckpt_p, cfg_p = d / ckpt, d / cfg
        if not ckpt_p.exists() or not cfg_p.exists():
            return None
        return {"model_path": str(ckpt_p), "config_path": str(cfg_p), "dir": str(d)}

    # -- status -----------------------------------------------------------

    def _state(self, model_id: str) -> ModelState:
        with self._guard:
            if model_id not in self._states:
                self._states[model_id] = ModelState(model_id)
            return self._states[model_id]

    def is_installed(self, model_id: str) -> bool:
        return self.paths(model_id) is not None

    def installed_size(self, model_id: str) -> int:
        d = self.model_dir(model_id)
        if not d.exists():
            return 0
        return sum(f.stat().st_size for f in d.rglob("*") if f.is_file())

    def status(self, model_id: str) -> dict[str, Any]:
        st = self._state(model_id)
        installed = self.is_installed(model_id)
        if installed and st.status in ("idle", "error"):
            st.status = "installed"
            st.error = None
        return {
            "id": model_id,
            "installed": installed,
            "sizeBytes": self.installed_size(model_id) if installed else 0,
            "path": str(self.model_dir(model_id)),
            "download": st.to_dict(),
        }

    def list(self) -> list[dict[str, Any]]:
        out = []
        for rec in self._registry.values():
            st = self.status(rec.id)
            out.append(
                {
                    "id": rec.id,
                    "name": rec.name,
                    "arch": rec.arch,
                    "target": rec.target,
                    "tags": rec.tags,
                    "license": rec.license,
                    "source": rec.source,
                    "modelType": rec.model_type,
                    "sizeMB": round(st["sizeBytes"] / 1e6, 1) if st["sizeBytes"] else rec.speculative_mb,
                    "downloadable": rec.downloadable,
                    "repo": rec.download.repo if rec.download else None,
                    "revision": rec.download.revision if rec.download else None,
                    "stems": rec.stems,
                    "sdr": rec.sdr,
                    "trait": rec.trait,
                    "usage": rec.usage,
                    "recommended": rec.recommended,
                    "ensemble": rec.ensemble,
                    **st,
                }
            )
        return out

    # -- subscriptions ----------------------------------------------------

    def subscribe(self, fn: Callable[[str], None]) -> None:
        self._subscribers.append(fn)

    def _notify(self, model_id: str) -> None:
        for fn in list(self._subscribers):
            try:
                fn(model_id)
            except Exception:  # pragma: no cover
                pass

    # -- download ---------------------------------------------------------

    def ensure(
        self,
        model_id: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
        timeout: float = 3600.0,
    ) -> dict[str, str]:
        """
        Return local paths for `model_id`, downloading first if necessary.
        Concurrent callers for the same model share a single download.
        """
        rec = self._registry.get(model_id)
        if rec is None:
            raise KeyError(f"Unknown model '{model_id}'")
        if not rec.downloadable:
            raise RuntimeError(
                f"Model '{model_id}' has no automated download source. "
                "It must be installed manually (see the model's upstream repo)."
            )

        existing = self.paths(model_id)
        if existing:
            return existing

        lock = self._locks.setdefault(model_id, threading.Lock())
        with lock:
            # Another thread may have finished while we waited.
            existing = self.paths(model_id)
            if existing:
                return existing
            self._download_blocking(model_id, rec, on_progress, timeout)

        paths = self.paths(model_id)
        if paths is None:
            st = self._state(model_id)
            raise RuntimeError(st.error or f"Download of '{model_id}' failed")
        return paths

    def download_async(self, model_id: str) -> dict[str, Any]:
        """Kick off a download in the background (idempotent)."""
        rec = self._registry.get(model_id)
        if rec is None:
            raise KeyError(f"Unknown model '{model_id}'")
        if not rec.downloadable:
            raise RuntimeError(f"Model '{model_id}' has no automated download source.")
        if self.is_installed(model_id):
            return self.status(model_id)

        st = self._state(model_id)
        with self._guard:
            th = self._threads.get(model_id)
            if th and th.is_alive():
                already = True  # already downloading — never start a second one
            else:
                already = False
                self._cancel[model_id] = threading.Event()
                t = threading.Thread(
                    target=self._download_worker,
                    args=(model_id, rec),
                    daemon=True,
                    name=f"dl-{model_id}",
                )
                self._threads[model_id] = t
                t.start()
        # Build the response OUTSIDE the lock (status() takes the same guard).
        return self.status(model_id) if already else st.to_dict()

    def cancel(self, model_id: str) -> bool:
        ev = self._cancel.get(model_id)
        if ev:
            ev.set()
            st = self._state(model_id)
            st.status = "idle"
            st.error = None
            st.speed_bps = 0.0
            self._notify(model_id)
            return True
        return False

    def delete(self, model_id: str) -> dict[str, Any]:
        """Remove a model's files. Never triggers a re-download."""
        if model_id not in self._registry:
            raise KeyError(f"Unknown model '{model_id}'")
        self.cancel(model_id)
        d = self.model_dir(model_id)
        freed = self.installed_size(model_id)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        t = self.tmp / model_id
        if t.exists():
            shutil.rmtree(t, ignore_errors=True)
        st = self._state(model_id)
        st.status = "idle"
        st.error = None
        st.received = 0
        st.total = 0
        st.speed_bps = 0.0
        logger.info("Deleted model %s (freed %.1f MB)", model_id, freed / 1e6)
        self._notify(model_id)
        return {"id": model_id, "freedBytes": freed, "installed": False}

    def _download_worker(self, model_id: str, rec: ModelRecord) -> None:
        try:
            self._download_blocking(model_id, rec, None, 3600.0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Download failed for %s: %s", model_id, exc)

    def _download_blocking(
        self,
        model_id: str,
        rec: ModelRecord,
        on_progress: Optional[Callable[[float, str], None]],
        timeout: float,
    ) -> None:
        st = self._state(model_id)
        st.status = "downloading"
        st.error = None
        st.received = 0
        st.total = sum(f.size or 0 for f in rec.download.files) or 0
        st.started_at = time.time()
        st.speed_bps = 0.0
        st._last_bytes = 0
        st._last_t = time.time()
        self._notify(model_id)

        cancel_ev = self._cancel.setdefault(model_id, threading.Event())
        staging = self.tmp / f"{model_id}-{uuid.uuid4().hex[:8]}"

        try:
            staging.mkdir(parents=True, exist_ok=True)

            # ---- fetch every file into staging -------------------------
            for spec in rec.download.files:
                self._fetch(rec.download, spec, staging, st, cancel_ev, on_progress)

            # ---- verify ------------------------------------------------
            st.status = "verifying"
            self._notify(model_id)
            for spec in rec.download.files:
                self._verify(staging / spec.dest, spec)

            # ---- manifest + atomic promote -----------------------------
            manifest = {
                "id": model_id,
                "name": rec.name,
                "repo": rec.download.repo,
                "revision": rec.download.revision,
                "license": rec.license,
                "model_type": rec.model_type,
                "installed_at": time.time(),
                "files": [
                    {
                        "dest": f.dest,
                        "remote": f.remote,
                        "size": (staging / f.dest).stat().st_size,
                        "sha256": f.sha256,
                    }
                    for f in rec.download.files
                ],
            }
            (staging / "manifest.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )

            final = self.model_dir(model_id)
            if final.exists():
                shutil.rmtree(final, ignore_errors=True)
            os.replace(staging, final)  # atomic on the same filesystem

            st.status = "installed"
            st.received = st.total
            st.speed_bps = 0.0
            logger.info("Model %s installed at %s", model_id, final)
            self._notify(model_id)

        except _Cancelled:
            shutil.rmtree(staging, ignore_errors=True)
            st.status = "idle"
            st.error = "Cancelled"
            st.speed_bps = 0.0
            logger.info("Download cancelled: %s", model_id)
            self._notify(model_id)
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(staging, ignore_errors=True)
            st.status = "error"
            st.error = str(exc)
            st.speed_bps = 0.0
            logger.warning("Download error for %s: %s", model_id, exc)
            self._notify(model_id)

    # -- transfer ---------------------------------------------------------

    def _fetch(
        self,
        spec: DownloadSpec,
        file: FileSpec,
        staging: Path,
        st: ModelState,
        cancel: threading.Event,
        on_progress: Optional[Callable[[float, str], None]],
    ) -> None:
        dest = staging / file.dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(dest.suffix + ".part")
        url = spec.url(file.remote)
        st.current_file = file.dest

        last_err: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            if cancel.is_set():
                raise _Cancelled()
            try:
                self._stream(url, part, st, cancel, on_progress, file.size)
                # sanity: non-empty and (if known) exact size
                got = part.stat().st_size
                if got == 0:
                    raise RuntimeError("received 0 bytes")
                if file.size and got != file.size:
                    raise RuntimeError(f"size mismatch: got {got}, expected {file.size}")
                os.replace(part, dest)  # atomic within staging
                return
            except _Cancelled:
                raise
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                st.retries = attempt
                logger.warning(
                    "%s: attempt %d/%d failed (%s)", file.dest, attempt, MAX_RETRIES, exc
                )
                if attempt < MAX_RETRIES:
                    time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"Failed to download {file.dest}: {last_err}")

    def _stream(
        self,
        url: str,
        part: Path,
        st: ModelState,
        cancel: threading.Event,
        on_progress: Optional[Callable[[float, str], None]],
        expect: Optional[int],
    ) -> None:
        """Stream to `part`, resuming from an existing partial file if possible."""
        resume_at = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": "uvr-local/1.0"}
        token = os.environ.get("HF_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if resume_at:
            headers["Range"] = f"bytes={resume_at}-"

        req = Request(url, headers=headers)
        with urlopen(req, timeout=60) as resp:  # noqa: S310 (trusted HF host)
            length = resp.headers.get("Content-Length")
            total = int(length) if length else None
            if resume_at and resp.status != 206:
                # Server ignored Range — start over.
                resume_at = 0
                part.unlink(missing_ok=True)
            if total:
                st.total = max(st.total, total + resume_at)
            mode = "ab" if resume_at else "wb"
            with part.open(mode) as fh:
                while True:
                    if cancel.is_set():
                        raise _Cancelled()
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    fh.write(chunk)
                    st.tick(resume_at + fh.tell())
                    if on_progress:
                        pct = (st.received / st.total * 100) if st.total else 0.0
                        on_progress(min(pct, 99.0), f"Downloading model {pct:.0f}%")
        st.tick(resume_at + (part.stat().st_size if part.exists() else 0))

    def _verify(self, path: Path, spec: FileSpec) -> None:
        if not path.exists():
            raise RuntimeError(f"missing file after download: {spec.dest}")
        size = path.stat().st_size
        if spec.size and size != spec.size:
            raise RuntimeError(f"{spec.dest}: size {size} != expected {spec.size}")
        if spec.sha256:
            h = hashlib.sha256()
            with path.open("rb") as fh:
                for chunk in iter(lambda: fh.read(CHUNK), b""):
                    h.update(chunk)
            if h.hexdigest() != spec.sha256:
                raise RuntimeError(f"{spec.dest}: sha256 mismatch")


class _Cancelled(Exception):
    """Raised internally when a download is cancelled."""


# Module-level singleton — one manager for the whole worker process.
manager = ModelManager()
