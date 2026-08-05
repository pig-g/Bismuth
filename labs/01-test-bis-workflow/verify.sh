#!/usr/bin/env sh
set -u

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/../.." && pwd)
REGNET=${LAB1_REGNET:-"$REPO_ROOT/scripts/regnet"}
WORKFLOW=${LAB1_WORKFLOW:-"$SCRIPT_DIR/run.py"}
REGNET_PORT=${LAB1_REGNET_PORT:-3030}
PYTHON=${PYTHON:-"$REPO_ROOT/.venv/bin/python"}
SCRIPT_INTERPRETER=${LAB1_SCRIPT_INTERPRETER:-}
started=0
workflow_pid=

run_script() {
    if [ -n "$SCRIPT_INTERPRETER" ]; then
        "$SCRIPT_INTERPRETER" "$@"
    else
        "$@"
    fi
}

run_regnet() {
    run_script "$REGNET" "$@"
}

start_workflow() {
    if [ -n "$SCRIPT_INTERPRETER" ]; then
        "$SCRIPT_INTERPRETER" "$WORKFLOW" &
    else
        "$PYTHON" "$WORKFLOW" &
    fi
    workflow_pid=$!
}

port_is_closed() {
    "$PYTHON" - "$REGNET_PORT" <<'PY'
import socket
import sys

with socket.socket() as probe:
    probe.settimeout(0.25)
    raise SystemExit(probe.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0)
PY
}

cleanup_on_exit() {
    if [ -n "$workflow_pid" ]; then
        kill -TERM "$workflow_pid" 2>/dev/null || true
        wait "$workflow_pid" 2>/dev/null || true
        workflow_pid=
    fi
    if [ "$started" -eq 1 ]; then
        run_regnet stop >/dev/null 2>&1 || true
    fi
}

handle_signal() {
    signal_status=$1
    trap - EXIT HUP INT TERM
    cleanup_on_exit
    exit "$signal_status"
}

trap cleanup_on_exit EXIT
trap 'handle_signal 129' HUP
trap 'handle_signal 130' INT
trap 'handle_signal 143' TERM

if ! port_is_closed; then
    echo "Lab 1: port $REGNET_PORT is already in use; refusing to start" >&2
    exit 1
fi

started=1
if ! run_regnet start; then
    started=0
    echo "Lab 1: regnet start failed" >&2
    exit 1
fi

workflow_status=0
start_workflow
wait "$workflow_pid" || workflow_status=$?
workflow_pid=

stop_status=0
run_regnet stop || stop_status=$?
if [ "$stop_status" -eq 0 ]; then
    started=0
fi

if ! port_is_closed; then
    echo "Lab 1 cleanup failed: port $REGNET_PORT still has a listener" >&2
    exit 1
fi
echo "Lab 1 cleanup: port $REGNET_PORT is closed"

if [ "$workflow_status" -ne 0 ]; then
    exit "$workflow_status"
fi
if [ "$stop_status" -ne 0 ]; then
    echo "Lab 1: regnet stop failed" >&2
    exit "$stop_status"
fi

echo "LAB 1 PASS"
