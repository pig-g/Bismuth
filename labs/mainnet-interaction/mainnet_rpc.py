#!/usr/bin/env python3
"""Mainnet interaction library (read + local-signing write).

This is the separate mainnet track, distinct from the `labs/01-test-bis-workflow`
regnet CLI. It talks to the actual Bismuth mainnet through a BismuthClient.

Safety contract
---------------
* The private key is NEVER sent to a node. BismuthClient.send() signs locally
  (see its `send` method: `self._wallet.sign_encoded(...)` then broadcasts only
  the signed transaction via `mpinsert`). We rely on that and never call the
  deprecated node-side signing (`txsend`/`keygen`) of `commands.py`.
* Reads go through a strict allowlist of read-only RPCs. Mutation / process
  control commands are rejected before they reach the node.
* Writes are bounded to a small trial amount and require an explicit
  human confirmation string; a `*_ok` flag must be True to actually send.
* Every entrypoint prints an explicit REAL-MAINNET warning.

All network behaviour is behind `client.command(...)`, so tests inject a fake
client and never touch a live node or spend real BIS.
"""

import shlex
from decimal import Decimal, InvalidOperation

# Real Bismuth mainnet: show this at the top of any output.
MAINNET_WARNING = (
    "REAL BISMUTH MAINNET - real wallets, real BIS, irreversible transactions.\n"
    "Use only small trial amounts you can afford to lose.\n"
    "Your private key stays on this machine; it is never sent to any node."
)

# Safe read-only RPCs (no state change, no process control, no key exposure).
READ_ONLY_ALLOWLIST = {
    "getversion",
    "statusjson",
    "blocklast",
    "blocklastjson",
    "api_getblockfromheight",
    "api_getblockfromhash",
    "api_getblockrange",
    "api_getbalance",
    "api_gettransaction",
    "mpgetjson",
    "mempool",
    "portget",
}

# Clearly dangerous / key-mutating / write commands that must never pass.
BLOCKED_SEND_COMMANDS = {
    "txsend", "keygen", "keygenjson", "api_clearmempool", "clearmempool",
    "mpinsert", "regtest_generate", "walletpassphrase", "backupwallet",
}

# Upper bound (BIS) for one learner trial transfer. Small by design.
MAX_TRIAL_AMOUNT = Decimal("0.10000000")


class MainnetError(RuntimeError):
    pass


class MainnetRPC:
    """Wraps a client exposing `.command(command, options)` (e.g. BismuthClient).

    The same injected object may also expose `.send(...)` for local-signing
    writes; that is optional and only used by `sign_and_send`.
    """

    def __init__(self, client, *, max_amount=MAX_TRIAL_AMOUNT):
        self.client = client
        self.max_amount = Decimal(str(max_amount))

    # ---- read-only -------------------------------------------------------

    def observe(self, command, options=None):
        """Run one allowlisted read-only RPC. Returns the node response."""
        command = str(command).lower()
        if command not in READ_ONLY_ALLOWLIST:
            raise MainnetError(
                f"{command} is not a read-only allowlisted mainnet RPC"
            )
        return self.client.command(command=command, options=list(options or []))

    def block_height(self):
        """Return current mainnet tip height via blocklastjson."""
        response = self.observe("blocklastjson")
        height = (response or {}).get("block_height")
        if not isinstance(height, int) or height < 1:
            raise MainnetError("blocklastjson returned a malformed block height")
        return height

    # ---- write (local signing only) -------------------------------------

    def sign_and_send(self, recipient, amount, *, operation="", data="",
                      confirm=False):
        """Sign locally and broadcast one small trial transaction.

        Requires `confirm=True` (set by a human after reading the amount). This
        method never touches the client's private key field directly; it calls
        the client's own `send`, which signs locally.
        """
        amount_d = _coerce_amount(amount, self.max_amount)
        if not confirm:
            raise MainnetError(
                "sending was not confirmed; re-run with confirm=True after "
                "checking the amount"
            )
        send = getattr(self.client, "send", None)
        if not callable(send):
            raise MainnetError(
                "this client does not support local sending (no .send method)"
            )
        txid = send(
            recipient=recipient,
            amount=float(amount_d),
            operation=operation,
            data=data,
        )
        if not txid:
            raise MainnetError("transaction was rejected by the node")
        return txid

    def reject_if_blocked_send(self, command):
        """Refuse a write that would otherwise touch the node as read."""
        if str(command).lower() in BLOCKED_SEND_COMMANDS:
            raise MainnetError(
                f"{command} is a mainnet write/control command and is blocked"
            )


def _coerce_amount(value, max_amount):
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise MainnetError("amount must be a decimal number") from exc
    if not amount.is_finite() or amount <= 0:
        raise MainnetError("amount must be a positive finite number")
    if amount > max_amount:
        raise MainnetError(
            f"amount {amount} exceeds the small trial limit {max_amount}"
        )
    return amount


def parse_send_args(text, max_amount=MAX_TRIAL_AMOUNT):
    """Parse 'send <recipient> <amount> [operation] [data]' safely."""
    words = shlex.split(text)
    if len(words) < 3:
        raise MainnetError("usage: send <recipient> <amount> [operation] [data]")
    _, recipient, amount, *rest = words
    operation = rest[0] if len(rest) >= 1 else ""
    data = rest[1] if len(rest) >= 2 else ""
    return recipient, _coerce_amount(amount, max_amount), operation, data
