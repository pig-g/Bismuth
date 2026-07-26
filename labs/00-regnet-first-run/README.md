# Lab 0: Regnet First Run and Shared-Failure Diagnosis

**Time:** 60–90 minutes
**Level:** Python developer who can use a terminal and read a pytest failure

> **Safety:** Do not use real BIS, a mainnet wallet, or a mainnet ledger in this lab.
> The supplied runner binds only to `127.0.0.1`, uses a temporary data directory
> and wallet, and removes them after the tests finish.

## The incident

An earlier test fixture started `python3 node.py regnet2`, slept for ten seconds,
and then ran 26 integration tests. All 26 failed with connection errors. The
failures looked broad, but they had one shared cause: the Core node stayed on its
mainnet startup path while the tests connected to the regnet port.

This lab turns that incident into a repeatable diagnosis exercise.

## Learning objectives

By the end you will be able to:

1. distinguish the **Core node** process from the **BismuthClient** RPC caller;
2. explain why mainnet port `5658` and regnet port `3030` must not be mixed;
3. identify one startup-contract error that creates many downstream failures;
4. explain why **RPC readiness** is stronger than a fixed sleep;
5. identify the temporary data directory, wallet, ledger, peers, and logs used by the test node;
6. verify that the listener is owned by this runner, bound to `127.0.0.1`, and cleaned up.

## Prerequisites

- Linux or macOS shell with Python 3.11 available as `python3`
- a fresh clone or clean checkout of this branch
- network access for the first dependency installation
- port `3030` free on loopback

Do not start a node manually. The verifier owns the process lifecycle.
The verifier clears and recreates the repository-local `.venv`; do not keep
manually installed packages or other irreplaceable files there.

## Repository map

- `node.py` — Core node entry point
- `node_cli.py` — startup argument parsing and isolation validation
- `tests/config_custom.txt` — explicit regnet configuration
- `tests/conftest.py` — isolated node lifecycle and RPC readiness probe
- `scripts/test_regnet.sh` — clean virtualenv plus complete test suite
- `tests/test_regnet_runtime.py` — executable safety contract

## Run the lab

From the repository root:

```bash
./labs/00-regnet-first-run/verify.sh
```

The command performs preflight checks, runs the focused Lab 0 acceptance tests,
executes the real regnet integration path, and confirms that port `3030` is
closed afterward. A successful run ends with `LAB 0 PASS`.

Then work through [exercise.md](exercise.md). Record short answers before reading
[instructor.md](instructor.md), which contains the diagnosis and discussion guide.

## What success proves—and what it does not

A pass proves that this checkout can launch an isolated local regnet, observe it
through RPC, run the selected tests, and clean up. It does **not** prove mainnet
correctness, authorize a mainnet transaction, or make test BIS valuable.

## Troubleshooting

- **`python3` missing:** set `PYTHON` to a Python 3.11 executable.
- **port 3030 already in use:** stop the unrelated listener; the verifier fails
  closed rather than attaching to it.
- **dependency installation fails:** check network/package-index access and rerun.
- **node startup fails:** inspect the node output printed by pytest. The fixture
  includes the exact command and captured output in the failure.
