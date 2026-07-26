#!/usr/bin/env sh
set -eu

CDPATH=''
export CDPATH
REPO_ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON=${PYTHON:-python3}
VENV_DIR="$REPO_ROOT/.venv"

cd "$REPO_ROOT"
if [ -L "$VENV_DIR" ]; then
    echo "Refusing to clear symlinked virtualenv: $VENV_DIR" >&2
    exit 1
fi
if [ -e "$VENV_DIR" ] && [ ! -f "$VENV_DIR/pyvenv.cfg" ]; then
    echo "Refusing to clear non-virtualenv directory: $VENV_DIR" >&2
    exit 1
fi
"$PYTHON" -m venv --clear "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install -r tests/requirements.txt
exec "$VENV_DIR/bin/python" -m pytest tests -q
