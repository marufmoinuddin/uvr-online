#!/usr/bin/env bash
#
# Frontend verification gate: typecheck -> lint -> production build.
#
# Two things this script exists to enforce:
#
#   1. `next dev` and `next build` SHARE .next. A running dev server makes the
#      build fail with "Cannot find module for page" / "_app.js.nft.json ENOENT",
#      which looks like a code bug but is really a stale-cache collision. So we
#      always stop every next process and wipe .next before building.
#   2. npm is not on PATH in this environment; the binaries under
#      node_modules/.bin are the supported entry point.
#
# Usage:
#   scripts/verify-web.sh              # typecheck + lint + build
#   scripts/verify-web.sh --keep-dev   # don't kill a running dev server
#
# Exit: 0 = all green, 1 = a stage failed.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB="$ROOT/web"
BIN="$WEB/node_modules/.bin"

KEEP_DEV=0
[ "${1:-}" = "--keep-dev" ] && KEEP_DEV=1

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

if [ "$KEEP_DEV" -eq 0 ]; then
  # Stop dev servers AND the standalone server, which is spawned separately and
  # does not always match a 'next dev' pattern.
  if pgrep -f 'next dev|next-server|next start' >/dev/null 2>&1; then
    echo "==> stopping running next processes (they share .next with the build)"
    pkill -f 'next dev|next-server|next start' >/dev/null 2>&1
    sleep 1
    pkill -9 -f 'next dev|next-server|next start' >/dev/null 2>&1
    sleep 1
  fi
  # A stale server can keep holding the port even after the process is gone.
  if ss -ltn 2>/dev/null | grep -q ':3000 '; then
    echo "warning: something is still listening on :3000 — build may collide"
  fi
  rm -rf .next
  echo "==> .next cleared"
fi

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

# --- 3. build --------------------------------------------------------------

echo "==> production build"
"$BIN/next" build || fail "build"

echo
echo "OK — typecheck, lint and build all passed"