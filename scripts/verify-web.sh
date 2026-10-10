#!/usr/bin/env bash
#
# Frontend verification gate: typecheck -> lint -> build -> browser smoke.
#
# Process ownership
# -----------------
# This script may only stop processes IT started. It deliberately does NOT
# `pkill` next, `kill` by port, or otherwise touch a server the developer is
# running — terminating an unrelated application is not an acceptable side
# effect of verifying.
#
# To achieve that, verification is fully isolated from normal development:
#
#   * its own build directory (`.next-verify` via UVR_NEXT_DIST_DIR), so it
#     never shares `.next` with a running dev/prod server and therefore never
#     needs that server stopped;
#   * its own port (UVR_VERIFY_PORT, default 3100), so it cannot collide with
#     the application's port 3000;
#   * explicit PID + process-group tracking, with cleanup registered on EXIT,
#     INT and TERM so a failed check, an error exit, or Ctrl-C all release it.
#
# If the verification port is already occupied, that is reported as a FAILURE
# rather than resolved by killing the listener.
#
# Usage:
#   scripts/verify-web.sh
#
# Exit: 0 = all green, 1 = a stage failed.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB="$ROOT/web"
# UVR_WEB_BIN allows running against a different Next/tsc install (a pnpm
# store, a hoisted monorepo root, or a stub used by the lifecycle tests).
BIN="${UVR_WEB_BIN:-$WEB/node_modules/.bin}"

VERIFY_DIST=".next-verify"
VERIFY_PORT="${UVR_VERIFY_PORT:-3100}"
export UVR_NEXT_DIST_DIR="$VERIFY_DIST"

# --- owned-process tracking ------------------------------------------------

VERIFY_PID=""
VERIFY_PGID=""

cleanup() {
  # Preserve the caller's exit status: a trap must never turn a failing gate
  # into a passing one (or vice versa) by changing $?.
  local rc=$?
  trap - EXIT INT TERM

  if [ -n "$VERIFY_PGID" ]; then
    # Signal the whole group: `next start` forks children, so killing only the
    # wrapper PID can leave the actual server holding the port.
    kill -TERM "-$VERIFY_PGID" 2>/dev/null
    for _ in $(seq 1 20); do
      kill -0 "-$VERIFY_PGID" 2>/dev/null || break
      sleep 0.25
    done
    kill -KILL "-$VERIFY_PGID" 2>/dev/null
  elif [ -n "$VERIFY_PID" ]; then
    kill -TERM "$VERIFY_PID" 2>/dev/null
  fi
  VERIFY_PID=""
  VERIFY_PGID=""

  cd "$WEB" 2>/dev/null && rm -rf "$VERIFY_DIST"

  exit "$rc"
}

# Registered BEFORE anything is started, so an early failure or a Ctrl-C during
# the build still runs cleanup.
trap cleanup EXIT
trap 'cleanup' INT TERM

cd "$WEB" || { echo "error: $WEB not found" >&2; exit 1; }

fail() {
  echo
  echo "FAILED at: $1"
  exit 1
}

# --- preflight -------------------------------------------------------------

if [ ! -x "$BIN/tsc" ] || [ ! -x "$BIN/next" ]; then
  echo "error: dependencies missing — run 'npm install' (or 'pnpm i') in web/" >&2
  exit 1
fi

# A listener on the verification port is reported, never killed. If it is a
# leftover from a previous crashed run, the operator decides.
if ss -ltn 2>/dev/null | grep -q ":$VERIFY_PORT "; then
  echo "error: something is already listening on :$VERIFY_PORT" >&2
  echo "       That is the verification port. Stop it, or re-run with" >&2
  echo "       UVR_VERIFY_PORT=<other> to use a different one." >&2
  exit 1
fi

# The application's own port is never inspected and never touched.

# --- 1. typecheck ----------------------------------------------------------

echo "==> typecheck (tsc --noEmit)"
"$BIN/tsc" --noEmit || fail "typecheck"

# --- 2. lint ---------------------------------------------------------------
#
# `next lint` exits 0 even when it reports warnings, so a plain call would
# print "✔ No ESLint warnings or errors" in some runs and still pass in
# others while a real warning sits in the output. `--max-warnings=0` turns any
# warning into a non-zero exit, which is what a gate should do.
#
# Verified: an injected `<img>` without alt produces 2 warnings
# (@next/next/no-img-element + jsx-a11y/alt-text) and fails this stage.

echo "==> lint (next lint --max-warnings=0)"
"$BIN/next" lint --max-warnings=0 || fail "lint"

# --- 3. build (isolated dist dir) -----------------------------------------

echo "==> production build (dist=$VERIFY_DIST)"
"$BIN/next" build || fail "build"

# --- 4. browser smoke against the temporary server -------------------------

echo "==> starting temporary server on :$VERIFY_PORT"
# setsid gives the server its own process group, so cleanup can signal the
# whole tree without reaching anything else on the machine.
setsid "$BIN/next" start -p "$VERIFY_PORT" >/tmp/verify-web-server.log 2>&1 &
VERIFY_PID=$!
VERIFY_PGID="$(ps -o pgid= -p "$VERIFY_PID" 2>/dev/null | tr -d ' ' | head -1)"

ready=0
for _ in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 3 "http://localhost:$VERIFY_PORT/" 2>/dev/null)
  if [ "$code" = "200" ]; then ready=1; break; fi
  sleep 1
done

if [ "$ready" -ne 1 ]; then
  echo "--- server log ---" >&2
  tail -20 /tmp/verify-web-server.log >&2
  fail "temporary server never became ready on :$VERIFY_PORT"
fi

echo "==> browser smoke (:$VERIFY_PORT)"
for route in / /tools/vocal-remover /tools/audio-repair /tools/instrument-extractor /explore; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 15 "http://localhost:$VERIFY_PORT$route" 2>/dev/null)
  [ "$code" = "200" ] || fail "smoke check $route returned $code"
  echo "    ok  $route"
done

# Scope note: these routes are asserted to RENDER, not to function against the
# worker. `next start` serves static/SSR output without the API, so this stage
# proves the build is servable, not that any model runs. Claiming more than
# that from a stage that only curls HTTP would be the kind of green that
# quietly stops meaning anything.

echo
echo "OK — typecheck, lint, build and browser smoke all passed"
echo "    (temporary server on :$VERIFY_PORT is stopped on exit)"