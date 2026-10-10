#!/usr/bin/env bash
#
# The full pre-flight gate. Run this after every change, before believing it.
#
#   scripts/verify-all.sh              # everything
#   scripts/verify-all.sh --quick      # skip the production build (faster loop)
#   scripts/verify-all.sh --keep-dev   # don't kill a running next dev
#
# Stages:
#   1. catalog integrity  — the two catalogs agree (api/models.json vs web)
#   2. verifier self-test — the catalog verifier still detects known bugs
#   3. backend compiles   — py_compile every api module
#   4. typecheck + lint + build
#
# Exit: 0 = all green.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QUICK=0
KEEP_DEV=0
for arg in "$@"; do
  case "$arg" in
    --quick) QUICK=1 ;;
    --keep-dev) KEEP_DEV=1 ;;
  esac
done

FAILED=0
stage() { echo; echo "═══ $1 ═══"; }
record() { if [ "$1" -ne 0 ]; then FAILED=1; echo "  ✗ $2"; else echo "  ✓ $2"; fi; }

stage "1/6 catalog integrity"
python3 "$ROOT/scripts/verify-catalog.py"
record $? "api/models.json and web models.ts agree"

stage "2/6 catalog verifier self-test"
python3 "$ROOT/scripts/test-verify-catalog.py" >/dev/null 2>&1
record $? "verifier still catches all injected bug classes"

stage "3/6 backend compiles"
if [ -x "$ROOT/api/.venv/bin/python" ]; then
  PY="$ROOT/api/.venv/bin/python"
else
  PY="python3"
fi
COMPILE_OUT=$("$PY" -m py_compile \
  "$ROOT/api/main.py" \
  "$ROOT/api/backend.py" \
  "$ROOT/api/job_queue.py" \
  "$ROOT/api/model_manager.py" \
  "$ROOT/api/repair.py" 2>&1)
record $? "api/*.py compile cleanly ${COMPILE_OUT:+— $COMPILE_OUT}"

stage "4/6 repair pipeline (real ffmpeg)"
# DSP needs more than "exit 0": this checks every op is audible, full length,
# and that a chain which silences the signal is rejected.
if [ -x "$ROOT/api/.venv/bin/python" ]; then
  "$ROOT/api/.venv/bin/python" "$ROOT/scripts/test-repair.py" >/tmp/verify-repair.log 2>&1
  rc=$?
  [ $rc -ne 0 ] && tail -12 /tmp/verify-repair.log
  record $rc "repair ops produce audible, full-length audio"
else
  echo "  – skipped (no api/.venv)"
fi

stage "5/6 stem naming + VRAM release"
"$ROOT/api/.venv/bin/python" "$ROOT/scripts/test-stems.py" >/tmp/verify-stems.log 2>&1
rc=$?
[ $rc -ne 0 ] && tail -12 /tmp/verify-stems.log
record $rc "stem names canonical; both paths release VRAM"

stage "6/6 frontend"
WEB_ARGS=()
[ "$QUICK" -eq 1 ] && WEB_ARGS+=("--quick")
[ "$KEEP_DEV" -eq 1 ] && WEB_ARGS+=("--keep-dev")
if [ "$QUICK" -eq 1 ]; then
  # verify-web.sh has no --quick; emulate by running its first two stages.
  ( cd "$ROOT/web" || exit 1
    ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next lint --max-warnings=0 )
  record $? "typecheck + lint"
else
  "$ROOT/scripts/verify-web.sh" "${WEB_ARGS[@]+"${WEB_ARGS[@]}"}" >/tmp/verify-web.log 2>&1
  rc=$?
  [ $rc -ne 0 ] && tail -25 /tmp/verify-web.log
  record $rc "typecheck + lint + production build"
fi

echo
if [ "$FAILED" -eq 0 ]; then
  echo "═══ ALL GREEN ═══"
else
  echo "═══ GATE FAILED — see above ═══"
fi
exit "$FAILED"