#!/usr/bin/env bash

# HiveOS sources this callback; do not change the parent shell's option state.
ENDPOINT="${CUSTOM_URL:-}"
WALLET="${CUSTOM_TEMPLATE:-}"
ALGO="${CUSTOM_ALGO:-}"
EXTRA="${CUSTOM_USER_CONFIG:-}"

die() {
  printf 'coinrig-native: %s\n' "$*" >&2
  return 1 2>/dev/null || exit 1
}

package_dir_candidate="${COINRIG_PACKAGE_DIR:-$(dirname -- "${BASH_SOURCE[0]}")}"
PACKAGE_DIR="$(CDPATH= cd -- "$package_dir_candidate" 2>/dev/null && pwd -P)" || {
  die "cannot resolve installed package directory" || return $?
}
unset package_dir_candidate

command -v python3 >/dev/null 2>&1 || { die "python3 is required"; return $?; }
if ! python3 "$PACKAGE_DIR/submission-gate.py" validate-endpoint --endpoint "$ENDPOINT" >/dev/null; then
  die "CUSTOM_URL must be a trusted RFC1918 IPv4 host:port" || return $?
fi

case "$ALGO" in
  ""|rx2|rx/2) ;;
  *) die "CUSTOM_ALGO must be rx2, rx/2, or empty" || return $? ;;
esac

case "$EXTRA" in
  ""|threads=32) ;;
  *) die "CUSTOM_USER_CONFIG must be threads=32 or empty" || return $? ;;
esac

if [[ ! "$WALLET" =~ ^C[123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]{94}$ ]]; then
  die "CUSTOM_TEMPLATE must be a 95-character COIN primary address beginning with C" || return $?
fi

mkdir -p "$PACKAGE_DIR" || { die "cannot create miner directory"; return $?; }
umask 077
config_tmp="$PACKAGE_DIR/.config.json.$$"
gateway_tmp="$PACKAGE_DIR/.gateway.$$"

if ! cat > "$config_tmp" <<EOF
{
  "api": { "id": null, "worker-id": null },
  "http": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 18082,
    "access-token": null,
    "restricted": true
  },
  "autosave": false,
  "background": false,
  "colors": false,
  "title": false,
  "randomx": {
    "init": -1,
    "mode": "fast",
    "1gb-pages": false,
    "rdmsr": false,
    "wrmsr": false
  },
  "cpu": {
    "enabled": true,
    "huge-pages": true,
    "huge-pages-jit": false,
    "hw-aes": null,
    "priority": null,
    "memory-pool": false,
    "yield": true,
    "asm": true,
    "rx/2": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31]
  },
  "opencl": false,
  "cuda": false,
  "log-file": null,
  "donate-level": 0,
  "print-time": 30,
  "health-print-time": 60,
  "retries": 5,
  "retry-pause": 5,
  "pools": [
    {
      "algo": "rx/2",
      "url": "127.0.0.1:18882",
      "user": "$WALLET",
      "pass": "x",
      "rig-id": null,
      "nicehash": false,
      "keepalive": true,
      "enabled": true,
      "tls": false,
      "daemon": true,
      "daemon-poll-interval": 1000,
      "daemon-job-timeout": 15000
    }
  ]
}
EOF
then
  rm -f "$config_tmp" "$gateway_tmp"
  die "cannot write temporary miner configuration" || return $?
fi

if ! printf '%s\n' "$ENDPOINT" > "$gateway_tmp"; then
  rm -f "$config_tmp" "$gateway_tmp"
  die "cannot write temporary gateway state" || return $?
fi
if ! chmod 600 "$config_tmp" "$gateway_tmp"; then
  rm -f "$config_tmp" "$gateway_tmp"
  die "cannot protect generated configuration" || return $?
fi
if ! mv -f "$gateway_tmp" "$PACKAGE_DIR/.gateway"; then
  rm -f "$config_tmp" "$gateway_tmp"
  die "cannot install validated gateway state" || return $?
fi
if ! mv -f "$config_tmp" "$PACKAGE_DIR/config.json"; then
  rm -f "$config_tmp"
  die "cannot install generated miner configuration" || return $?
fi

printf 'coinrig-native: prepared locked rx/2 full-memory config for 32 threads\n'
