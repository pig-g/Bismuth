#!/usr/bin/env sh
# Setup an isolated venv for the Mainnet Interaction Track only.
#
# Creates <repo>/.venv-mainnet with just the bismuthclient dependency needed
# by mainnet_cli.py. This is SEPARATE from the regnet .venv (Labs 0-8) so that
# the mainnet track can be run independently and never shares state that the
# regnet verifier recreates/clears.
#
# Usage:
#   ./labs/mainnet-interaction/setup_venv.sh
#
# Then run:
#   .venv-mainnet/bin/python ./labs/mainnet-interaction/mainnet_cli.py height

set -eu

CDPATH=''
export CDPATH
LAB_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(cd -- "$LAB_DIR/../.." && pwd)
VENV_DIR="$REPO_ROOT/.venv-mainnet"
PYTHON=${PYTHON:-python3}

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "error: Python executable not found: $PYTHON" >&2
    exit 1
fi

# 1. Create (or refresh) the isolated venv.
if [ -e "$VENV_DIR" ]; then
    if [ -f "$VENV_DIR/pyvenv.cfg" ]; then
        echo "[setup] refreshing existing venv at $VENV_DIR"
    else
        echo "[setup] removing stale non-venv directory at $VENV_DIR" >&2
        rm -rf "$VENV_DIR"
    fi
fi
echo "[setup] creating venv at $VENV_DIR"
"$PYTHON" -m venv --clear --upgrade-deps "$VENV_DIR"

# 2. Install the pinned mainnet-track dependency.
#    bismuthclient 0.0.53 (the version pinned/verified in the wiki plan) pulls
#    its own transitive deps (base58, coincurve, ed25519, polysign, PySocks, ...).
echo "[setup] installing bismuthclient==0.0.53 into $VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --quiet --upgrade "bismuthclient==0.0.53"

# 3. If the repo pins a bismuthclient, honour it; otherwise 0.0.53 is used.
if [ -f "$REPO_ROOT/requirements-mainnet.txt" ]; then
    echo "[setup] installing repo requirements-mainnet.txt"
    "$VENV_DIR/bin/python" -m pip install --quiet -r "$REPO_ROOT/requirements-mainnet.txt"
fi

# 4. Verify the import works.
if "$VENV_DIR/bin/python" -c 'import bismuthclient' 2>/dev/null; then
    echo "[setup] OK - bismuthclient importable."
else
    echo "[setup] WARNING: bismuthclient import failed." >&2
    exit 1
fi

echo
echo "Mainnet venv ready: $VENV_DIR"
echo "Run the track with:  .venv-mainnet/bin/python ./labs/mainnet-interaction/mainnet_cli.py height"
