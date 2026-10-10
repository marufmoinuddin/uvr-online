#!/usr/bin/env bash
#
# Restart the local worker cleanly — no orphans, no leaked VRAM.
#
# WHY THIS EXISTS
#   `run-local.sh` ends in `exec uv run ... uvicorn`, and `uv run` FORKS rather
#   than execs. So `pkill -f 'uvicorn main:app'` kills the child while its
#   parent wrapper survives, and repeated restarts accumulate orphaned workers.
#   Each one holds ~140 MB of VRAM idle, and the two that had loaded a large
#   model held ~1 GB each. On a 5.8 GB card that quietly ate the whole GPU and
#   made unrelated models fail to load with:
#
#     New implementation failed: CUDA out of memory ... has a total capacity of
#     5.78 GiB of which 19.44 MiB is free
#
#   which audio-separator reports as the deeply misleading:
#     "model file is corrupt or incomplete"
#
#   Two catalog models (Duality V1 / InstVox Duality V2) were wrongly marked
#   unsupported because of this. They work fine once the GPU is actually free.
#
# Usage:  scripts/restart-worker.sh [--stop-only]

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8000}"
STOP_ONLY=0
[ "${1:-}" = "--stop-only" ] && STOP_ONLY=1

# Match the real uvicorn child, not just the `uv run` wrapper.
worker_pids() {
  pgrep -f "uvicorn main:app.*--port ${PORT}" 2>/dev/null
  # Anything still bound to the port, whatever its cmdline.
  ss -lptnH "sport = :${PORT}" 2>/dev/null \
    | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u
}

kill_workers() {
  local pids
  pids="$(worker_pids | sort -u | tr '\n' ' ')"
  [ -z "${pids// /}" ] && return 0
  echo "==> stopping workers: ${pids% }"
  # Signal the whole process GROUP so the uv wrapper dies with the child.
  for p in $pids; do
    pgid="$(ps -o pgid= -p "$p" 2>/dev/null | tr -d ' ')"
    if [ -n "${pgid:-}" ] && [ "$pgid" != "$(ps -o pgid= -p $$ | tr -d ' ')" ]; then
      kill -TERM -- "-${pgid}" 2>/dev/null || kill -TERM "$p" 2>/dev/null
    else
      kill -TERM "$p" 2>/dev/null
    fi
  done
  for _ in $(seq 1 20); do
    pgrep -f "uvicorn main:app.*--port ${PORT}" >/dev/null 2>&1 || break
    sleep 0.5
  done
  for p in $(worker_pids | sort -u); do kill -9 "$p" 2>/dev/null; done
}

port_busy() { ss -lptnH "sport = :${PORT}" 2>/dev/null | grep -q .; }

kill_workers
# Verify rather than assume — this is the whole point of the script.
if port_busy; then
  echo "!! port ${PORT} is still bound after cleanup; refusing to continue" >&2
  ss -lptn "sport = :${PORT}" >&2
  exit 1
fi
[ "$STOP_ONLY" -eq 1 ] && { echo "==> port ${PORT} free"; exit 0; }

if command -v nvidia-smi >/dev/null 2>&1; then
  left="$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | wc -l)"
  used="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null)"
  echo "==> GPU: ${used} MiB used across ${left} process(es)"
fi

cd "$ROOT/api"
echo "==> starting worker on :${PORT}"
nohup ./run-local.sh > /tmp/uvr-api.log 2>&1 &

for i in $(seq 1 60); do
  if curl -fsS -m 2 "http://localhost:${PORT}/api/health" >/dev/null 2>&1; then
    echo "==> healthy: $(curl -sS -m 3 "http://localhost:${PORT}/api/health")"
    exit 0
  fi
  sleep 1
done
echo "!! worker did not become healthy within 60s — see /tmp/uvr-api.log" >&2
tail -20 /tmp/uvr-api.log >&2
exit 1