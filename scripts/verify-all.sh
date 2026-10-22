#!/usr/bin/env bash
#
# The full pre-flight gate. Run this after every change, before believing it.
#
#   scripts/verify-all.sh              # everything
#   scripts/verify-all.sh --quick      # skip the production build (faster loop)
#
# Process ownership: the gate never stops a server it did not start. The
# frontend stage builds into its own directory and port, and cleans up only
# its own process group — see scripts/verify-web.sh.
#
# Stages:
#   1. catalog integrity  — the two catalogs agree (api/models.json vs web)
#   2. verifier self-test — the catalog verifier still detects known bugs
#   3. backend compiles   — py_compile every api module
#   4. repair pipeline    — DSP and the combined DSP+neural workflow
#   5. stem naming + VRAM release
#   6. CPU mode           — device resolution, the CPU catalogue guard, and a
#                            real separation on the CPU
#   7. frontend           — typecheck + lint + build + browser smoke
#
# Exit: 0 = all green.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QUICK=0
for arg in "$@"; do
  case "$arg" in
    --quick) QUICK=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

FAILED=0
stage() { echo; echo "═══ $1 ═══"; }
record() { if [ "$1" -ne 0 ]; then FAILED=1; echo "  ✗ $2"; else echo "  ✓ $2"; fi; }

stage "1/7 catalog integrity"
python3 "$ROOT/scripts/verify-catalog.py"
record $? "api/models.json and web models.ts agree"

stage "2/7 catalog verifier self-test"
if python3 "$ROOT/scripts/test-verify-catalog.py" >/dev/null 2>&1; then
  record 0 "verifier still catches all injected bug classes"
else
  record 1 "verifier still catches all injected bug classes"
fi

# The catalogue writer edits models.ts IN PLACE. A writer that can silently
# mangle the file it maintains is worse than none, so its nested-metadata
# insert, idempotency and misaligned-spec paths are regression-tested too.
python3 "$ROOT/scripts/test-add-verified-models.py" >/tmp/verify-writer.log 2>&1
record $? "catalogue writer is idempotent and formats nested metadata safely"

# The frontend stage owns a temporary server; these prove it only ever stops
# what it started, and that it stops it on every exit path.
bash "$ROOT/scripts/test-gate-lifecycle.sh" >/tmp/verify-lifecycle.log 2>&1
rc=$?
[ $rc -ne 0 ] && tail -12 /tmp/verify-lifecycle.log
record $rc "gate owns only its own server and always releases it"

stage "3/7 backend compiles"
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
  "$ROOT/api/sep_worker.py" \
  "$ROOT/api/repair.py" 2>&1)
record $? "api/*.py compile cleanly ${COMPILE_OUT:+— $COMPILE_OUT}"

stage "4/7 repair pipeline (real ffmpeg + neural workflow)"
# DSP needs more than "exit 0": this checks every op is audible, full length,
# and that a chain which silences the signal is rejected. The second script
# covers the combined DSP + neural repair workflow.
if [ -x "$ROOT/api/.venv/bin/python" ]; then
  "$ROOT/api/.venv/bin/python" "$ROOT/scripts/test-repair.py" >/tmp/verify-repair.log 2>&1
  rc=$?
  [ $rc -ne 0 ] && tail -12 /tmp/verify-repair.log
  record $rc "repair ops produce audible, full-length audio"

  "$ROOT/api/.venv/bin/python" "$ROOT/scripts/test-repair-workflow.py" \
    >/tmp/verify-repair-workflow.log 2>&1
  rc=$?
  [ $rc -ne 0 ] && tail -14 /tmp/verify-repair-workflow.log
  record $rc "combined DSP+neural repair: one output, declared stem, stage order"
else
  echo "  – skipped (no api/.venv)"
fi

stage "5/7 stem naming + VRAM release"
"$ROOT/api/.venv/bin/python" "$ROOT/scripts/test-stems.py" >/tmp/verify-stems.log 2>&1
rc=$?
[ $rc -ne 0 ] && tail -12 /tmp/verify-stems.log
record $rc "stem names canonical; both paths release VRAM"

stage "6/7 CPU mode (device resolution, catalogue guard, real CPU separation)"
# Runs the whole CPU path end to end on the CPU: the device setting, the
# refusal of a model the catalogue does not mark CPU-capable, and a real
# separation whose stems are checked for silence, NaN and duration drift.
# UVR_DEVICE=cpu is set even though the test sets it itself, so the stage
# cannot accidentally pass by running on a GPU.
if [ -x "$ROOT/api/.venv/bin/python" ]; then
  UVR_DEVICE=cpu "$ROOT/api/.venv/bin/python" "$ROOT/scripts/test-cpu-mode.py" --full \
    >/tmp/verify-cpu.log 2>&1
  rc=$?
  [ $rc -ne 0 ] && tail -14 /tmp/verify-cpu.log
  record $rc "CPU mode works, and blocked models are refused with a clear error"
else
  echo "  – skipped (no api/.venv)"
fi

stage "7/7 frontend (typecheck + lint + build + browser smoke)"
WEB_ARGS=()
[ "$QUICK" -eq 1 ] && WEB_ARGS+=("--quick")
if [ "$QUICK" -eq 1 ]; then
  # verify-web.sh has no --quick; emulate by running its first two stages.
  ( cd "$ROOT/web" || exit 1
    ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next lint --max-warnings=0 )
  record $? "typecheck + lint"
else
  "$ROOT/scripts/verify-web.sh" "${WEB_ARGS[@]+"${WEB_ARGS[@]}"}" >/tmp/verify-web.log 2>&1
  rc=$?
  [ $rc -ne 0 ] && tail -25 /tmp/verify-web.log
  record $rc "typecheck + lint + production build + browser smoke"
fi

echo
if [ "$FAILED" -eq 0 ]; then
  echo "═══ ALL GREEN ═══"
else
  echo "═══ GATE FAILED — see above ═══"
fi
exit "$FAILED"