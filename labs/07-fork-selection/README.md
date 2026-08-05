# Lab 7: Fork and Chain-Consensus Rules

Walk through the concrete rules a Bismuth node applies at a hard fork — which protocol versions stop being accepted, and how it verifies the post-fork reward — using a deterministic script against synthetic fixtures.

- **Time:** about 5 minutes
- **Guide:** read this page in GitHub or a Markdown editor
- **Runtime:** a read-only Python script from a local macOS or Linux Terminal

## The key idea

A software like Bismuth grows through hard forks. To upgrade the network without everyone upgrading at the same second, nodes agree on a **fork height** and begin enforcing new rules there. The `Fork` class in `node/fork.py` holds those constants and the checks:

```python
self.POW_FORK = 1450000                      # height where the fork activates
self.FORK_AHEAD = 5                          # block to start enforcing the version gate
self.versions_remove = ['mainnet0020', ...]  # protocol versions no longer accepted
self.REWARD_MAX = 6                          # post-fork reward cap
```

> **Safety:** this lab is fully read-only. It instantiates the `Fork` class and runs deterministic in-memory checks. It starts no node, opens no port, touches no database file, holds no keys, and has no mainnet connection.

## 1. Run the demo

From the repository root, after completing [Lab 0](../00-regnet-first-run/README.md) once so `.venv` exists:

```bash
.venv/bin/python ./labs/07-fork-selection/fork_demo.py
```

## 2. Read the result

### 1. Protocol version gating

The demo starts a fake node that accepts `mainnet0023`, `mainnet0020`, and `mainnet0019`, then calls `fork.limit_version(node)`:

```text
node accepts before: ['mainnet0023', 'mainnet0020', 'mainnet0019']
node accepts after:  ['mainnet0023', 'mainnet0019']
removal log entries: 1
```

Verify that `mainnet0020` (one of the versions in `versions_remove`) was removed from the allowed list while the current `mainnet0023` stayed. In production this is how old nodes are gradually cut off at the fork.

### 2. Post-fork reward check

`check_postfork_reward` reads the reward at `POW_FORK + 1` and compares it to the cap:

```text
reward=5  (< cap 6):  passed=True
reward=10 (>= cap 6): passed=False
```

A reward **below** the cap (`REWARD_MAX`) confirms the fork is behaving; a reward **at or above** the cap flags a problem.

### 3. Fail-safe on a database error

```text
reward=db-error:  passed=True  fork_passed=True
```

If the database read fails, `fork.py` **assumes the fork passed** rather than freezing or rejecting the chain. This is a deliberate fail-safe: a transient read problem must never wedge the node.

## Reading the real code

Open `node/fork.py`. The version gate is in `limit_version` (it walks `node.version_allow` and drops anything listed in `versions_remove`). The reward check is in `check_postfork_reward`, which tries memory first, falls back to the on-disk handle, and only sets `PASSED` based on `FORK_REWARD < REWARD_MAX`. `check_postfork_reward_testnet` mirrors it for `POW_FORK_TESTNET = 894170`.

## Clean up

Nothing to stop: the demo is a short-lived read-only process and leaves no files, node, wallet, or port behind.

## What you learned

```text
Bismuth hard forks activate at a fixed height (POW_FORK)
-> at the fork, nodes stop accepting the removed protocol versions
-> a post-fork reward below REWARD_MAX confirms the fork
-> on a database error the node assume-the-best (fail-safe)
-> this is how rule changes propagate without everyone upgrading at once
```

Lab 5 showed how a block is stored; Lab 6 showed how difficulty steers block time. This lab shows the third piece of chain growth: the explicit rules that let the network change protocol versions at a chosen height.
