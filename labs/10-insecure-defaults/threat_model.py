#!/usr/bin/env python3
"""Lab 10: unsafe defaults - threat model and hardening scanner.

Bismuth's node exposes a JSON-over-TCP interface (apihandler.py for read
queries, commands.py for the client command set) and binds to 0.0.0.0:<port>.
Some commands carry dangerous defaults for someone running a node for fun or
learning: they send a *private key* to the node, expose configuration, or let
anyone clear the mempool.

This lab (a) builds a threat model of those unsafe defaults, and (b) includes a
small hardening *scanner* that flags risky patterns in source files so you can
see and fix them. It does NOT modify the node; it teaches you to recognise the
patterns and how a hardening patch should look.

Run with:  .venv/bin/python ./labs/10-insecure-defaults/threat_model.py
"""

import re
from dataclasses import dataclass, field


@dataclass
class Threat:
    name: str
    severity: str  # High / Medium / Low
    risky_pattern: str  # string that must appear in the source line
    rationale: str
    safe_guidance: str
    hit_lines: list = field(default_factory=list)


THREATS = [
    Threat(
        name="private-key-to-node signing",
        severity="High",
        risky_pattern="remote_tx_privkey",
        rationale=(
            "txsend() accepts a raw private key and forwards it to the node so "
            "the node can sign. Anyone who copies this pattern sends their key "
            "over the wire and loses custody of it."
        ),
        safe_guidance=(
            "Sign locally and broadcast only the signed transaction ("
            "BismuthClient.send / send_nogui style). Never send a private key "
            "to a node."
        ),
    ),
    Threat(
        name="key generation on the node",
        severity="High",
        risky_pattern="def keygen",
        rationale=(
            "keygen() has the node create/export keys. Doing wallet genesis on "
            "a remote node risks the key material living where you do not trust it."
        ),
        safe_guidance="Generate the wallet locally (wallet.der on your machine).",
    ),
    Threat(
        name="config disclosure",
        severity="Medium",
        risky_pattern="def api_getconfig",
        rationale=(
            "api_getconfig returns node configuration to any caller. Useful for "
            "ops, but on an internet-facing 0.0.0.0 node it leaks topology/"
            "settings."
        ),
        safe_guidance="Bind to 127.0.0.1 or gate sensitive read commands behind auth.",
    ),
    Threat(
        name="mempool wipe",
        severity="High",
        risky_pattern="def api_clearmempool",
        rationale=(
            "api_clearmempool lets any connected peer drop the local mempool. On "
            "an exposed node this is a denial-of-service / griefing vector."
        ),
        safe_guidance="Never expose mempool-control commands on a public interface; "
                      "require local/authenticated access.",
    ),
    Threat(
        name="bind-all-addresses",
        severity="Medium",
        risky_pattern="0.0.0.0",
        rationale=(
            "Listening on 0.0.0.0:<port> exposes JSON-over-TCP to the whole "
            "network. For a learning node this widens the attack surface."
        ),
        safe_guidance="Prefer 127.0.0.1 (loopback) unless peers genuinely need remote "
                      "access; understand what each exposed command can do.",
    ),
]


# Lines that merely *document* a risky pattern (e.g. this very file) should not
# be flagged when scanning arbitrary source. The scanner reports source files
# passed to it; the doc/README text is separate.
SCAN_EXTENSIONS = {".py"}


def scan_file(path, threats):
    """Scan one source file against the threat model; record hitting lines."""
    report = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        report[path] = [("<error>", str(exc))]
        return report
    for threat in threats:
        for lineno, line in enumerate(lines, 1):
            if threat.risky_pattern in line:
                threat.hit_lines.append((path, lineno, line.strip()))
    return report


def print_threat_model(threats):
    print("Threat model: unsafe defaults in apihandler.py / commands.py")
    print("=" * 72)
    for t in threats:
        print(f"\n[{t.severity.upper():6}] {t.name}")
        print(f"  pattern : {t.risky_pattern!r}")
        print(f"  why     : {t.rationale}")
        print(f"  fix     : {t.safe_guidance}")


def print_scan(threats):
    print("\nHardening scanner results")
    print("-" * 72)
    flagged = False
    for t in threats:
        for path, lineno, line in t.hit_lines:
            flagged = True
            print(f"  {path}:{lineno}  [{t.severity}] {t.name}")
            print(f"      {line}")
            print(f"      -> fix: {t.safe_guidance}")
    if not flagged:
        print("  (no risky patterns found in scanned files)")


def main():
    print_threat_model(THREATS)
    # Scan the real node sources so the lesson is grounded in actual code.
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.abspath(os.path.join(here, "..", ".."))
    targets = [os.path.join(repo, f) for f in ("commands.py", "apihandler.py")]
    for f in targets:
        scan_file(f, THREATS)
    print_scan(THREATS)


if __name__ == "__main__":
    main()
