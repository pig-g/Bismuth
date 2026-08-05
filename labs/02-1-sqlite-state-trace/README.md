# Lab 2.1: SQLite State Trace

Follow one locally signed test transaction across the persistence boundary between the in-memory mempool and the owned temporary SQLite ledger.

- **Time:** about 10 minutes
- **Guide:** read this page in GitHub or a Markdown editor
- **Runtime:** run the existing Lab 1 CLI in a local macOS or Linux Terminal

## Safety boundary

This lab starts an owned node only on `127.0.0.1:3030`. It uses test BIS, generated temporary wallets, a RAM mempool, and `regmode.db` inside an owned temporary directory. It has no mainnet connection, no remote fallback, and no real BIS.

`sqltx` is not an arbitrary SQL console. It opens only the session's temporary ledger in read-only mode and runs one parameterized query against the `transactions` table. You cannot provide a database path or SQL text. On `quit`, the node, wallets, and entire temporary directory are deleted.

## 1. Start the existing CLI

From the repository root:

```bash
.venv/bin/python ./labs/01-test-bis-workflow/cli.py
```

Wait for the `regnet>` prompt.

## 2. Create a funded local sender

Run:

```text
wallets
```

Observe the generated Alice and Bob addresses. Then mine one reward block for Alice:

```text
mine 1
```

The private keys remain local and are not printed.

## 3. Send one transaction into the RAM mempool

```text
send alice bob 1
```

The CLI signs locally and prints a 56-character transaction ID. In legacy Bismuth, the relationship is:

```python
txid = signature[:56]
```

Confirm that the pending row is visible through the structured mempool view:

```text
mempool
```

The row has the same named `txid`.

## 4. Prove that pending is not yet persisted

```text
sqltx last
```

Expected fields include:

```json
{
  "database": "temporary regnet ledger",
  "table": "transactions",
  "row_found": false
}
```

This session deliberately uses a RAM mempool. Before mining, the valid transaction exists in mempool state but not yet in the SQLite `transactions` table.

## 5. Mine the persistence boundary

```text
mine 1
```

Check that the pending view is now empty:

```text
mempool
```

Then query the same txid in the owned ledger:

```text
sqltx last
```

Now `row_found` is `true`. Compare these safe fields with the earlier mempool row:

- `txid`
- `address` and `recipient`
- `amount`
- `operation` and `openfield`
- `block_height`

The command does not expose the full signature, public key, database path, or arbitrary rows.

## 6. Clean up

```text
quit
```

The supervisor terminates its owned child node, waits for port `3030` to close, and removes all CLI session state.

## What you learned

```text
local signature
→ RAM mempool row
→ no ledger SQLite row yet
→ mine a block
→ mempool removal
→ confirmed regmode.db transactions row
```

Lab 2 showed the public lifecycle. Lab 2.1 shows the local storage boundary without turning the learner CLI into a general database shell.
