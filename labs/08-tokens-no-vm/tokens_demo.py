#!/usr/bin/env python3
"""Lab 8: token issue / transfer / reindex model (NO VM).

Demonstrates the Bismuth 'tokens without a VM' idea from node/tokensv2.py:
tokens are just specially-labelled transactions. The operation field says
'token:issue' or 'token:transfer', and the openfield name encodes
'token_name:amount'. A separate index table rebuilds balances from those rows.

This is a self-contained teaching model of that accounting. It uses a real,
ephemeral SQLite database in a temporary directory (created and deleted in the
same run). Safety: no node, no port, no persistent file, no keys, no mainnet.
"""

import sqlite3
import tempfile
from pathlib import Path


def build_tokens_table(connection):
    connection.execute(
        "CREATE TABLE tokens ("
        "block_height INTEGER, timestamp, token, address, recipient, txid, amount INTEGER)"
    )


def build_transactions(connection):
    connection.execute(
        "CREATE TABLE transactions ("
        "block_height INTEGER, timestamp, address TEXT, recipient TEXT, "
        "signature TEXT, operation TEXT, openfield TEXT, reward NUMERIC)"
    )


def insert_tx(connection, height, operation, address, recipient, signature, openfield):
    connection.execute(
        "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?)",
        (height, 1000 + height, address, recipient, signature, operation, openfield, 0),
    )


def txid(signature):
    return signature[:56]


def reindex(connection):
    """Rebuild the tokens table from transaction rows, mirroring tokensv2 logic."""
    build_tokens_table(connection)
    issues = connection.execute(
        "SELECT block_height, address, signature, openfield FROM transactions "
        "WHERE operation='token:issue' ORDER BY block_height"
    ).fetchall()
    for height, address, signature, openfield in issues:
        name, total = openfield.split(":")
        # match tokensv2: address="issued" marker, recipient=issuer address
        connection.execute(
            "INSERT INTO tokens VALUES (?,?,?,?,?,?,?)",
            (height, "", name, "issued", address, txid(signature), int(total)),
        )

    transfers = connection.execute(
        "SELECT block_height, address, recipient, signature, openfield FROM transactions "
        "WHERE operation='token:transfer' ORDER BY block_height"
    ).fetchall()
    for height, sender, recipient, signature, openfield in transfers:
        name, amount = openfield.split(":")
        amount = int(amount)
        credit = connection.execute(
            "SELECT COALESCE(SUM(amount),0) FROM tokens WHERE recipient=? AND token=?",
            (sender, name),
        ).fetchone()[0]
        debit = connection.execute(
            "SELECT COALESCE(SUM(amount),0) FROM tokens WHERE address=? AND token=?",
            (sender, name),
        ).fetchone()[0]
        balance = credit - debit
        if 0 <= balance - amount:
            connection.execute(
                "INSERT INTO tokens VALUES (?,?,?,?,?,?,?)",
                (height, "", name, sender, recipient, txid(signature), amount),
            )


def balances(connection, name):
    """Net token balance per holder: credits (as recipient) minus debits (as sender)."""
    holders = set()
    for (address,) in connection.execute(
        "SELECT recipient FROM tokens WHERE token=? ", (name,)
    ).fetchall():
        holders.add(address)
    for (address,) in connection.execute(
        "SELECT address FROM tokens WHERE token=? ", (name,)
    ).fetchall():
        if address and address != "issued":
            holders.add(address)
    result = []
    for holder in sorted(holders):
        credit = connection.execute(
            "SELECT COALESCE(SUM(amount),0) FROM tokens WHERE token=? AND recipient=?",
            (name, holder),
        ).fetchone()[0]
        debit = connection.execute(
            "SELECT COALESCE(SUM(amount),0) FROM tokens WHERE token=? AND address=?",
            (name, holder),
        ).fetchone()[0]
        result.append((holder, credit - debit))
    return result


def main():
    print("Lab 8: token issue / transfer / reindex model (no VM)")
    print("A self-contained model of the token accounting in node/tokensv2.py.\n")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "tokens.db"
        connection = sqlite3.connect(str(db_path))
        build_transactions(connection)

        # --- issue ---
        insert_tx(connection, 1, "token:issue", "a" * 56, "a" * 56, "s-issue-" + "x" * 50, "worthless:1000")
        # --- transfers ---
        insert_tx(connection, 2, "token:transfer", "a" * 56, "b" * 56, "s-t1-" + "y" * 51, "worthless:100")
        insert_tx(connection, 3, "token:transfer", "b" * 56, "c" * 56, "s-t2-" + "z" * 51, "worthless:40")
        insert_tx(connection, 4, "token:transfer", "a" * 56, "c" * 56, "s-t3-" + "w" * 51, "worthless:60")
        # --- an over-spend that must be rejected ---
        insert_tx(connection, 5, "token:transfer", "c" * 56, "z" * 56, "s-t4-" + "v" * 51, "worthless:9999")
        connection.commit()

        reindex(connection)

        print("Issued 'worthless:1000' to " + ("a" * 56)[:8] + "...")
        print("Transfers: a->b 100, b->c 40, a->c 60, then c->z 9999 (insufficient)\n")
        for address, total in balances(connection, "worthless"):
            print(f"  balance {address[:8]}... = {total}")

        expected = {"a" * 56: 840, "b" * 56: 60, "c" * 56: 100}
        print("\nExpected (a=1000-100-60=840, b=100-40=60, c=40+60=100):")
        print("  the c->z 9999 transfer was rejected because c held only 100")
        ok = all(
            dict(balances(connection, "worthless")).get(addr) == total
            for addr, total in expected.items()
        )
        print(f"\nreindex balance check: {'OK' if ok else 'MISMATCH'}")
        print("\nObservation:")
        print("- tokens need no VM: a token is just transactions tagged token:issue / token:transfer")
        print("- the index table is rebuilt from the same rows each reindex (deterministic)")
        print("- transfers are rejected when they would over-draw the sender's token balance")


if __name__ == "__main__":
    main()
