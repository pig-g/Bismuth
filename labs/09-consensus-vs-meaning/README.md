# Lab 9: Consensus Data vs Meaning — a New Indexer Prototype

See how Bismuth keeps the **consensus layer** (what the network agrees on) separate from the **meaning layer** (what applications interpret), and build a small **new indexer** over the same raw rows.

- **Time:** ~8 min
- **Guide:** read this page
- **Runtime:** local macOS or Linux Terminal
- **Prerequisite:** the repository `.venv` from [Lab 0](../00-regnet-first-run/README.md)

## The idea

Every Bismuth transaction carries two reserved fields that the consensus layer treats **opaquely**:

| field | role in consensus |
|---|---|
| `operation` | a short string (e.g. `0`, `alias:register`, `token:issue`) — the node stores and relays it but does not interpret it |
| `openfield` | free text (e.g. an alias, or `gem:1000`) — likewise stored/relayed verbatim |

The block is valid regardless of what these strings *mean*. Meaning is added by a separate **indexer layer**: in the real codebase, `tokensv2.py`, `aliasesv2.py`, `staking.py`, and `digest.py` each read `operation`/`openfield` and build their own derived view. If you deploy a new indexer, you add a new meaning **without touching the block data or the consensus rules**.

## Run the prototype

```bash
.venv/bin/python ./labs/09-consensus-vs-meaning/indexer_prototype.py
```

You will see two layers over the *same* rows:

1. **Consensus layer** — prints exactly what the node stores/relays, with `operation`/`openfield` as opaque strings. It asserts nothing about `alias:register` or `gem:1000`.
2. **Indexer layer** — a brand-new **“asset temperature”** index you just invented. It parses `openfield` to discover the `gem` asset and derives `mentions`, `distinct_active_addresses`, and a normalised `temperature`, none of which exist in the block data.

```text
[consensus layer] ...
   h=2 BBBBBBBBBB... op='alias:register'   openfield='alice'
   h=3 AAAAAAAAAA... op='token:issue'      openfield='gem:1000'
   ...
[indexer layer] ...
   asset 'gem': mentions=4 distinct_active_addrs=4 temperature=0.5714
```

## What to notice

- The raw rows never change between the two layers — the prototype proves **adding meaning does not modify consensus data**.
- An indexer is allowed to *disagree*: two indexers can interpret the same `openfield` differently, and consensus does not care.
- This is the same separation the real network uses: a token indexer and an alias indexer both consume the same opaque `operation` strings.

## Reading the code

- `indexer_prototype.py` — the tiny owned ledger (`build_raw_ledger`), the naive consensus view (`consensus_layer`), and your new index (`new_indexer_prototype`).
- In the repo: `tokensv2.py` (`token_*` ops), `aliasesv2.py` (`alias:*`), `staking.py`, `digest.py` are the production indexers that inspired this.

## Limitations

- This prototype uses a small synthetic ledger for determinism; it is not a full token consensus implementation (that is Lab 8 territory).
- It only *reads* blocks; it does not validate signatures or balances — that is the node's job.
- Renaming or extending an indexer here affects nothing on any network.
