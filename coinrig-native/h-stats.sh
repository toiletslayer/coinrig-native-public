#!/usr/bin/env bash

package_dir_candidate="${COINRIG_PACKAGE_DIR:-$(dirname -- "${BASH_SOURCE[0]}")}"
PACKAGE_DIR="$(CDPATH= cd -- "$package_dir_candidate" 2>/dev/null && pwd -P)" || {
  khs=0
  stats=null
  return 0 2>/dev/null || exit 0
}
unset package_dir_candidate
PYTHON_BIN="${PYTHON_BIN:-python3}"

IFS=$'\t' read -r khs stats < <(
  "$PYTHON_BIN" "$PACKAGE_DIR/submission-gate.py" stats \
    --url http://127.0.0.1:18082/2/summary \
    --timeout 2 2>/dev/null || printf '0\tnull\n'
)

khs="${khs:-0}"
stats="${stats:-null}"
