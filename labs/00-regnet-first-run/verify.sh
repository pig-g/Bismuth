#!/usr/bin/env sh
set -eu

CDPATH=''
export CDPATH
LAB_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(cd -- "$LAB_DIR/../.." && pwd)
PYTHON=${PYTHON:-python3}
REGNET_RUNNER=${LAB0_REGNET_RUNNER:-"$REPO_ROOT/scripts/test_regnet.sh"}
REGNET_PORT=3030
if [ -n "${LAB0_REGNET_RUNNER:-}" ]; then
    REGNET_PORT=${LAB0_REGNET_PORT:-3030}
fi

port_is_closed() {
    "$PYTHON" -c 'import socket, sys
s = socket.socket()
s.settimeout(0.5)
status = s.connect_ex(("127.0.0.1", int(sys.argv[1])))
s.close()
sys.exit(0 if status != 0 else 1)' "$REGNET_PORT"
}

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Lab 0 preflight failed: Python executable not found: $PYTHON" >&2
    exit 1
fi
if [ ! -f "$REGNET_RUNNER" ]; then
    echo "Lab 0 preflight failed: regnet runner not found: $REGNET_RUNNER" >&2
    exit 1
fi
if ! port_is_closed; then
    echo "Lab 0 preflight failed: port $REGNET_PORT is already in use" >&2
    exit 1
fi

echo "[Lab 0] preflight: port $REGNET_PORT is closed"
echo "[Lab 0] running isolated regnet acceptance path"
runner_status=0
PYTHON="$PYTHON" sh "$REGNET_RUNNER" || runner_status=$?

if ! port_is_closed; then
    echo "Lab 0 cleanup failed: port $REGNET_PORT still has a listener" >&2
    exit 1
fi

echo "[Lab 0] cleanup: port $REGNET_PORT is closed"
if [ "$runner_status" -ne 0 ]; then
    echo "Lab 0 runner failed with status $runner_status" >&2
    exit "$runner_status"
fi

echo "LAB 0 PASS"
