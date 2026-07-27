# Lab 1: Test BIS Transfer and Ledger Query

**Time:** 10–15 minutes

Use an isolated standalone regnet to generate test funds, transfer exactly one
test BIS, verify the recipient balance, inspect the confirmed transaction, and
find it in both the ledger and its block.

> **Safety:** Do not use real BIS, a mainnet wallet, or a mainnet ledger. This
> lab accepts only the owned standalone node on `127.0.0.1:3030`; its wallet and
> databases live under the system temporary directory and are removed by
> `stop`.

## Explore the regnet directly (Linux or macOS)

First complete [Lab 0](../00-regnet-first-run/README.md), which creates the
repository-local `.venv`. Start the interactive educational CLI from the
repository root:

```bash
.venv/bin/python ./labs/01-test-bis-workflow/cli.py
```

The app owns a temporary local node and two wallets for the entire console
session. Try this exercise one line at a time after the `regnet>` prompt:

```text
wallets
mine
block last
send alice bob 1
mempool
mine
balance bob
tx last
ledger bob 5
block last
block tx
blocks 10
rpc api_getconfig
help
quit
```

This lets learners directly execute safe Bismuth API commands and see their JSON
responses. `send` signs locally with the selected temporary wallet; key material
is never displayed or sent to the node. `quit`, EOF, interruption, and errors
stop the owned node and remove the wallets and ledger.

`block last` always shows the current chain tip, including a reward-only block.
`block tx` shows the block containing the most recently sent transaction, so run
`mine 1` (or `rpc regtest_generate 1`) after `send` first. If that transaction
is still in the mempool, the CLI returns immediately with an instruction instead
of waiting on the node. `blocks 10` is the compact local block-explorer view: it
lists recent heights, hashes, rewards, and included transactions. Use
`blocks <start> <count>` for a specific range.

The `rpc` command uses an explicit educational allowlist. Read/query commands
and `regtest_generate` are available; process control, key export, remote
signing, mainnet access, and destructive commands such as
`api_clearmempool` are blocked. The legacy repository `commands.py` does not
provide these safety boundaries and should not be used for this lab.
Allowed RPC arguments are type- and range-checked before transmission, so a
malformed address, identifier, height, limit, or confirmation count fails
immediately instead of waiting on a node-side handler.

## Run an automatic Alice/Bob round trip

For a complete demonstration without typing each command, run:

```bash
.venv/bin/python ./labs/01-test-bis-workflow/session.py
```

This is not a test-status-only command. It starts an isolated local node, creates
temporary Alice and Bob wallets, mines local funds, sends `1` test BIS from
Alice to Bob, sends `0.25` test BIS from Bob back to Alice, and prints both
transaction IDs, confirmation blocks, addresses, and final balances. The output
contains these lines with real values from that run:

```text
LOCAL REGNET SESSION PASS
Alice: <local address>
Bob: <local address>
Alice -> Bob: 1.00000000 test BIS
Alice transaction: <transaction ID>
Bob -> Alice: 0.25000000 test BIS
Bob transaction: <transaction ID>
Bob final balance: 0.73988000 test BIS
Local regnet stopped; temporary wallets and ledger removed.
```

No private key is printed. The command always stops the node and removes both
temporary wallets and the local ledger when it succeeds, fails, or is
interrupted.

## Keep the standalone regnet running (Linux only)

The separate lifecycle currently requires Linux `/proc` and pidfd ownership
checks. On Linux, use three commands when you want the node to remain running
between operations:

```bash
./scripts/regnet start
.venv/bin/python ./labs/01-test-bis-workflow/run.py
./scripts/regnet stop
```

Do not use this three-command path on macOS yet. Use `session.py` or `cli.py`;
each directly owns its node child and therefore provides bounded,
cross-platform cleanup without unsafe PID signalling.

The workflow discovers the wallet from ownership-verified standalone metadata;
you do not copy a wallet path or use a wallet from the repository. It creates a
fresh random recipient address for each run and prints no private key.

Success begins with:

```text
TEST BIS WORKFLOW PASS
```

It then prints the sender, recipient, transferred amount, recipient balance,
transaction ID, confirmation block, and block hash. All values exist only in
the temporary local regnet.

To execute the same lifecycle with automatic failure cleanup:

```bash
./labs/01-test-bis-workflow/verify.sh
```

## What the script does

1. `regtest_generate` mines one local funding block for the temporary wallet.
2. The client signs and submits a `1.00000000` test BIS transfer to a new random
   recipient.
3. `regtest_generate` mines one confirmation block.
4. `api_gettransaction` verifies the confirmed amount and recipient.
5. `balancegetjson` proves the recipient owns exactly `1.00000000` test BIS.
6. `addlistlimjson` locates the transaction in the address ledger.
7. `api_getblockfromheight` proves the same transaction is in its confirmation
   block.

The script fails instead of reporting success if any semantic check disagrees.
An `OK` mining acknowledgement alone is not accepted as proof of the transfer.

## Explore in a pytest test

The same primitives are available through the existing fixture:

```python
from common import get_client


def test_test_bis_transfer(myserver):
    client = get_client()
    client.command(command="regtest_generate", options=[1])
    txid = client.send(recipient="f" * 56, amount=1.0)
    client.command(command="regtest_generate", options=[1])
    transaction = client.command(
        command="api_gettransaction", options=[txid, True]
    )
    assert transaction["txid"] == txid
```

Use only generated regnet balances. Do not substitute a mainnet endpoint,
wallet, address with real funds, or ledger.

## Cleanup and troubleshooting

- Always run `./scripts/regnet stop`, including after workflow failure.
- `verify.sh` traps failures, stops only the ownership-verified node, and checks
  that port `3030` is closed.
- If the workflow says standalone regnet is not running, run
  `./scripts/regnet start` first.
- If port `3030` is already occupied, do not kill the listener through this lab;
  identify and stop it separately.
