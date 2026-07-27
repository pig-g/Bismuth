# Lab 0: Regnet Quickstart

**Time:** 10–15 minutes

Use this guide to run Bismuth's isolated local regnet and write tests against it.
It requires no mainnet setup.

> **Safety:** Do not use real BIS, a mainnet wallet, or a mainnet ledger here.
> The test fixture binds to `127.0.0.1:3030`, creates temporary state and a
> temporary wallet, then removes them when pytest finishes.

## Prerequisites

- Linux or macOS
- Python 3.11 available as `python3`
- network access for the first dependency installation
- loopback port `3030` available

The runner clears and recreates the repository-local `.venv`. Do not keep
manually installed packages or irreplaceable files there.

## Verify regnet

From the repository root, run:

```bash
./labs/00-regnet-first-run/verify.sh
```

The verifier creates a clean environment, starts regnet, runs the tests, stops
the node, and confirms that port `3030` is closed. Success ends with:

```text
LAB 0 PASS
```

To run the same complete regnet test path directly:

```bash
./scripts/test_regnet.sh
```

Do not start the node manually for tests. The pytest fixture owns startup,
readiness, temporary files, and cleanup.

## Run regnet while developing

After the clean verifier has created `.venv`, Linux users can start a standalone
local regnet:

```bash
./scripts/regnet start
./scripts/regnet status
```

The start command prints the isolated wallet and log paths. Regnet remains on
`127.0.0.1:3030` until you stop it:

```bash
./scripts/regnet stop
```

Standalone state lives under the system temporary directory, never in the
repository or a mainnet wallet. `stop` verifies process ownership, uses bounded
SIGTERM/SIGKILL cleanup through a Linux pidfd, confirms port `3030` is closed,
and removes that state. On systems without pidfd support, `stop` refuses to
signal a PID rather than risk stopping an unrelated process. The standalone
three-command lifecycle is therefore Linux-only. On macOS, run the owned
cross-platform transaction session instead:

```bash
.venv/bin/python ./labs/01-test-bis-workflow/cli.py
# or the automatic round trip:
.venv/bin/python ./labs/01-test-bis-workflow/session.py
```

The operating-system account running these commands is the trust boundary.
Lifecycle locking protects concurrent `scripts/regnet` invocations; it does not
attempt to defend against another process with the same UID deliberately
rewriting its private runtime, because that process can already signal the node
and modify all files owned by the account.

## Write a regnet test

Add a test under `tests/` and request the session-scoped `myserver` fixture. Use
`get_client` to send RPC commands to the isolated node:

```python
from common import get_client


def test_my_regnet_command(myserver):
    client = get_client()
    result = client.command(command="portget")
    assert int(result["port"]) == 3030
```

For tests that need blocks or test funds, generate local regnet blocks:

```python
client.command(command="regtest_generate", options=[1])
```

Regnet blocks and balances have no mainnet value. All mutable regnet state remains
in a temporary directory outside the repository.

## Useful files

- `tests/conftest.py` — `myserver` lifecycle and readiness
- `tests/common.py` — `get_client`
- `tests/test_node.py` — RPC test examples
- `tests/test_ledger.py` — ledger query examples
- `tests/config_custom.txt` — regnet configuration

## Troubleshooting

- **`python3` missing:** set `PYTHON` to a Python 3.11 executable.
- **port 3030 already in use:** stop the unrelated listener and rerun.
- **dependency installation fails:** check package-index access.
- **node startup fails:** pytest prints the launch command and captured
  `node-output.log` contents before removing the temporary directory.
