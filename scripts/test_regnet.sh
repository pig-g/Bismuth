#!/usr/bin/env sh
set -eu

CDPATH=''
export CDPATH
REPO_ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
if [ -z "${PYTHON:-}" ]; then
    if command -v python3.11 >/dev/null 2>&1; then
        PYTHON=python3.11
    elif command -v uv >/dev/null 2>&1 &&
        UV_PYTHON=$(uv python find 3.11 2>/dev/null); then
        PYTHON=$UV_PYTHON
    else
        PYTHON=python3
    fi
fi
VENV_DIR="$REPO_ROOT/.venv"

cd "$REPO_ROOT"
PYTHON_VERSION=$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [ "$PYTHON_VERSION" != "3.11" ]; then
    echo "Regnet tests require Python 3.11; '$PYTHON' is Python $PYTHON_VERSION." >&2
    echo "Install Python 3.11, then run: PYTHON=python3.11 ./scripts/test_regnet.sh" >&2
    exit 1
fi
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
