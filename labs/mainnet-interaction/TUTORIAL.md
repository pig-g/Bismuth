# Mainnet Interaction Track — Step-by-Step Tutorial

Follow this in order. Each step shows the exact command and what you should see.

> **Warning first:** this talks to the **real Bismuth mainnet**. Reads are safe.
> The only write (`send`) moves **real BIS and cannot be undone** — use a small
> trial amount only. Your private key stays on this machine and is never sent.

## Step 0 — Create the isolated environment (one time)

From the repository root, run the automatic setup. It creates a `.venv-mainnet`
folder (separate from the regnet `.venv`) and installs the pinned
`bismuthclient`:

```bash
sh ./labs/mainnet-interaction/setup_venv.sh
```

You should see it finish with:

```text
[setup] OK - bismuthclient importable.
Mainnet venv ready: .../.venv-mainnet
```

> Only if you see an error here do you need to check Python 3.11 is installed
> (`python3 --version`) and that you have network access for pip.

From here on, every command uses `./.venv-mainnet/bin/python`.

## Step 1 — Confirm you are on real mainnet (read only)

```bash
./.venv-mainnet/bin/python ./labs/mainnet-interaction/mainnet_cli.py status
```

You should see the warning banner, then JSON with `"difficulty"`, `"consensus"`,
and a working `"server_timestamp"`. This proves you reached a real mainnet node.

## Step 2 — Read the current chain height (read only)

```bash
./.venv-mainnet/bin/python ./labs/mainnet-interaction/mainnet_cli.py height
```

Expected output ends in something like:

```text
mainnet block height: 4928681
```

The number will be higher next run — the chain is live.

## Step 3 — Look at one real block (read only)

```bash
./.venv-mainnet/bin/python ./labs/mainnet-interaction/mainnet_cli.py block 4928659
```

You get a real block's transactions. Note the reward (block subsidy), the
`txid`, and that **signatures and public keys show as `[REDACTED]`**.

## Step 4 — Check a balance (read only)

```bash
./.venv-mainnet/bin/python ./labs/mainnet-interaction/mainnet_cli.py balance <some-address>
```

Use any Bismuth address (for example one you see in a block). Reads never touch
your own keys.

## Step 5 — Create a local wallet (local only)

```bash
./.venv-mainnet/bin/python ./labs/mainnet-interaction/mainnet_cli.py wallet new ./trial.der
```

Expected output:

```text
wallet created: ./trial.der
address: 246358ec29a5b071afe1f31765761aa4bdfd05d08eb325e68784badb
```

- The address is **public** — safe to share.
- The private key is in `./trial.der` on **your machine only**. Never upload it
  and never paste it into any tool.

## Step 6 — Deposit a small trial amount (your choice)

This is the **only** place real BIS enters. Send a **small** amount (e.g. less
than a dollar's worth) from an exchange or wallet you already control to the
address from Step 5. It appears on-chain within a minute or two.

If you do not deposit, skip to Step 8 — everything else still works.

## Step 7 — Send a small trial transfer (optional, irreversible)

```bash
./.venv-mainnet/bin/python ./labs/mainnet-interaction/mainnet_cli.py send \
  --wallet ./trial.der \
  --to <receiver-address> \
  --amount 0.001
```

The CLI reprints the amount, warns it is real BIS on mainnet, and asks you to
type the word `send` to confirm. Only then does it sign locally and broadcast.

- If you type anything else, it aborts and sends nothing.
- If the wallet has no balance it is rejected: `Sending more than owned`.
- Amounts above the small cap are refused before sending.

## Step 8 — Verify (read only, always works)

```bash
./.venv-mainnet/bin/python ./labs/mainnet-interaction/mainnet_cli.py tx <txid>
```

Shows one confirmed transaction. If you completed Step 7, pass the txid from the
send output to confirm it reached the chain.

## Clean up

- The wallet file `./trial.der` is the only thing you created on disk. Delete it
  to remove the wallet.
- The track starts no node and opens no local port.
- To remove the environment later: `rm -rf .venv-mainnet` (re-run setup to
  recreate).

## Troubleshooting

- **`bismuthclient` import error** — run Step 0 again; ensure you used
  `./.venv-mainnet/bin/python`, not plain `python`.
- **`Could not connect` / no height** — a seed may be briefly down. Retry, or
  wait a minute; `BismuthClient` iterates its seed list.
- **`Sending more than owned`** — that wallet has no balance; deposit first
  (Step 6).
