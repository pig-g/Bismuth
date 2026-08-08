#!/usr/bin/env python3
"""Checkpoint SQLite WAL files into their main DBs and remove leftover sidecars.

Run this AFTER the observer node has been cleanly stopped. It checkpoint-truncates
the WAL of every Bismuth DB in this repo (the DBs the observer writes to) so the
'-wal' / '-shm' sidecar files disappear, leaving the databases in a clean offline
state safe for backup or an offline fork_recovery rollback.

WAL sidecars are NORMAL while the node is up. Never delete them with rm. This
script is the safe way to finalize them: it folds the WAL frames into the main
DB (PRAGMA wal_checkpoint(TRUNCATE)) and verifies nothing is left over.

Usage:
    python3 checkpoint_wal.py [BISMUTH_ROOT]

If BISMUTH_ROOT is omitted it defaults to the directory this script lives in
(the repo base). The script refuses to run while a Bismuth node process is
still alive.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

# Observer DBs that live in journal_mode=WAL (ledger and hyper). index.db is
# journal_mode=delete, so it has no WAL to checkpoint — included only when we
# detect a sidecar for it.
WAL_DBS = ("static_obs/ledger.db", "static_obs/hyper.db")

# Node processes this script will refuse to run alongside. Match the real
# entrypoint specifically (node.py --config-custom/--config) so that unrelated
# processes or wrapper shells whose cmdline merely mentions "node.py" are not
# mistaken for a live node.
NODE_PATTERNS = ("node.py --config",)


def _node_process_running() -> list[int]:
    """Return pids of running Bismuth node processes, or [] if none."""
    pids: list[int] = []
    for pat in NODE_PATTERNS:
        try:
            out = subprocess.run(
                ["pgrep", "-f", pat],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            continue
        for line in out.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                pids.append(int(line))
    # drop our own pgrep/subprocess pids (they contain the pattern string too)
    me = os.getpid()
    return [p for p in pids if p != me]


def _checkpoint(path: Path) -> tuple[str, tuple[int, int, int] | None]:
    """Checkpoint one DB's WAL (TRUNCATE). Returns (journal_mode, result)."""
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        result = tuple(row) if row is not None else None
    finally:
        conn.close()
    return mode, result


def _leftover_sidecars(root: Path) -> list[Path]:
    found: list[Path] = []
    for db in WAL_DBS:
        for suffix in (".db-wal", ".db-shm"):
            p = root / f"{db}{suffix}"
            if p.exists():
                found.append(p)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Checkpoint WAL sidecars into their main DBs (safe offline finalization)."
        )
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=str(Path(__file__).resolve().parent),
        help="Bismuth repo root (default: this script's directory)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 1

    # Safety gate 1: the node must not be running.
    pids = _node_process_running()
    if pids:
        print(f"error: Bismuth node process(es) still running: {pids}", file=sys.stderr)
        print("Stop the node first (send the local 'stop' command), then re-run.", file=sys.stderr)
        return 1

    # Safety gate 2: every DB we plan to touch must exist.
    missing = [db for db in WAL_DBS if not (root / db).exists()]
    if missing:
        print(f"error: missing DB files: {missing}", file=sys.stderr)
        return 1

    print(f"Bismuth root: {root}")
    print("node processes: none (safe to checkpoint)")

    all_ok = True
    for rel in WAL_DBS:
        path = root / rel
        mode, result = _checkpoint(path)
        busy = bool(result is not None and result[0])
        status = "OK" if (not busy and result is not None and result[1] == 0 and result[2] == 0) else "CHECK"
        print(f"  {rel}: journal_mode={mode} wal_checkpoint(TRUNCATE)={result} -> {status}")
        if busy:
            # A busy summary (first value 1) means another connection is using the DB.
            print("    warning: another connection holds the DB; do not remove sidecars yet", file=sys.stderr)
            all_ok = False

    # Verify sidecars are gone.
    left = _leftover_sidecars(root)
    if left:
        for p in left:
            print(f"  leftover sidecar (safe since not busy): {p} ({p.stat().st_size} bytes)")
        # If checkpoint reported busy, fail-closed; otherwise stale empty residue is removable.
        if all_ok:
            for p in left:
                try:
                    p.unlink()
                    print(f"  removed stale sidecar: {p.name}")
                except OSError as e:
                    print(f"  error removing {p}: {e}", file=sys.stderr)
                    all_ok = False
        else:
            print("error: DB was busy; sidecars left in place", file=sys.stderr)
            return 1

    if all_ok:
        print("WAL checkpoint complete: databases are clean and offline.")
        return 0
    print("WAL checkpoint finished with warnings.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
