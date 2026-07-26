# Lab 0 Instructor Guide

## Purpose and pacing

This 60–90 minute lab teaches diagnosis through a real infrastructure failure,
not merely how to run pytest.

- 0–10 min: incident framing and component boundary
- 10–30 min: startup contract and network mismatch
- 30–50 min: protocol-level readiness
- 50–80 min: live verifier, cleanup, and discussion
- 80–90 min: exit ticket and remediation review

Do not give the root cause before learners complete Checkpoint 2. If dependency
installation dominates class time, prepare a disposable Python 3.11 environment,
but still have learners run the same verifier.

## Shared root cause

The historical fixture launched `python3 node.py regnet2` and then used a fixed sleep.
The legacy positional value did not establish the complete network and filesystem
isolation contract. The node could remain on the default `mainnet0022` path and
port `5658`, while every BismuthClient test connected to regnet port `3030`.
Therefore `ConnectionRefusedError` across 26 tests was one startup failure fanning
out through a shared session fixture—not 26 independent application defects.

The repair is fail-closed and explicit:

```text
python node.py \
  --config-custom tests/config_custom.txt \
  --regnet-dir <temporary-directory> \
  --wallet-file <temporary-directory>/wallet.der \
  --bind 127.0.0.1 \
  --readiness-token <random-token>
```

## Checkpoint answers

### Checkpoint 1

The Core node owns the local regnet state and RPC listener. BismuthClient is the
caller used by tests. The flow is `pytest -> BismuthClient -> TCP 3030 -> Core
node`. A session-scoped fixture is shared, so failure before the listener becomes
ready prevents every dependent test from reaching its own assertion.

### Checkpoint 2

Expected values are version `regnet`, port `3030`, numeric loopback
`127.0.0.1`, a pytest-created temporary data directory outside the repository,
and a wallet inside that directory. Mainnet normally uses `5658`. Diagnose the
shared startup contract first: independently debugging test bodies would treat
fan-out symptoms as separate causes.

Current validation also rejects missing explicit config, public bind addresses,
wallets outside the temporary directory, and data directories overlapping the
repository. These are safety boundaries, not convenience flags.

### Checkpoint 3

A fixed sleep answers only “has time passed?” and is both too short on slow hosts
and wasteful on fast hosts. Process liveness and an open socket still do not prove
that the spawned process owns the expected listener.

The readiness sequence proves progressively more:

1. `portget` returns the effective RPC port `3030`;
2. `api_getconfig` reports the runtime configuration;
3. its `readiness_token` equals the random token passed to this process.

The token prevents accidentally accepting an unrelated service already listening
on the same port. The monotonic deadline is recalculated for connect, send, and
receive so several nominal one-second operations cannot silently exceed the total
startup budget. On failure, pytest prints the exact launch command and captured
`node-output.log`, turning a generic timeout into a diagnosable startup report.

### Checkpoint 4

`stop_regnet` terminates the process, waits, and escalates to kill after a bounded
timeout. `cleanup_regnet` uses nested `finally` blocks so output-handle close,
environment restoration, and temporary-directory removal continue even if process
cleanup fails. Preflight rejection of an occupied `3030` prevents the lab from
attaching to or disrupting a process it did not start.

Environmental failures happen before assertions and include missing Python,
package-index errors, an occupied port, or node startup output. Assertion failures
appear after the fixture is ready and identify a specific expected behavior.

## Expected verifier evidence

A successful run must end with all of the following:

- focused documentation and verifier acceptance tests pass;
- a real Core node answers `portget` and `api_getconfig` on loopback;
- the selected regnet tests pass;
- cleanup removes the temporary wallet, ledger, index, peers, logs, and process;
- a fresh connection attempt to `127.0.0.1:3030` is refused;
- final line: `LAB 0 PASS`.

If startup fails, have learners read the printed command and node output before
changing code. Do not bypass the ownership token, use a public bind, reuse a
mainnet wallet, or leave a manually started node running.

## Discussion prompts

1. Which other integration suites could misclassify fixture failure as many test failures?
2. When is a health endpoint insufficient to establish process ownership?
3. What should be temporary versus repository-tracked in a blockchain test network?
4. Which parts of this contract belong in CI, and which require an external learner?

## Exit-ticket rubric

A complete answer states that the node and client selected different effective
ports, that readiness is protocol evidence rather than elapsed time, that all
mutable state lives in a temporary directory with loopback-only binding, and that
post-run connection refusal demonstrates cleanup.
