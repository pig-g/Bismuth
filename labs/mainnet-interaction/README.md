# Mainnet Interaction Track: Real Bismuth Mainnet, Read + Small Write

This is the **separate mainnet track**, distinct from the regnet labs (Labs 0–8). It talks to the **actual Bismuth mainnet** so you can observe the real chain and — if you choose — move a **small trial amount** of real BIS the way a real wallet does.

- **Time:** read 5 min; small send a few minutes
- **Guide:** read this page in GitHub or a Markdown editor
- **Runtime:** a local macOS or Linux Terminal

> **Because Bismuth has no testnet, we use the real mainnet with small trial amounts.** This is real money on a real network: transactions are irreversible. Only send amounts you can afford to lose.

## Safety contract (read this first)

1. **Reads are allowlisted.** The observer only issues safe read-only RPCs (`statusjson`, `blocklastjson`, `api_getblockfromheight`, `api_getbalance`, …). Write / process-control commands are rejected before they ever reach a node.
2. **Local signing only.** Your private key is loaded from your own local file and **never sent to any node**. BismuthClient signs the transaction locally and broadcasts only the signed transaction. We do NOT use the deprecated `txsend`/`keygen` node-side signing that sends a private key.
3. **Small trial amounts.** A single transfer is capped at a tiny default (`0.10000000` BIS) and must be confirmed before sending.
4. **Explicit warning.** Every command prints a REAL-MAINNET warning banner.
5. **No funds, no loss.** A freshly created wallet has no BIS, so a send from it is rejected by the node until you deposit a small trial balance.

## What you can do

| Command | Purpose | Safe? |
|---|---|---|
| `status` | node state, consensus height, difficulty | read-only |
| `height` | current mainnet block height | read-only |
| `block <height>` | one block (signatures/public keys redacted) | read-only |
| `balance <address>` | an address balance | read-only |
| `tx <txid>` | one confirmed transaction | read-only |
| `wallet new <path>` | create a local wallet (private key stays local) | local only |
| `send --wallet <p> --to <addr> --amount <a> [--op x] [--data y]` | locally sign + broadcast a small trial send | confirmed, small |

## 1. Prerequisites

- macOS or Linux, Python 3.11
- the isolated `.venv` (from [Lab 0](../00-regnet-first-run/README.md))
- outbound access to a public Bismuth mainnet node on port `5658`
- for `send`: a local wallet that holds a **small trial BIS balance** you added yourself

## 2. Observe the real chain (read-only, no keys)

From the repository root:

```bash
.venv/bin/python ./labs/mainnet-interaction/mainnet_cli.py height
.venv/bin/python ./labs/mainnet-interaction/mainnet_cli.py status
.venv/bin/python ./labs/mainnet-interaction/mainnet_cli.py block 4928659
```

Every command starts with the warning banner and prints safe read-only data. Verify the current height keeps rising, and that the latest block's difficulty and mining reward are real mainnet values. Full signatures and public keys are shown as `[REDACTED]`.

## 3. Create a local wallet

```bash
.venv/bin/python ./labs/mainnet-interaction/mainnet_cli.py wallet new ./trial.der
```

This creates a local wallet file and prints only its **public address**. The private key stays in that file on your machine. Copy the printed address.

## 4. Deposit a small trial amount (optional)

If you already have real BIS somewhere, send a **small trial amount** to the address from step 3 (e.g. from an exchange or an existing wallet). This is the only place real BIS enters this track — and it is your choice with your coins.

## 5. Send a small trial transfer (optional, confirmed)

```bash
.venv/bin/python ./labs/mainnet-interaction/mainnet_cli.py send \
  --wallet ./trial.der \
  --to <another-address> \
  --amount 0.001
```

The CLI re-prints the amount, warns it is real BIS on mainnet, and asks you to type `send` to confirm. It refuses oversize amounts and will be rejected by the node if the wallet holds less than what you are sending.

## Reading the code

- `mainnet_rpc.py` — the safety core: the read-only allowlist, the small-amount cap, the local-signing send path, and the blocked-write guard.
- `mainnet_cli.py` — the command entrypoint, the persistent warning banner, and output redaction.
- The signing happens inside `BismuthClient.send` (in your `.venv`): it calls `self._wallet.sign_encoded(...)` locally, then broadcasts only the signed transaction via `mpinsert`. It never transmits your private key.

## Design notes and limitations

- Seeds are point-in-time public nodes from the 2026-07-26 audit; a seed may be down at any moment. `BismuthClient` iterates the seed list.
- The `send` cap is a conservative default (`0.10000000` BIS). You may raise it deliberately, but keep it small.
- Automatic tests never connect to the network and never spend BIS; they inject a fake client.
- See the wiki plan `concepts/bismuth-mainnet-interaction-track` for the full design rationale.

## Clean up

- `wallet new` writes only the file you name. Delete it to remove the wallet.
- The track starts no node, opens no local port, and leaves no temporary state.
- `send` does not leave local state either; it just signs and broadcasts.
