# Lab 10: Unsafe Defaults — Threat Model + Hardening Scanner

Build a mental threat model of the dangerous defaults a Bismuth node ships with, then run a small **hardening scanner** that flags those patterns in the real source so you learn to recognise and fix them.

- **Time:** ~8 min
- **Guide:** read this page
- **Runtime:** local macOS or Linux Terminal
- **Prerequisite:** the repository `.venv` from [Lab 0](../00-regnet-first-run/README.md)

## The idea

Bismuth's node listens on a TCP port (`0.0.0.0:<port>` — default `5658` on mainnet) and answers two command families: read queries in `apihandler.py` (`api_*`) and client commands in `commands.py`. A few of these are **unsafe by default** for someone running a node for learning:

- `commands.py` `keygen` / `txsend` send a **raw private key to the node** so it can sign.
- `api_getconfig` discloses node configuration to any caller.
- `api_clearmempool` lets any connected peer wipe the local mempool (DoS / griefing).
- Binding to `0.0.0.0` exposes all of the above to the whole network.

This lab does **not** patch the node. It makes you *recognise* the patterns and understand what a safe design looks like.

## Run the threat model + scanner

```bash
.venv/bin/python ./labs/10-insecure-defaults/threat_model.py
```

The script:

1. prints a **threat model** table — for each unsafe default: severity, the risky pattern, *why* it is dangerous, and a *safe fix*;
2. runs its **hardening scanner** over the real `commands.py` and `apihandler.py` and lists the exact lines that match, each with its fix.

You should see it flag the real `remote_tx_privkey = arg1` call in `txsend` (`commands.py:333`), `def keygen` (`commands.py:215`), `api_getconfig` (`commands.py:90`, `apihandler.py:139`), and `api_clearmempool` (`apihandler.py:149`).

## What to notice

- Several HIGH-severity findings are about **custody of the private key**: never let a node sign for you; sign where you control the key and broadcast only the signed transaction.
- Read-only queries are fine; *control/state-changing* commands are the ones to gate.
- Binding to loopback (`127.0.0.1`) instead of `0.0.0.0` shrinks the attack surface a lot for a learning node.
- This is the same reasoning that shaped the [Mainnet Interaction Track](../mainnet-interaction/README.md): local signing only, and never exposing destructive control.

## Reading the code

- `threat_model.py` — the `Threat` dataclass, the threat table, and the small `scan_file` scanner. Add your own patterns to `THREATS` to extend the model.
- In the repo: `commands.py` (`keygen`, `txsend`) and `apihandler.py` (`api_getconfig`, `api_clearmempool`) are the real subjects.

## Limitations

- The scanner does simple substring matching — it can produce false positives (e.g. a commented line) and cannot reason about runtime state. It is a teaching aid, not a security product.
- It never modifies the node; hardening is left to the learner/reviewer.
- A real deployment review needs a human and a proper network/auth threat model; this is a starting point.
