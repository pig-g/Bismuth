# Lab 5: Block-to-SQLite Structure

Follow one confirmed local transaction into its containing block, then compare the node's RPC block view with the exact rows stored in the owned temporary SQLite ledger.

- **Time:** about 10 minutes
- **Guide:** read this page in GitHub or a Markdown editor
- **Runtime:** run the existing Lab 1 CLI in a local macOS or Linux Terminal

## The key idea

Bismuth does not store a block as one row in a separate `blocks` table. A block is represented by the rows in the `transactions` table that share the same `block_height` and the same `block_hash`.

```text
block at height H
├── user transaction row(s)   transactions.block_height = H
├── mining reward row         transactions.block_height = H
└── difficulty row            misc.block_height = H
```

The node's RPC view groups those transaction rows into a JSON block. This lab proves that both views describe the same block.

## Safety boundary

This lab starts one owned node only on `127.0.0.1:3030`. It uses generated temporary wallets, test BIS, and `regmode.db` inside an owned temporary directory. It has no mainnet connection, no remote fallback, and no real BIS.

`sqlblock` is **not an arbitrary SQL** console. It opens only the current session's temporary ledger in read-only mode. The learner can provide only `tx` or a positive block height. The implementation uses parameterized queries against the `transactions` and `misc` tables; it accepts neither a database path nor SQL text.

Private keys stay local, are never printed, and are never sent through node RPC. `quit` removes the node, wallets, ledger, and the complete temporary directory.

## 1. Start the existing CLI

First complete [Lab 0](../00-regnet-first-run/README.md) once so the repository has its `.venv`. From the repository root, run:

```bash
.venv/bin/python ./labs/01-test-bis-workflow/cli.py
```

Wait for the `regnet>` prompt. Type the commands below without copying the prompt itself.

## 2. Create a transaction and its block

<!-- exercise:start -->
```text
wallets
mine 1
send alice bob 1
mine 1
sqlblock tx
quit
```
<!-- exercise:end -->

### `wallets`

The CLI creates temporary Alice and Bob identities. Their addresses are public for this local session; their private keys are not displayed.

### `mine 1`

The first local block funds Alice with test BIS. Regnet rewards have no mainnet value.

### `send alice bob 1`

Alice signs one transaction locally. Record the printed transaction ID. It identifies the user transaction, not the containing block.

### The second `mine 1`

This confirms Alice's transaction and adds a mining reward row to the same block.

## 3. Compare RPC and SQLite safely

```text
sqlblock tx
```

The command resolves the last transaction's confirmation height, calls `api_getblockfromheight`, and compares that RPC block with SQLite. It does not print the RPC transaction's full signature or public key; the educational output contains the signature-derived transaction ID and the safe block fields needed for this comparison.

The RPC response groups all rows in that block under `transactions`. The SQLite side uses the same confirmation height to read:

```sql
SELECT ...
FROM transactions
WHERE block_height = ?
ORDER BY rowid;
```

It also reads exactly one parameterized difficulty row:

```sql
SELECT difficulty
FROM misc
WHERE block_height = ?;
```

The learner cannot change either statement.

## 4. Read the result

The output has this shape, with values from the current local run:

```json
{
  "database": "temporary regnet ledger",
  "tables": ["transactions", "misc"],
  "block_height": 2,
  "block_hash": "<56-character block hash>",
  "transaction_count": 2,
  "difficulty": "8",
  "all_rows_share_block_identity": true,
  "rpc_block_hash_matches": true,
  "rpc_transaction_count_matches": true,
  "rpc_transaction_ids_match": true,
  "selected_transaction_matches": true,
  "rpc_matches_sqlite": true,
  "rows": [
    {
      "kind": "user_transaction",
      "txid": "<the transaction ID printed by send>",
      "address": "<Alice address>",
      "recipient": "<Bob address>",
      "amount": "1.00000000"
    },
    {
      "kind": "mining_reward",
      "recipient": "<miner address>",
      "reward": "<local reward>"
    }
  ]
}
```

Verify all of these observations:

1. `block_height` identifies the last transaction's confirmation block.
2. Every returned SQLite transaction row has the same `block_height` and same `block_hash`.
3. The `user_transaction` row has the transaction ID printed by `send`.
4. The same block also has a `mining_reward` row.
5. The `misc` table contributes the difficulty for that same height.
6. `rpc_transaction_ids_match` proves that the user transaction IDs in RPC and SQLite are the same.
7. `selected_transaction_matches` proves the transaction printed by `send` occurs exactly once in both views.
8. All RPC/SQLite comparison fields, including `rpc_matches_sqlite`, are `true`.

The output omits full signatures and public keys. Those values are public in a confirmed transaction, but they are not needed to understand the block-to-SQLite mapping.

The command fails closed if the RPC block identity or transaction count disagrees with SQLite rather than presenting mismatched data as a successful lesson.

## Transaction ID versus block hash

These identifiers answer different questions:

```text
txid       → which individual transaction?
block_hash → which block of transaction rows?
```

In this Bismuth version, the transaction ID is `signature[:56]`. The block hash is a 56-character lowercase hexadecimal identifier shared by every row in its block.

## Why the difficulty is not yet a real-network lesson

Regnet uses a pinned local difficulty so mining is immediate and deterministic. This lab proves storage structure, not live difficulty adjustment. The next lab should observe actual Bismuth mainnet block timestamps and difficulty through a separate explicit read-only entrypoint; it must not add mainnet fallback to this mutable regnet CLI.

## Clean up

The final command is:

```text
quit
```

Successful cleanup ends with:

```text
Regnet stopped; temporary wallets and ledger removed.
```

## What you learned

```text
locally signed transaction
→ confirmed at one block height
→ RPC groups the block as JSON
→ SQLite stores user and reward transaction rows
→ rows share one block height and block hash
→ misc stores difficulty for that height
→ RPC and SQLite identities match
```

Lab 2.1 traced when one transaction becomes persistent. Lab 5 expands the view from one row to the complete block structure without exposing arbitrary SQL or a database path.
