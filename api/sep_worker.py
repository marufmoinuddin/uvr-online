"""Child process that runs ONE separation job.

Separation runs in its own process rather than in a thread of the worker,
because a Python thread cannot be killed:

  * A cancelled or timed-out job on a CPU would otherwise keep burning every
    core for the remaining (possibly hours-long) inference while the queue
    reported it as cancelled, and every job behind it would wait. Killing the
    process is the only way to actually stop the work.
  * A native crash — a CUDA OOM inside torch used to abort the whole worker
    with an uncatchable SIGSEGV — now takes down the child, not the API. The
    job fails, the worker survives, and the next job can start.

The protocol with the parent is deliberately tiny: a queue of tagged tuples.

    ("progress", float, str)    best-effort progress, 0-100
    ("result", list[dict])      the stems that were produced
    ("error", str)              a human-readable failure

This module has no import-time side effects and deliberately does not import
`main`: the `spawn` start method re-imports the target's module in the child,
so anything imported here runs twice (once per process) and must be inert.
"""

from __future__ import annotations

import logging
import os
import traceback
from typing import Any

logger = logging.getLogger("uvr.worker")


def run_separation(request: dict[str, Any], channel: Any) -> None:
    """Run one separation, reporting progress and the result to the parent.

    Everything the job needs arrives in `request`; nothing is read from the
    parent's memory, because there is no shared memory between the two
    processes.
    """
    # Imported here, not at module scope: the parent imports this module to
    # get the target function, and importing the whole inference stack twice
    # would double the parent's start-up cost for no reason.
    from backend import separate_file

    model_id = request["modelId"]
    input_path = request["inputPath"]
    output_dir = request["outputDir"]

    def progress(pct: float, stage: str) -> None:
        try:
            channel.put(("progress", float(pct), str(stage)))
        except Exception:  # pragma: no cover - the parent may be gone
            pass

    try:
        stems = separate_file(
            model_id,
            input_path,
            output_dir,
            request.get("outputFormat") or "mp3",
            bool(request.get("useTTA", False)),
            bool(request.get("extractInstrumental", False)),
            progress,
            request.get("extractTarget") or None,
        )
    except BaseException as exc:  # noqa: BLE001 - reported to the parent
        logger.exception("Separation failed in the child process")
        message = str(exc) or exc.__class__.__name__
        try:
            channel.put(("error", message))
        except Exception:  # pragma: no cover
            pass
        _flush(channel)
        return

    try:
        channel.put(("result", stems))
    except Exception:  # pragma: no cover
        pass
    _flush(channel)


def _flush(channel: Any) -> None:
    """Make sure the queued messages are actually delivered before we exit.

    A multiprocessing queue is written by a background feeder thread; exiting
    without closing it can drop the final message, which would leave the parent
    waiting for a result that was already on its way.
    """
    try:
        channel.close()
        channel.join_thread()
    except Exception:  # pragma: no cover
        pass
