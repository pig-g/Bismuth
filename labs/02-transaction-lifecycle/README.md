# Lab 2: Transaction Lifecycle and Block Explorer

**Time:** 10–15 minutes

Follow one locally signed transfer as it moves through Bismuth:

```text
mempool → unconfirmed transaction → confirmed block → ledger → balance
```

This lab adds no second application. Its runtime entrypoint is the safe
interactive CLI from Lab 1; this README is the learner entrypoint and guided
exercise.

> **Safety:** The CLI owns one temporary node on `127.0.0.1:3030`, two temporary
> wallets, and a temporary ledger. Use no real BIS, mainnet wallet, mainnet
> ledger, or remote node. Private keys stay local and are never displayed or
> sent to the node.

## Before you start

Complete [Lab 0](../00-regnet-first-run/README.md) once so the repository has
its `.venv`. Keep this README open in GitHub or a Markdown editor. Run the CLI
in a separate local macOS or Linux Terminal from the repository root:

```bash
.venv/bin/python ./labs/01-test-bis-workflow/cli.py
```

GitHub only renders these instructions. The Python process, temporary wallets,
ledger, and regnet node run on your own Mac or Linux computer. When startup is
ready, the Terminal shows:

```text
BISMUTH REGNET CLI
Owned local node: 127.0.0.1:3030 (no mainnet, no real BIS)
regnet>
```

If port `3030` is already occupied, the CLI fails closed and leaves that
listener untouched. Stop or identify the foreign listener yourself; do not
kill it through this lab.

## Run the lifecycle

Type the following commands one line at a time after the `regnet>` prompt. Do
not paste the prompt itself.

<!-- exercise:start -->
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
<!-- exercise:end -->

## What to observe

### 1. Create local funds and inspect the chain tip

`wallets` prints temporary Alice and Bob addresses. `mine 1` adds a local
reward-only block that funds Alice. `block last` displays that latest chain
tip; it does not mean "the block containing the last transfer."

### 2. Send without mining

`send alice bob 1` signs locally with Alice's temporary wallet and submits the
transfer. Record the printed transaction ID for the rest of the exercise.

The first `mempool` response contains that transaction. It is accepted by the
local node but is not yet part of a block or the confirmed ledger.

The first `tx last` and `block tx` deliberately stop immediately rather than
waiting on an RPC retry. Their messages include:

```text
last sent transaction is unconfirmed; run mine 1 first
```

This is the difference between **accepted** and **confirmed**.

### 3. Mine the confirmation block

The second `mine 1` creates a block containing the pending transfer. The next
`mempool` response no longer contains it because the transaction has moved
from pending state into the chain.

Now `tx last` shows the confirmed transaction, including its transaction ID,
sender, recipient, amount, and block height. `block tx` resolves that height
and displays the containing block.

### 4. Connect block history, ledger, and balance

`blocks 10` is the compact block explorer. Find both the normal Alice-to-Bob
transaction and the mining reward in recent history.

`balance bob` shows Bob's confirmed balance. `ledger bob 10` shows the address
history. Verify the same transaction ID across the earlier mempool entry,
`tx last`, `block tx`, and Bob's ledger entry.

`rpc api_getconfig` demonstrates the safe raw-RPC allowlist. Secret-like
configuration values, including the local ownership token, appear as
`[REDACTED]`.

## Command meanings

| Command | Question it answers |
|---|---|
| `block last` | What is the current chain tip? |
| `mempool` | Which transactions are accepted but not confirmed? |
| `tx last` | Is the most recently sent transaction confirmed, and at what height? |
| `block tx` | Which block contains the most recently sent transaction? |
| `blocks 10` | What rewards and normal transactions are in recent blocks? |
| `balance bob` | What confirmed balance does Bob have? |
| `ledger bob 10` | Which confirmed ledger entries affect Bob? |

## Completion checklist

You have completed Lab 2 when you can verify all of these from one session:

- the transfer first appears in `mempool`;
- `tx last` and `block tx` report it as unconfirmed before mining;
- after `mine 1`, the transfer disappears from `mempool`;
- `tx last` reports a confirmation height;
- `block tx` contains the normal Alice-to-Bob transfer;
- `blocks 10` distinguishes that transfer from its block reward;
- Bob's ledger and confirmed balance reflect the transfer;
- the same transaction ID connects the pending transaction, confirmed
  transaction, containing block, and ledger entry.

Finish with `quit`. Successful cleanup ends with:

```text
Regnet stopped; temporary wallets and ledger removed.
```

The same cleanup is attempted on EOF, errors, and Terminal interruption. On
macOS, use this direct-child CLI path rather than the Linux-only standalone
`./scripts/regnet start|status|stop` lifecycle.

## Next lab

A signing-identity lab can follow this same transaction from its locally built
signing buffer through public key, address, signature verification, and
Bismuth's signature-derived transaction ID. It should reuse this CLI session
rather than expose private keys or add remote signing.
