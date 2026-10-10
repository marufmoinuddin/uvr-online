#!/usr/bin/env bash
# Start (or restart) the Next.js frontend on :3000.
#
# Mirrors scripts/restart-worker.sh for the API side: stop whatever owns the
# port, wait for it to actually release, then start fresh. Plain `next start`
# on an occupied port exits with a confusing "port already in use" after a
# partially-served build.
set -euo pipefail

cd "$(dirname "$0")/.."
WEB_DIR="$PWD/web"
PORT="${WEB_PORT:-3000}"

# Kill any process holding the port. `--` guards against a pid that looks
# like an option; `2>/dev/null || true` because it is absent most of the time.
pids=$(ss -lptn "sport = :$PORT" 2>/dev/null \
  | grep -oP 'pid=\K[0-9]+' | sort -u || true)
if [[ -n "$pids" ]]; then
  echo "==> stopping web on :$PORT (pids: $(echo "$pids" | tr '\n' ' '))"
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null || true
  for _ in $(seq 1 40); do
    ss -lnt "sport = :$PORT" 2>/dev/null | grep -q LISTEN || break
    sleep 0.25
  done
  if ss -lnt "sport = :$PORT" 2>/dev/null | grep -q LISTEN; then
    echo "ERROR: port $PORT still in use; refusing to start" >&2
    exit 1
  fi
fi

echo "==> building"
cd "$WEB_DIR"
./node_modules/.bin/next build >/tmp/uvr-web-build.log 2>&1 || {
  echo "BUILD FAILED — see /tmp/uvr-web-build.log" >&2
  tail -30 /tmp/uvr-web-build.log >&2
  exit 1
}

echo "==> starting web on :$PORT"
exec ./node_modules/.bin/next start -p "$PORT"