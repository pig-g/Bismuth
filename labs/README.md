# Bismuth Labs 0–8: Download and Run

This is the newcomer entrypoint for the practical Bismuth learning labs. It starts with downloading the correct GitHub branch, creates an isolated Python environment, and shows exactly how to run Labs 0 through 8 on macOS or Linux.

No existing Bismuth installation, wallet, BIS balance, Docker container, or mainnet node is required.

> **Safety:** Labs 0–8 use only an owned local regnet on `127.0.0.1:3030` (Labs 0–5) or short-lived read-only simulation scripts (Labs 6–8). Labs 0–5 use generated temporary wallets and valueless test BIS; Labs 6–8 are pure arithmetic/deterministic checks that start no node. There is no mainnet connection or remote fallback. A private key is never printed or sent to the node. Leaving the CLI with `quit` deletes the local node, wallets, and ledger.

## What you will learn

| Lab | Main question | Time |
|---|---|---:|
| [Lab 0](00-regnet-first-run/README.md) | Can I start and cleanly stop an isolated Bismuth regnet? | 10–15 min |
| [Lab 1](01-test-bis-workflow/README.md) | Can Alice send test BIS to Bob and inspect the result? | 10–15 min |
| [Lab 2](02-transaction-lifecycle/README.md) | How does a transaction move from mempool to block and ledger? | 10–15 min |
| [Lab 2.1](02-1-sqlite-state-trace/README.md) | When does a pending transaction become a SQLite row? | 10 min |
| [Lab 3](03-signing-identity/README.md) | How do key, address, signature, and txid bind together? | 10 min |
| [Lab 4](04-competing-spend-rejection/README.md) | How does the account-model mempool reserve pending funds? | 10 min |
| [Lab 5](05-block-sqlite-structure/README.md) | How is one block represented by SQLite transaction rows? | 10 min |
| [Lab 6](06-difficulty-simulation/README.md) | How does difficulty steer block time? | 5 min |
| [Lab 7](07-fork-selection/README.md) | What rules does a node apply at a hard fork? | 5 min |
| [Lab 8](08-tokens-no-vm/README.md) | How are tokens built with no VM? | 5 min |

Run them in that order. Lab 2.1 is a short bridge between Labs 2 and 3. Labs 6–8 are short read-only simulations: Lab 6 shows the difficulty feedback controller, Lab 7 walks the `Fork` consensus rules, and Lab 8 models token issue/transfer/reindex.

## 1. Prerequisites

You need:

- macOS or Linux;
- Python 3.11;
- Git, or a browser and an unzip tool;
- internet access for the first dependency installation;
- local loopback port `3030` available.

Check Python in a Terminal:

```bash
python3.11 --version
```

The result must begin with `Python 3.11`. If the command is missing, install Python 3.11 from [python.org](https://www.python.org/downloads/) or your operating system's package manager. On macOS with Homebrew:

```bash
brew install python@3.11
```

These labs are command-line exercises. GitHub displays the guides, but the node and Python commands run in a local **Terminal** on your own Mac or Linux computer.

## 2. Download the correct GitHub branch

Until the lab pull request is merged, use the `hermes/lab-1-test-bis-workflow` branch of `pig-g/Bismuth`. Do not download a different branch and expect these lab paths to exist.

### Option A — Git clone (recommended)

In a Terminal, choose a folder where you keep projects and run:

```bash
git clone --branch hermes/lab-1-test-bis-workflow --single-branch https://github.com/pig-g/Bismuth.git
cd Bismuth
```

Verify the branch:

```bash
git branch --show-current
```

Expected:

```text
hermes/lab-1-test-bis-workflow
```

### Option B — Download ZIP

1. Open [the lab branch on GitHub](https://github.com/pig-g/Bismuth/tree/hermes/lab-1-test-bis-workflow).
2. Click the green **Code** button.
3. Click **Download ZIP**.
4. Extract `Bismuth-hermes-lab-1-test-bis-workflow.zip`.
5. Open a Terminal in the extracted `Bismuth-hermes-lab-1-test-bis-workflow` folder.

For example, if your browser saved it in `Downloads`:

```bash
cd ~/Downloads
unzip Bismuth-hermes-lab-1-test-bis-workflow.zip
cd Bismuth-hermes-lab-1-test-bis-workflow
```

All commands below assume the Terminal is at the repository root—the folder containing `node.py`, `tests`, and `labs`.

## 3. One-time setup and Lab 0

Make sure nothing else is listening on port `3030`. Then run the verified clean setup:

```bash
PYTHON=python3.11 ./labs/00-regnet-first-run/verify.sh
```

If a ZIP extraction did not preserve executable permissions, use:

```bash
PYTHON=python3.11 sh ./labs/00-regnet-first-run/verify.sh
```

The verifier:

1. checks that port `3030` is free;
2. clears and recreates the repository-local `.venv`;
3. installs the pinned learning dependencies;
4. runs the isolated regnet tests;
5. stops its owned node and checks cleanup.

The first run requires network access and may take a few minutes. Success ends with:

```text
LAB 0 PASS
```

Do not store personal files in `.venv`; the verifier intentionally recreates it.

## 4. Understand the two command locations

There are two different prompts in these guides.

### Local Terminal

Run the Python application from the repository root:

```bash
.venv/bin/python ./labs/01-test-bis-workflow/cli.py
```

Wait until you see:

```text
BISMUTH REGNET CLI
Owned local node: 127.0.0.1:3030 (no mainnet, no real BIS)
regnet>
```

### `regnet>` prompt

Commands such as `wallets`, `mine 1`, and `send alice bob 1` are typed inside the running CLI after `regnet>`. Do not type `regnet>` itself.

Finish every exercise with:

```text
quit
```

Wait for:

```text
Regnet stopped; temporary wallets and ledger removed.
```

Start a fresh CLI session for each lab. Each session creates new wallets and a new empty chain, so values from an earlier session do not carry over.

## 5. Lab 1 — Test BIS workflow

Read the [full Lab 1 guide](01-test-bis-workflow/README.md). For an automatic demonstration, run in the local Terminal:

```bash
.venv/bin/python ./labs/01-test-bis-workflow/session.py
```

For the interactive exercise, start `cli.py`, then type:

```text
wallets
mine 1
send alice bob 1
mempool
mine 1
balance bob
tx last
ledger bob 5
block tx
quit
```

Observe the generated addresses, transaction ID, confirmed block, Bob's balance, and cleanup. The displayed BIS is local test BIS only.

## 6. Lab 2 — Transaction lifecycle

Read the [full Lab 2 guide](02-transaction-lifecycle/README.md). Start a fresh `cli.py`, then type:

```text
wallets
mine 1
block last
send alice bob 1
mempool
tx last
block tx
mine 1
mempool
tx last
block tx
blocks 10
balance bob
ledger bob 10
rpc api_getconfig
quit
```

Before the second `mine 1`, the transaction is pending. After mining, it leaves the mempool and appears in its containing block and Bob's ledger.

## 7. Lab 2.1 — SQLite persistence boundary

Read the [full Lab 2.1 guide](02-1-sqlite-state-trace/README.md). Start a fresh `cli.py`, then type:

```text
wallets
mine 1
send alice bob 1
mempool
sqltx last
mine 1
mempool
sqltx last
quit
```

The first `sqltx last` reports no SQLite row. The second reports the confirmed row for the same transaction ID.

## 8. Lab 3 — Signing identity

Read the [full Lab 3 guide](03-signing-identity/README.md). Start a fresh `cli.py`, then type:

```text
wallets
mine 1
send alice bob 1
mine 1
identity last
quit
```

Verify that the original signature, public-key/address binding, signature-derived transaction ID, and local tampering rejection are all `true`. No private key or tampered transaction is transmitted.

## 9. Lab 4 — Competing spend rejection

Read the [full Lab 4 guide](04-competing-spend-rejection/README.md). Start a fresh `cli.py`, then type:

```text
wallets
mine 1
balance alice
send alice bob 10
mempool
send alice bob 10
mempool
tx last
mine 1
mempool
tx last
balance bob
ledger bob 10
quit
```

The first distinct transaction is accepted. The second distinct transaction competes for the pending account balance and is rejected. Only the first transfer confirms.

## 10. Lab 5 — Block-to-SQLite structure

Read the [full Lab 5 guide](05-block-sqlite-structure/README.md). Start a fresh `cli.py`, then type:

```text
wallets
mine 1
send alice bob 1
mine 1
sqlblock tx
quit
```

Confirm that:

- RPC and SQLite report the same block height and block hash;
- the block has a normal user transaction row and a mining reward row;
- the `misc` table supplies difficulty for the same height;
- RPC and SQLite contain the same user transaction IDs;
- the selected transaction occurs exactly once in both views;
- `rpc_matches_sqlite` is `true`.

`sqlblock tx` performs the RPC comparison internally and prints only the safe
educational block mapping; it does not print the full transaction signature or
public key.

## 11. Troubleshooting

### `Python 3.11` is required

Run Lab 0 with an explicit interpreter:

```bash
PYTHON=python3.11 ./labs/00-regnet-first-run/verify.sh
```

### Port 3030 is occupied

The labs fail closed and do not kill or modify an existing listener. Stop the application that owns the port yourself, then rerun. Do not use the learner CLI to terminate an unknown process.

### `Permission denied` on a shell script

Run it through `sh`:

```bash
PYTHON=python3.11 sh ./labs/00-regnet-first-run/verify.sh
```

### A CLI command says the transaction is unconfirmed

Run:

```text
mine 1
```

Then retry the query.

### The Terminal was closed or interrupted

The direct-child CLI attempts bounded cleanup on EOF, `HUP`, `INT`, and `TERM`. Before restarting, make sure no old learner Terminal is still running. If port `3030` remains occupied, identify its owner rather than killing it through the lab.

### macOS lifecycle note

Use `cli.py` or `session.py` on macOS. The persistent `./scripts/regnet start|status|stop` lifecycle relies on Linux `/proc` and pidfd ownership checks and is not the macOS learner path.

## Completion

You have completed Labs 0–5 when you can explain this chain:

```text
owned regnet
→ temporary wallets and local signing
→ pending transaction in mempool
→ confirmed transaction in SQLite
→ signature-derived transaction identity
→ pending account debit protection
→ block represented by transaction rows plus difficulty metadata
```

All writable and adversarial exercises stay on owned regnet. The next curriculum stage uses a separate, explicit read-only client to observe the actual Bismuth mainnet; it must never be an implicit fallback from this local CLI.
