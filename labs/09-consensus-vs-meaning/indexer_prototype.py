#!/usr/bin/env python3
"""Lab 9: consensus data vs meaning - a new indexer prototype.

Bismuth stores transactions with two reserved fields that the *consensus*
layer treats opaquely: `operation` and `openfield`. The node does not parse
`openfield`; it only stores and relays it. Meaning arrives in a separate
*indexer* layer (e.g. aliasesv2.py, tokensv2.py, staking.py, digest.py) that
reads those fields and builds derived ledgers/tables.

In this lab you build a NEW indexer prototype (an 'asset temperature' index)
over the same raw consensus rows, showing that adding meaning does not change
the block data.

Run with:  .venv/bin/python ./labs/09-consensus-vs-meaning/indexer_prototype.py
"""

import sqlite3, tempfile, os
from collections import defaultdict, Counter


def build_raw_ledger(con):
    """Emit a small owned ledger of raw consensus transaction rows.

    Each row is (block_height, address, recipient, amount, signature, operation,
    openfield). These look exactly like what a node stores - operation/openfield
    are opaque strings here. The consensus layer does not interpret them.
    """
    rows = [
        # (height, addr, recipient, amount, op, openfield)
        (1, "A" * 56, "A" * 56, 0, "s1", "0", ""),
        (2, "B" * 56, "B" * 56, 0, "s2", "alias:register", "alice"),
        (3, "A" * 56, "A" * 56, 0, "s3", "token:issue", "gem:1000"),
        (3, "C" * 56, "B" * 56, 0, "s4", "token:issue", "gem:1000"),
        (4, "A" * 56, "D" * 56, 0, "s5", "token:transfer", "gem:40"),
        (4, "A" * 56, "B" * 56, 0, "s6", "token:transfer", "gem:10"),
        (5, "E" * 56, "E" * 56, 0, "s7", "0", "merkle-ish"),
    ]
    con.execute("DROP TABLE IF EXISTS txns")
    con.execute(
        "CREATE TABLE txns (block_height INTEGER, address TEXT, recipient TEXT, "
        "amount REAL, signature TEXT, operation TEXT, openfield TEXT)"
    )
    con.executemany(
        "INSERT INTO txns VALUES (?,?,?,?,?,?,?)", rows
    )
    con.commit()
    return con


def consensus_layer(con):
    """What the consensus layer can honestly say: it only selects the raw rows.
    It never asserts what 'alias:register' or 'gem:1000' means."""
    return con.execute(
        "SELECT block_height, address, operation, openfield FROM txns "
        "ORDER BY block_height, signature"
    ).fetchall()


def new_indexer_prototype(con):
    """NEW indexer: 'asset temperature'.

    Reads the same raw rows and derives meaning that the node never stores.
    Asset temperature = number of distinct active addresses that mention an
    asset (its issue/transfer openfield token), normalised by chain height.
    """
    mentions = Counter()
    active = defaultdict(set)
    for height, addr, recipient, amount, sig, operation, openfield in con.execute(
        "SELECT block_height, address, recipient, amount, signature, "
        "operation, openfield FROM txns ORDER BY block_height, signature"
    ):
        token = None
        # indexer reads the opaque openfield to derive a token name - meaning.
        if operation == "token:issue" and ":" in openfield:
            token = openfield.split(":", 1)[0]
        elif operation == "token:transfer" and ":" in openfield:
            token = openfield.split(":", 1)[0]
        if token:
            mentions[token] += 1
            active[token].add(addr)
            if recipient and recipient != addr:
                active[token].add(recipient)

    # normalise by total rows => a 0..1 'temperature'
    total_rows = sum(1 for _ in con.execute("SELECT 1 FROM txns"))
    result = {}
    for token, count in mentions.items():
        result[token] = {
            "mentions": count,
            "distinct_addresses": len(active[token]),
            "temperature": round(len(active[token]) / max(total_rows, 1), 4),
        }
    return result


def main():
    print("Lab 9: consensus data vs meaning - a new indexer prototype")
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "ledger.db")
        con = sqlite3.connect(db)
        build_raw_ledger(con)

        print()
        print("[consensus layer] - what the node stores/relays (opaque):")
        for row in consensus_layer(con):
            h, addr, operation, openfield = row
            print(f"   h={h} {addr[:10]}... op={operation!r:20} openfield={openfield!r}")

        print()
        print("[indexer layer] - NEW 'asset temperature' prototype over the SAME rows:")
        for token, info in sorted(new_indexer_prototype(con).items()):
            print(f"   asset {token!r}: mentions={info['mentions']} "
                  f"distinct_active_addrs={info['distinct_addresses']} "
                  f"temperature={info['temperature']}")

        print()
        print("The block rows never changed: only a separate indexer added meaning.")
        con.close()


if __name__ == "__main__":
    main()
