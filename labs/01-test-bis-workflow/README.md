# Lab 1: Test BIS Transfer and Ledger Query

**Time:** 10–15 minutes

Use an isolated standalone regnet to generate test funds, transfer exactly one
test BIS, verify the recipient balance, inspect the confirmed transaction, and
find it in both the ledger and its block.

> **Safety:** Do not use real BIS, a mainnet wallet, or a mainnet ledger. This
> lab accepts only the owned standalone node on `127.0.0.1:3030`; its wallet and
> databases live under the system temporary directory and are removed by
> `stop`.

## Run the workflow

First complete [Lab 0](../00-regnet-first-run/README.md), which creates the
repository-local `.venv`. Then run these commands from the repository root:

```bash
./scripts/regnet start
.venv/bin/python ./labs/01-test-bis-workflow/run.py
./scripts/regnet stop
```

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
