#!/usr/bin/env python3
"""Run a test-BIS transfer and inspect its confirmed local regnet state."""

from decimal import Decimal
from pathlib import Path
import secrets
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bismuthclient.bismuthclient import BismuthClient
import regnet_control

TRANSFER_AMOUNT = Decimal("1.00000000")
OPERATION = "lab1"
OPENFIELD = "test-bis-workflow"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run_workflow(client):
    recipient = secrets.token_hex(28)

    require(
        client.command(command="regtest_generate", options=[1]) == "OK",
        "Regnet did not generate the funding block",
    )
    txid = client.send(
        recipient=recipient,
        amount=float(TRANSFER_AMOUNT),
        operation=OPERATION,
        data=OPENFIELD,
    )
    require(isinstance(txid, str) and txid, "Regnet rejected the test transfer")
    require(
        client.command(command="regtest_generate", options=[1]) == "OK",
        "Regnet did not generate the confirmation block",
    )

    transaction = client.command(
        command="api_gettransaction", options=[txid, True]
    )
    require(transaction.get("txid") == txid, "Confirmed transaction was not found")
    require(transaction.get("recipient") == recipient, "Transaction recipient changed")
    require(
        Decimal(str(transaction.get("amount"))) == TRANSFER_AMOUNT,
        "Transaction amount changed",
    )

    balance = client.command(command="balancegetjson", options=[recipient])
    recipient_balance = Decimal(str(balance["balance"]))
    require(
        recipient_balance == TRANSFER_AMOUNT,
        "Recipient balance does not equal the confirmed test transfer",
    )

    ledger = client.command(command="addlistlimjson", options=[recipient, 10])
    ledger_entry = next(
        (entry for entry in ledger if entry["signature"].startswith(txid)), None
    )
    require(ledger_entry is not None, "Confirmed transfer is absent from the ledger")

    block_height = transaction["blockheight"]
    block_response = client.command(
        command="api_getblockfromheight", options=[block_height]
    )
    block = block_response[str(block_height)]
    require(
        any(entry["txid"] == txid for entry in block["transactions"]),
        "Confirmation block does not contain the transfer",
    )

    return {
        "sender": client.address,
        "recipient": recipient,
        "amount": f"{TRANSFER_AMOUNT:.8f}",
        "txid": txid,
        "recipient_balance": f"{recipient_balance:.8f}",
        "transaction": transaction,
        "ledger_entry": ledger_entry,
        "block": block,
    }


def standalone_client():
    current = regnet_control.status()
    if not current.running or current.metadata is None:
        raise RuntimeError("Standalone regnet is not running; use ./scripts/regnet start")
    return BismuthClient(
        servers_list={f"{regnet_control.REGNET_HOST}:{regnet_control.REGNET_PORT}"},
        wallet_file=current.metadata["wallet_file"],
    )


def main():
    try:
        result = run_workflow(standalone_client())
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"lab 1: {exc}", file=sys.stderr)
        return 1

    print("TEST BIS WORKFLOW PASS")
    print(f"Sender: {result['sender']}")
    print(f"Recipient: {result['recipient']}")
    print(f"Transferred: {result['amount']} test BIS")
    print(f"Recipient balance: {result['recipient_balance']} test BIS")
    print(f"Transaction: {result['txid']}")
    print(f"Confirmed block: {result['block']['block_height']}")
    print(f"Block hash: {result['block']['block_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
