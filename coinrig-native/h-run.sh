#!/usr/bin/env bash
set -euo pipefail

MINER_DIR="${MINER_DIR:-/hive/miners/custom/coinrig-native}"
MINER_LOG_DIR="${MINER_LOG_DIR:-/var/log/miner/coinrig-native}"
LOG_FILE="$MINER_LOG_DIR/coinrig-native.log"
READY_FILE="$MINER_DIR/.full-dataset-ready"
PYTHON_BIN="${PYTHON_BIN:-python3}"
FULL_DATASET_TIMEOUT="${FULL_DATASET_TIMEOUT:-300}"
GATE_PID=""
MINER_PID=""
START_LINE=1

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

current_run_log_has() {
  awk -v start="$START_LINE" -v needle="$1" '
    NR >= start && index($0, needle) { found = 1; exit }
    END { exit(found ? 0 : 1) }
  ' "$LOG_FILE"
}

trap on_signal INT TERM HUP

mkdir -p "$MINER_LOG_DIR"
touch "$LOG_FILE"
rm -f "$READY_FILE"

[[ "$FULL_DATASET_TIMEOUT" =~ ^[1-9][0-9]{0,2}$ ]] && (( FULL_DATASET_TIMEOUT <= 600 )) ||
  fail_run "FULL_DATASET_TIMEOUT must be 1-600 seconds"

command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail_run "python3 is required"
test -x "$MINER_DIR/xmrig" || fail_run "xmrig is missing or not executable"
test -f "$MINER_DIR/config.json" || fail_run "config.json is missing; HiveOS must run h-config.sh first"
test -f "$MINER_DIR/.gateway" || fail_run "validated gateway state is missing"

gateway="$(tr -d '\r\n' < "$MINER_DIR/.gateway")"
gateway_pair="$("$PYTHON_BIN" "$MINER_DIR/submission-gate.py" validate-endpoint --endpoint "$gateway")" ||
  fail_run "gateway must be a trusted RFC1918 IPv4 host:port"
read -r gateway_host gateway_port <<< "$gateway_pair"
"$PYTHON_BIN" "$MINER_DIR/submission-gate.py" validate-config --config "$MINER_DIR/config.json" ||
  fail_run "locked startup configuration rejected"

"$PYTHON_BIN" "$MINER_DIR/submission-gate.py" serve \
  --listen-host 127.0.0.1 \
  --listen-port 18882 \
  --upstream-host "$gateway_host" \
  --upstream-port "$gateway_port" \
  --ready-file "$READY_FILE" >> "$LOG_FILE" 2>&1 &
GATE_PID=$!

sleep 0.2
kill -0 "$GATE_PID" 2>/dev/null || fail_run "submission gate failed to start"

START_LINE=$(( $(wc -l < "$LOG_FILE") + 1 ))
log_event "starting XMRig; submitblock remains blocked pending full-dataset proof"
"$MINER_DIR/xmrig" \
  --config "$MINER_DIR/config.json" \
  --algo=rx/2 \
  --daemon \
  --threads=32 \
  --randomx-mode=fast \
  --randomx-wrmsr=-1 \
  --donate-level=0 \
  --no-color >> "$LOG_FILE" 2>&1 &
MINER_PID=$!

started="$(date +%s)"
while kill -0 "$MINER_PID" 2>/dev/null; do
  kill -0 "$GATE_PID" 2>/dev/null || fail_run "submission gate exited; stopping miner"

  if current_run_log_has "switching to slow mode" ||
     current_run_log_has "fast RandomX mode disabled"; then
    fail_run "slow/light RandomX fallback detected; stopping before submitblock can pass"
  fi

  if current_run_log_has "allocated 2336 MB" && current_run_log_has "dataset ready"; then
    umask 077
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
  if current_run_log_has "switching to slow mode" ||
     current_run_log_has "fast RandomX mode disabled"; then
    fail_run "slow/light RandomX fallback detected after startup; stopping miner"
  fi
  sleep 1
done

miner_status=0
wait "$MINER_PID" || miner_status=$?
terminate_children
exit "$miner_status"
