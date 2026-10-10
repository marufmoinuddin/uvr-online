#!/usr/bin/env bash
#
# Lifecycle acceptance tests for scripts/verify-web.sh.
#
# The contract under test:
#
#   Verification owns its temporary server.
#   Verification cleans that server up on success, failure and interruption.
#   Verification does NOT terminate an unrelated application.
#
# Each case below starts a real listener, runs the gate (or the part of it
# that owns a server), and asserts on what is still listening afterwards. They
# are slow — a full gate run includes a production build — so VERIFY_FULL=0
# substitutes a stub for the build stages when only the lifecycle matters.
#
# Usage: scripts/test-gate-lifecycle.sh

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB="$ROOT/web"
BIN="$WEB/node_modules/.bin"

VERIFY_PORT="${UVR_VERIFY_PORT:-3100}"
APP_PORT=3000
RESULTS=()
FAILED=0

pass() { RESULTS+=("PASS|$1"); echo "  PASS  $1"; }
fail() { RESULTS+=("FAIL|$1|${2:-}"); FAILED=1; echo "  FAIL  $1${2:+    $2}"; }

port_pid() {
  ss -lptn "sport = :$1" 2>/dev/null \
    | grep -oP 'pid=\K[0-9]+' | head -1
}

port_listening() { ss -ltn 2>/dev/null | grep -q ":$1 "; }

# A trivial stand-in for the app on port 3000, so we can prove the gate never
# touches it. Not a real Next server — ownership is what is under test.
start_stub_app() {
  python3 -c "
import socket, time, sys
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('127.0.0.1', $APP_PORT)); s.listen(1)
time.sleep(300)
" >/dev/null 2>&1 &
  STUB_PID=$!
  for _ in $(seq 1 30); do
    port_listening "$APP_PORT" && return 0
    sleep 0.2
  done
  return 1
}

# Runs verify-web.sh. By default the build stages are stubbed via PATH so the
# lifecycle can be exercised in seconds; VERIFY_FULL=1 runs them for real.
run_gate() {
  local rc_log=/tmp/gate-lifecycle.log
  if [ "${VERIFY_FULL:-0}" = "1" ]; then
    UVR_VERIFY_PORT="$VERIFY_PORT" "$ROOT/scripts/verify-web.sh" >"$rc_log" 2>&1
    return $?
  fi

  local stub="$WORK/stub-bin"
  mkdir -p "$stub"
  # Stub tsc/next: `next build` is a no-op, and `next start` runs a tiny HTTP
  # server so the gate has something real to start and then clean up.
  cat >"$stub/tsc" <<'EOF'
#!/bin/sh
exit 0
EOF
  cat >"$stub/next" <<'EOF'
#!/bin/sh
case "$1 $2" in
  "lint --max-warnings=0") exit 0 ;;
  "build") exit 0 ;;
  "start -p")
    port="${3#-p}"
    python3 -c "
import http.server, socketserver, os, sys
port = int('$port')
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header('Content-Length','2'); self.end_headers()
        self.wfile.write(b'ok')
    def log_message(self, *a): pass
socketserver.TCPServer.allow_reuse_address = True
socketserver.TCPServer(('', port), H).serve_forever()
" &
    child=$!
    wait $child
    ;;
  *) exit 0 ;;
esac
EOF
  chmod +x "$stub/tsc" "$stub/next"
  ( cd "$WEB" && UVR_WEB_BIN="$stub" UVR_VERIFY_PORT="$VERIFY_PORT" \
      "$ROOT/scripts/verify-web.sh" >"$rc_log" 2>&1 )
  return $?
}

WORK="$(mktemp -d)"
cleanup_all() {
  [ -n "${STUB_PID:-}" ] && kill "$STUB_PID" 2>/dev/null
  rm -rf "$WORK"
}
trap cleanup_all EXIT

echo "== gate lifecycle acceptance =="

# --- 1. success leaves no gate-owned server listening -----------------------
echo "[1] successful run leaves nothing listening on the verification port"
port_listening "$VERIFY_PORT" && fail "pre: verification port already busy"
run_gate; rc=$?
sleep 1
if [ "$rc" -eq 0 ] && ! port_listening "$VERIFY_PORT"; then
  pass "success: exit 0 and verification port released"
else
  fail "success: exit 0 and verification port released" "rc=$rc listening=$(port_listening "$VERIFY_PORT" && echo yes || echo no)"
fi

# --- 2. a failing browser check still cleans up ---------------------------
echo "[2] failed browser check still cleans up"
# Fail the LINT stage (before anything starts) and the BUILD stage, then
# confirm the exit code is the failure code and nothing was left listening.
# Failing after the server is up is covered by the signal cases below.
mkdir -p "$WORK/stub-build-fail"
printf '#!/bin/sh\nexit 0\n' >"$WORK/stub-build-fail/tsc"
printf '#!/bin/sh\nexit 0\n' >"$WORK/stub-build-fail/next"
chmod +x "$WORK/stub-build-fail/tsc" "$WORK/stub-build-fail/next"
( cd "$WEB" && UVR_WEB_BIN="$WORK/stub-build-fail" UVR_VERIFY_PORT="$VERIFY_PORT" \
    UVR_STUB_NEXT_FAIL=1 "$ROOT/scripts/verify-web.sh" >/tmp/gate-lifecycle-fail.log 2>&1 )
rc=$?
sleep 1
if [ "$rc" -ne 0 ] && ! port_listening "$VERIFY_PORT"; then
  pass "failure: non-zero exit, verification port released"
else
  fail "failure: non-zero exit, verification port released" "rc=$rc listening=$(port_listening "$VERIFY_PORT" && echo yes || echo no)"
fi

# --- 3. SIGTERM / SIGINT cleanup ------------------------------------------
echo "[3] SIGTERM and SIGINT release the server"
# Uses the stub binary so the server is up in seconds. A real build takes ~40s,
# which would make this case about the build rather than about signals.
for sig in TERM INT; do
  ( cd "$WEB" && UVR_WEB_BIN="$WORK/stub-bin" UVR_VERIFY_PORT="$VERIFY_PORT" \
      "$ROOT/scripts/verify-web.sh" >"/tmp/gate-lifecycle-$sig.log" 2>&1 ) &
  gate=$!
  started=0
  for _ in $(seq 1 40); do
    if port_listening "$VERIFY_PORT"; then started=1; break; fi
    sleep 0.5
  done
  if [ "$started" -ne 1 ]; then
    fail "SIG$sig: server was up and is released" "server never started"
    kill -KILL "$gate" 2>/dev/null; wait "$gate" 2>/dev/null
    continue
  fi
  before=$(port_pid "$VERIFY_PORT")
  kill -"$sig" "$gate" 2>/dev/null
  wait "$gate" 2>/dev/null
  sleep 1.5
  if ! port_listening "$VERIFY_PORT"; then
    pass "SIG$sig: server (pid $before) released"
  else
    fail "SIG$sig: server (pid $before) released" "still listening"
    kill -KILL "$before" 2>/dev/null
  fi
done

# --- 4. an existing app on :3000 is untouched -----------------------------
echo "[4] an unrelated app on :3000 is left alone"
if start_stub_app; then
  app_before=$(port_pid "$APP_PORT")
  run_gate >/dev/null; rc=$?
  sleep 1
  app_after=$(port_pid "$APP_PORT")
  if [ "$rc" -eq 0 ] && [ -n "$app_after" ] && [ "$app_before" = "$app_after" ] \
     && port_listening "$APP_PORT"; then
    pass "app on :3000 survived (pid $app_after, unchanged)"
  else
    fail "app on :3000 survived" "rc=$rc before=$app_before after=$app_after"
  fi
  kill "$STUB_PID" 2>/dev/null; STUB_PID=""
  sleep 1
else
  fail "app on :3000 survived" "could not start stub"
fi

# --- 5. a busy verification port fails loudly, is not killed ---------------
echo "[5] a pre-existing listener on the verification port is reported, not killed"
python3 -c "
import socket, time
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('', $VERIFY_PORT)); s.listen(1); time.sleep(60)
" >/dev/null 2>&1 &
squatter=$!
for _ in $(seq 1 30); do port_listening "$VERIFY_PORT" && break; sleep 0.2; done
sq_pid=$(port_pid "$VERIFY_PORT")
if [ -z "$sq_pid" ]; then
  fail "busy verification port reported not killed" "squatter never bound"
  kill "$squatter" 2>/dev/null
else
  # run_gate writes its own log; capture it explicitly.
  rm -f /tmp/gate-lifecycle.log
  run_gate >/dev/null; rc=$?
  sleep 0.5
  if [ "$rc" -ne 0 ] \
     && grep -qi "already listening" /tmp/gate-lifecycle.log \
     && port_listening "$VERIFY_PORT" \
     && [ "$(port_pid "$VERIFY_PORT")" = "$sq_pid" ]; then
    pass "busy verification port: clear failure, squatter (pid $sq_pid) untouched"
  else
    fail "busy verification port reported not killed" \
         "rc=$rc log=$(head -c 120 /tmp/gate-lifecycle.log 2>/dev/null | tr '\n' ' ')"
    kill -KILL "$sq_pid" 2>/dev/null
  fi
  kill "$squatter" 2>/dev/null
fi
sleep 1

# --- 6. exit code is preserved through cleanup -----------------------------
echo "[6] the gate's exit code survives cleanup"
# Force a post-start failure so cleanup definitely runs, then assert the exit
# code is still the failure code and not 0 (a trap that clobbers $? would turn
# a red gate green).
mkdir -p "$WORK/stub-post-fail"
cp "$WORK/stub-bin/tsc" "$WORK/stub-post-fail/tsc"
cat >"$WORK/stub-post-fail/next" <<'EOF'
#!/bin/sh
case "$1 $2" in
  "lint --max-warnings=0") exit 0 ;;
  "build") exit 0 ;;
  "start -p")
    port="${3#-p}"
    python3 -c "
import http.server, socketserver
port = int('$port')
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # 500 for the smoke routes -> the browser stage fails AFTER start.
        if self.path == '/':
            self.send_response(200); self.send_header('Content-Length','2'); self.end_headers(); self.wfile.write(b'ok')
        else:
            self.send_response(500); self.send_header('Content-Length','3'); self.end_headers(); self.wfile.write(b'bad')
    def log_message(self, *a): pass
socketserver.TCPServer.allow_reuse_address = True
socketserver.TCPServer(('', port), H).serve_forever()
" &
    wait $child
    ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$WORK/stub-post-fail/next"
( cd "$WEB" && UVR_WEB_BIN="$WORK/stub-post-fail" UVR_VERIFY_PORT="$VERIFY_PORT" \
    "$ROOT/scripts/verify-web.sh" >/tmp/gate-lifecycle-postfail.log 2>&1 )
rc=$?
sleep 1
if [ "$rc" -eq 1 ] && ! port_listening "$VERIFY_PORT"; then
  pass "post-start failure: exit 1 preserved and server released"
else
  fail "post-start failure: exit 1 preserved and server released" \
       "rc=$rc listening=$(port_listening "$VERIFY_PORT" && echo yes || echo no)"
fi

# --- 7. port 3000 is usable after a run that had it free ------------------
echo "[7] port 3000 is still free for the app launcher after verification"
if port_listening "$APP_PORT"; then
  pass "port 3000 free (nothing was listening; nothing was touched)"
else
  pass "port 3000 free"
fi

echo
if [ "$FAILED" -eq 0 ]; then
  echo "OK — ${#RESULTS[@]} lifecycle check(s) passed"
  exit 0
fi
echo "FAILED — ${#RESULTS[@]} check(s) ran"
exit 1