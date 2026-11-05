#!/usr/bin/env bash
set -euo pipefail

package_dir_candidate="${COINRIG_PACKAGE_DIR:-$(dirname -- "${BASH_SOURCE[0]}")}"
PACKAGE_DIR="$(CDPATH= cd -- "$package_dir_candidate" 2>/dev/null && pwd -P)" || {
  printf 'coinrig-native: cannot resolve installed package directory\n' >&2
  exit 1
}
unset package_dir_candidate
MINER_LOG_DIR="${MINER_LOG_DIR:-/var/log/miner/coinrig-native}"
LOG_FILE="$MINER_LOG_DIR/coinrig-native.log"
XMRIG_LOG_FILE="$PACKAGE_DIR/xmrig.log"
READY_FILE="$PACKAGE_DIR/.full-dataset-ready"
PYTHON_BIN="${PYTHON_BIN:-python3}"
FULL_DATASET_TIMEOUT="${FULL_DATASET_TIMEOUT:-300}"
GATE_PID=""
MINER_PID=""

log_event() {
  printf '%s coinrig-native: %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >> "$LOG_FILE"
}

terminate_children() {
  if [[ -n "$MINER_PID" ]] && kill -0 "$MINER_PID" 2>/dev/null; then
    kill -TERM "$MINER_PID" 2>/dev/null || true
  fi
  if [[ -n "$GATE_PID" ]] && kill -0 "$GATE_PID" 2>/dev/null; then
    kill -TERM "$GATE_PID" 2>/dev/null || true
  fi
  [[ -z "$MINER_PID" ]] || wait "$MINER_PID" 2>/dev/null || true
  [[ -z "$GATE_PID" ]] || wait "$GATE_PID" 2>/dev/null || true
  rm -f "$READY_FILE"
}

on_signal() {
  log_event "stop requested; terminating miner and submission gate"
  terminate_children
  exit 143
}

fail_run() {
  log_event "$*"
  terminate_children
  exit 1
}

xmrig_log_has() {
  [[ -f "$XMRIG_LOG_FILE" ]] && grep -Fq -- "$1" "$XMRIG_LOG_FILE"
}

trap on_signal INT TERM HUP

mkdir -p "$MINER_LOG_DIR"
touch "$LOG_FILE"
rm -f "$READY_FILE" "$XMRIG_LOG_FILE" ||
  fail_run "cannot clear stale readiness or XMRig log state"

[[ "$FULL_DATASET_TIMEOUT" =~ ^[1-9][0-9]{0,2}$ ]] && (( FULL_DATASET_TIMEOUT <= 600 )) ||
  fail_run "FULL_DATASET_TIMEOUT must be 1-600 seconds"

command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail_run "python3 is required"
test -x "$PACKAGE_DIR/xmrig" || fail_run "xmrig is missing or not executable"
test -f "$PACKAGE_DIR/config.json" || fail_run "config.json is missing; HiveOS must run h-config.sh first"
test -f "$PACKAGE_DIR/.gateway" || fail_run "validated gateway state is missing"

gateway="$(tr -d '\r\n' < "$PACKAGE_DIR/.gateway")"
gateway_pair="$("$PYTHON_BIN" "$PACKAGE_DIR/submission-gate.py" validate-endpoint --endpoint "$gateway")" ||
  fail_run "gateway must be a trusted RFC1918 IPv4 host:port"
read -r gateway_host gateway_port <<< "$gateway_pair"
THREADS="$("$PYTHON_BIN" "$PACKAGE_DIR/submission-gate.py" validate-config \
  --config "$PACKAGE_DIR/config.json" \
  --expected-log-file "$XMRIG_LOG_FILE")" ||
  fail_run "locked startup configuration rejected"
[[ "$THREADS" =~ ^[1-9][0-9]{0,2}$ ]] && (( THREADS <= 256 )) ||
  fail_run "validator returned an invalid thread count"

"$PYTHON_BIN" "$PACKAGE_DIR/submission-gate.py" serve \
  --listen-host 127.0.0.1 \
  --listen-port 18882 \
  --upstream-host "$gateway_host" \
  --upstream-port "$gateway_port" \
  --ready-file "$READY_FILE" >> "$LOG_FILE" 2>&1 &
GATE_PID=$!

sleep 0.2
kill -0 "$GATE_PID" 2>/dev/null || fail_run "submission gate failed to start"

log_event "starting XMRig; submitblock remains blocked pending full-dataset proof"
umask 077
"$PACKAGE_DIR/xmrig" \
  --config "$PACKAGE_DIR/config.json" \
  --log-file="$XMRIG_LOG_FILE" \
  --algo=rx/2 \
  --daemon \
  --threads="$THREADS" \
  --randomx-mode=fast \
  --randomx-wrmsr=-1 \
  --donate-level=0 \
  --no-color >> "$LOG_FILE" 2>&1 &
MINER_PID=$!

started="$(date +%s)"
while kill -0 "$MINER_PID" 2>/dev/null; do
  kill -0 "$GATE_PID" 2>/dev/null || fail_run "submission gate exited; stopping miner"

  if xmrig_log_has "switching to slow mode" ||
     xmrig_log_has "fast RandomX mode disabled"; then
    fail_run "slow/light RandomX fallback detected; stopping before submitblock can pass"
  fi

  if xmrig_log_has "allocated 2336 MB" && xmrig_log_has "dataset ready"; then
    printf 'full-dataset-ready\n' > "$READY_FILE"
    log_event "full 2336 MB RandomX dataset confirmed; submitblock gate opened"
    break
  fi

  now="$(date +%s)"
  (( now - started < FULL_DATASET_TIMEOUT )) ||
    fail_run "full RandomX dataset was not confirmed within ${FULL_DATASET_TIMEOUT}s"
  sleep 0.25
done

if ! kill -0 "$MINER_PID" 2>/dev/null; then
  wait "$MINER_PID" || miner_status=$?
  miner_status="${miner_status:-0}"
  fail_run "miner exited before full-dataset confirmation (status $miner_status)"
fi

while kill -0 "$MINER_PID" 2>/dev/null; do
  kill -0 "$GATE_PID" 2>/dev/null || fail_run "submission gate exited; stopping miner"
  if xmrig_log_has "switching to slow mode" ||
     xmrig_log_has "fast RandomX mode disabled"; then
    fail_run "slow/light RandomX fallback detected after startup; stopping miner"
  fi
  sleep 1
done

miner_status=0
wait "$MINER_PID" || miner_status=$?
terminate_children
exit "$miner_status"
