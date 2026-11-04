#!/usr/bin/env bash

MINER_DIR="${MINER_DIR:-/hive/miners/custom/coinrig-native}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

IFS=$'\t' read -r khs stats < <(
  "$PYTHON_BIN" "$MINER_DIR/submission-gate.py" stats \
    --url http://127.0.0.1:18082/2/summary \
    --timeout 2 2>/dev/null || printf '0\tnull\n'
)

khs="${khs:-0}"
stats="${stats:-null}"
