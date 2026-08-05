# Lab 8: Tokens Without a VM

See how Bismuth supports tokens with no virtual machine. A token is not a separate contract — it is simply transactions labelled with a special operation, and an index table is rebuilt from those rows. This lab runs a small model of that accounting against an ephemeral SQLite database.

- **Time:** about 5 minutes
- **Guide:** read this page in GitHub or a Markdown editor
- **Runtime:** a read-only Python script from a local macOS or Linux Terminal

## The key idea

Bismuth puts token behaviour inside ordinary transactions using two special `operation` values, with the amount encoded in `openfield` as `token_name:amount`:

```text
operation = token:issue      openfield = token_name:total_number
operation = token:transfer   openfield = token_name:amount
```

Because every transaction is signed and confirmed like any other, a token "contract" needs no execution environment. A separate index pass (`node/tokensv2.py`) walks the confirmed transactions and rebuilds token balances into a `tokens` table:

```text
confirmed transactions (operation = token:*)
        |
tokens_update() reindexes
        v
tokens table (block_height, token, address, recipient, txid, amount)
        |
balance of each holder = credits(as recipient) - debits(as sender)
```

> **Safety:** this lab is fully read-only and self-contained. It builds a temporary SQLite database in a temporary directory that is created and deleted inside the same run. It starts no node, opens no port, leaves no persistent file, holds no keys, and has no mainnet connection.

## 1. Run the demo

From the repository root, after completing [Lab 0](../00-regnet-first-run/README.md) once so `.venv` exists:

```bash
.venv/bin/python ./labs/08-tokens-no-vm/tokens_demo.py
```

## 2. What happens

The demo creates an ephemeral chain with one token issue and several transfers:

```text
issue:      worthless:1000              -> a (the issuer)
transfers:  a->b 100, b->c 40, a->c 60  (all valid)
            c->z 9999                   (rejected - c holds only 100)
```

The reindex rebuilds the `tokens` table and prints each holder's net balance:

```text
balance a ... = 840     (1000 - 100 - 60)
balance b ... = 60      (100 - 40)
balance c ... = 100     (40 + 60)
reindex balance check: OK
```

Verify:

1. **a** issued 1000, sent 100 to b and 60 to c, so it holds **840**.
2. **b** received 100 from a and sent 40 to c, so it holds **60**.
3. **c** received 40 and 60, so it holds **100**.
4. The `c->z 9999` transfer is rejected because **c** holds only 100 tokens — the sender's balance is checked before the transfer is recorded.

## Reading the real code

Open `node/tokensv2.py`. The `tokens_update` function:

1. creates the `tokens` index table if needed;
2. scans confirmed `token:issue` transactions (first column of `openfield` = token name, second = total) and inserts one row per issuance;
3. scans confirmed `token:transfer` transactions, and for each computes the sender's current balance (`credit_sender - debit_sender`);
4. only records a transfer when `balance_sender - transfer_amount >= 0`; otherwise it records an empty marker row so the invalid transaction is not re-scanned;
5. commits once at the end — the whole table can be rebuilt from the same confirmed rows, which is what makes reindex deterministic.

Note the real module uses `blake2bhash_generate` to derive a txid for entries whose signature is the literal `"0"`; this demo assumes real signatures and uses `signature[:56]` like the rest of the labs.

## Clean up

Nothing to stop: the demo creates a temporary directory and deletes it inside the same run. It leaves no node, wallet, ledger, port, or file behind.

## What you learned

```text
a token is just transactions tagged token:issue / token:transfer
-> amount is encoded in openfield as token_name:amount
-> balancing needs a VM only as a signed, confirmed transaction
-> an index table is rebuilt from the confirmed rows (deterministic reindex)
-> a transfer is rejected when the sender does not hold enough tokens
```

Lab 5 mapped a block to its rows; Lab 6 showed difficulty steering block time; Lab 7 showed fork rule changes. This lab shows a higher-level concept — a token — implemented purely on top of the same signed-transaction substrate, with no VM.
