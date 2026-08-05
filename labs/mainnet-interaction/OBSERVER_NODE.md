# Observer Node — run a read-only Bismuth mainnet node for P2P/consensus research

**Phase 5.** Operating a real Bismuth full node lets you *measure* ban behaviour,
peer health and consensus formation directly, instead of only observing via
remote seeds. This is real mainnet participation: it downloads the full chain.

## Costs (be sure before you start)

- **~5.9 GB** `https://bismuth.cz/ledger.tar.gz` full-chain snapshot
- **Tens of GB** once extracted (SQLite ledger)
- A node that stays up to follow the chain and interact with peers (this is
  what produces the ban log worth studying)

Bismuth has **no lightweight/partial download option** — the only path is the
full snapshot plus, optionally, `recompress_ledger()` hyperblock packing to
shrink the local DB after the fact.

## Safety contract (observer = read-only, no mining, no keys)

1. **Never mine.** The default config has no mining key; keep it that way so
   you never compete on mainnet.
2. **No wallet, no private key.** This node is observation-only. Wallet/local-
   signing flows live in the separate `mainnet-interaction` track and are not
   connected here.
3. **Minimise remote influence.** `allowed=127.0.0.1` so only localhost can
   drive admin/write commands (`stop`, `mpclear`, destructive api_*).
4. **Isolated data.** Put `static_obs/` (ledger) and logs in their own
   directory so nothing touches your normal Bismuth install or real funds.
5. **Explicit mainnet warning.** You are a real peer on the live network.

## Steps

1. Copy the repo node files (or clone fresh) into an observer directory.
2. Copy `observer_config.sample.txt` -> `config.txt` in that directory.
3. Create `static_obs/` and download + extract the ledger there:
   ```bash
   mkdir -p static_obs && cd static_obs
   curl -L -o ledger.tar.gz https://bismuth.cz/ledger.tar.gz
   tar xzf ledger.tar.gz
   ```
4. Start the node (no mining, accepts peers, bound read-only):
   ```bash
   <python> node.py
   ```
5. Let it sync and interact; watch/collect the log.

## Analysing the ban log

The peer handler logs warning accumulation and bans with a **reason**:

```
WARNING: Added 2 warning(s) to <ip>: Forked (4 / 30)
WARNING: <ip> is banned: Rollback
```

Parse and summarise it with the CLI:

```bash
python mainnet_cli.py net ban-analyze static_obs/node.log
```

Example output:

```
Ban analysis: 6 events (2 bans, 4 warnings)
  Bans by reason:
    - Consensus deviation too high x1
    - Rollback x1
  Warning accumulation (top IPs, threshold 30): ...
  Consensus blockers observed:
    - Consensus deviation too high
    - Forked
    - Rollback
```

## The ban reason catalogue (what blocks consensus)

| Reason | Weight | Consensus blocker? |
|---|---|---|
| `Failed to deliver the longest chain` | 1 | sync failure |
| `Forked` | 2 | forked chain |
| `Rollback` | 2 | reorg |
| `Operation timeout` | 2 | latency |
| `Rejected block` | 2 | invalid block |
| `Consensus deviation too high` | 10 | **diverged consensus** |

A peer is banned when accumulated warnings reach `ban_threshold` (default 30).
