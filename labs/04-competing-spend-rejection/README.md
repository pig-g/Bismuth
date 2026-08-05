# Lab 4: Competing Spend Rejection

Observe how Bismuth's account-based mempool reserves pending debits and rejects a second locally signed spend that would exceed the sender's remaining spendable balance.

- **Time:** about 10 minutes
- **Guide:** read this page in GitHub or a Markdown editor
- **Runtime:** run the existing Lab 1 CLI in a local macOS or Linux Terminal

## What this lab means by competing spend

Bismuth uses an **account model**, not a UTXO model. There is no named coin output consumed by two transactions. Therefore this lab does not claim to reproduce Bitcoin-style same-UTXO double spending.

Instead, Alice creates two different, valid local signatures. Each requests a 10 test BIS transfer from the same confirmed account balance. The first transaction enters the mempool. The second transaction then competes for funds already reserved by the pending first transaction and is rejected.

An exact duplicate signature follows a different `mempool_in` duplicate path. This exercise targets pending-balance contention through `debit_mempool`.

## Safety boundary

The CLI starts an owned node only on `127.0.0.1:3030`. It uses generated temporary wallets, temporary SQLite state, and test BIS. It has no mainnet connection, no remote fallback, and no real BIS.

Both private keys remain local. They are never printed or sent through node RPC. The learner uses the normal client-side `send` command; no raw transaction insertion, destructive RPC, or process-control RPC is exposed.

## 1. Start the existing CLI

From the repository root:

```bash
.venv/bin/python ./labs/01-test-bis-workflow/cli.py
```

Wait for the `regnet>` prompt.

## 2. Create wallets and fund Alice

```text
wallets
```

Generate one local reward block:

```text
mine 1
```

Read Alice's confirmed balance:

```text
balance alice
```

In the pinned regnet exercise, Alice has enough confirmed test BIS for either individual 10 BIS transfer, but not enough for both transfers plus fees.

## 3. Submit the first transaction

```text
send alice bob 10
```

This transaction is signed locally and accepted. Record the printed transaction ID.

Inspect the pending state:

```text
mempool
```

The structured response contains one row with the first transaction's txid. No balance has been confirmed for Bob yet.

## 4. Attempt the competing spend

```text
send alice bob 10
```

The second transaction has a different timestamp and signature, but it spends from the same Alice account while the first debit is pending. Expected rejection includes:

```text
Mempool: Cannot afford to pay fees
error: transaction was rejected
```

The check is not merely `amount <= confirmed balance`. In `mempool.py`, the node adds existing pending amounts and their fees to `debit_mempool`, then verifies that the new amount and fee still fit the remaining balance.

Confirm that rejection did not add another row:

```text
mempool
```

The same first transaction remains the only pending learner transfer.

Confirm that a failed `send` did not overwrite the CLI's last transaction identity:

```text
tx last
```

Because the first transaction is still pending, the CLI responds:

```text
last transaction is unconfirmed; run mine 1 first
```

## 5. Confirm only the accepted transaction

```text
mine 1
```

The pending mempool should now be empty:

```text
mempool
```

Query the transaction that survived the competing attempt:

```text
tx last
```

It resolves to the same txid printed by the first successful `send`.

Check Bob's confirmed balance:

```text
balance bob
```

Expected learner transfer balance:

```text
10.00000000 test BIS
```

Finally, inspect Bob's ledger:

```text
ledger bob 10
```

The ledger contains one confirmed transfer from Alice, not two. This is **one confirmed transfer** because the competing second spend never entered the mempool.

## 6. Clean up

```text
quit
```

The supervisor terminates its owned child node, waits for port `3030` to close, and removes the wallets, ledger, logs, and temporary directory.

## What you learned

```text
confirmed account balance
→ first transaction accepted
→ pending debit reserved in mempool
→ second valid signature competes for reserved funds
→ second transaction rejected
→ first transaction remains last
→ mine
→ one confirmed transfer
```

Lab 4 demonstrates account-model pending-balance protection. It does not prove that every possible network race or consensus-level replay is prevented; those require separate multi-peer and adversarial experiments.
