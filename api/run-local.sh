#!/usr/bin/env bash
#
# Run the UVR Local worker straight from a checkout — no Docker, no image
# rebuild. Use this for development: editing a .py file then takes effect on
# the next process start instead of a ~15 minute image rebuild.
#
#   ./run-local.sh          # first run syncs deps automatically
#   PORT=8001 ./run-local.sh
#
# The browser frontend can point at it with NEXT_PUBLIC_API_URL, or you can
# keep using the Docker web container.
set -euo pipefail

cd "$(dirname "$0")"

# Paths default to the repo layout. The model store IS shared with Docker (it
# is host-owned, so a model downloaded either way is reused rather than fetched
# twice). OUTPUT_ROOT deliberately is NOT shared: the container runs as root, so
# everything it creates under output/ is root-owned and the host user then
# cannot create the per-job upload directories. Using a separate output dir
# avoids needing sudo on every run.
export MODEL_CATALOG="${MODEL_CATALOG:-$PWD/models.json}"
export MODEL_STORE="${MODEL_STORE:-$PWD/../models}"
export OUTPUT_ROOT="${OUTPUT_ROOT:-$PWD/../output-local}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-max_split_size_mb:128}"

mkdir -p "$OUTPUT_ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: 'uv' is not installed. See https://docs.astral.sh/uv/" >&2
  exit 1
fi

# uv provisions a compatible interpreter itself: the host Python may be newer
# than the CUDA wheels support (torch cu128 has no 3.13+ builds).
if [ ! -d .venv ]; then
  echo "==> first run: creating .venv and installing dependencies"
  uv sync
fi

echo "==> OUTPUT_ROOT=$OUTPUT_ROOT"
echo "==> MODEL_STORE=$MODEL_STORE"
echo "==> http://0.0.0.0:${PORT:-8000}"
exec uv run --no-sync uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
