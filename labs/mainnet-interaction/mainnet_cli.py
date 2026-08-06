#!/usr/bin/env python3
"""Mainnet interaction CLI (read + local-signing trial send).

Talk to the real Bismuth mainnet. Reads are allowlisted; the only write is a
small trial transfer signed locally by BismuthClient (private key never sent).

Usage
-----
  <python> ./mainnet_cli.py status
  <python> ./mainnet_cli.py height
  <python> ./mainnet_cli.py block <height>
  <python> ./mainnet_cli.py balance <address>
  <python> ./mainnet_cli.py tx <txid>
  <python> ./mainnet_cli.py net probe    # Phase 0: per-seed network health
  <python> ./mainnet_cli.py wallet new <path>
  <python> ./mainnet_cli.py send --wallet <path> --to <addr> --amount <amt> [--op x] [--data y]

`send` prints its warning and asks for a confirmation phrase before broadcasting.
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bismuthclient.bismuthclient import BismuthClient  # noqa: E402
import mainnet_rpc  # noqa: E402
import net_probe  # noqa: E402

# Public Bismuth mainnet node (port 5658 is the node protocol port). One is
# enough for the CLI; BismuthClient can also be pointed at any reachable seed.
DEFAULT_SEED = "185.100.232.131:5658"


MAINNET_SEEDS = [
    "112.165.237.63:5658",
    "185.100.232.131:5658",
    "185.100.232.5:5658",
    "198.13.36.20:5658",
    "207.246.101.70:5658",
    "211.243.194.201:5658",
    "218.145.184.28:5658",
    "219.249.57.88:5658",
    "38.242.201.206:5658",
]


def make_client(wallet_file=None):
    return BismuthClient(servers_list=MAINNET_SEEDS, wallet_file=str(wallet_file or ""))


def probe_client(seed):
    """Fresh client pointed at exactly one seed (for per-seed diag polling)."""
    return BismuthClient(servers_list=[seed])


def print_json(value):
    print(json.dumps(redact(value), indent=2, default=str))


def redact(value):
    """Recursively remove full signatures / public keys from learner output."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in {"signature", "pubkey", "public_key"}:
                out[key] = "[REDACTED]"
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def cmd_status(client):
    print(mainnet_rpc.MAINNET_WARNING)
    print()
    rpc = mainnet_rpc.MainnetRPC(client)
    print_json(rpc.observe("statusjson"))


def cmd_height(client):
    print(mainnet_rpc.MAINNET_WARNING)
    print()
    rpc = mainnet_rpc.MainnetRPC(client)
    print(f"mainnet block height: {rpc.block_height()}")


def cmd_block(client, height):
    print(mainnet_rpc.MAINNET_WARNING)
    print()
    rpc = mainnet_rpc.MainnetRPC(client)
    print_json(rpc.observe("api_getblockfromheight", [int(height)]))


def cmd_balance(client, address):
    print(mainnet_rpc.MAINNET_WARNING)
    print()
    rpc = mainnet_rpc.MainnetRPC(client)
    print_json(rpc.observe("api_getbalance", [[address], 0]))


def cmd_tx(client, txid):
    print(mainnet_rpc.MAINNET_WARNING)
    print()
    rpc = mainnet_rpc.MainnetRPC(client)
    print_json(rpc.observe("api_gettransaction", [txid, True]))


def cmd_wallet_new(path):
    print(mainnet_rpc.MAINNET_WARNING)
    print()
    client = make_client(wallet_file=path)
    if not client.new_wallet(str(path)):
        print("error: could not create wallet", file=sys.stderr)
        return 1
    client.load_wallet(str(path))
    print(f"wallet created: {path}")
    print(f"address: {client.address}")
    print("\nOnly the public address is shown. The private key stays in this file on your machine.")


def cmd_net_probe():
    """Poll every public seed and print a network-health probe. Read-only."""
    result = net_probe.probe_all(probe_client, MAINNET_SEEDS)
    print(net_probe.report(result))
    if result.diverging_seeds():
        return 2
    return 0


def cmd_net_health():
    """Phase 1: print a 0-100 health score + grade. Read-only."""
    result = net_probe.probe_all(probe_client, MAINNET_SEEDS)
    h = net_probe.health_score(result)
    print(f"Health score: {h['score']}/100 ({h['grade']})")
    for r in h["reasons"]:
        print(f"  - {r}")
    if h["score"] < 50:
        return 2
    return 0


def cmd_net_fork_check(height):
    """Phase 2: compare block hash at height across seeds to detect a fork. Read-only."""
    report = net_probe.fork_check(probe_client, MAINNET_SEEDS, height)
    print(net_probe.fork_report(report))
    if report["fork"]:
        return 2
    return 0


def cmd_net_mine_stats(height, seed=None):
    """Phase 3: block-interval + difficulty + mempool stats from one seed. Read-only."""
    seed = seed or MAINNET_SEEDS[0]
    stats = net_probe.mine_stats(probe_client, seed, height)
    print(net_probe.mine_report(stats))
    return 0


def cmd_net_record(out_dir, interval, rounds, seed=None):
    """Phase 4: record metric samples to a local JSONL file on an interval."""
    import os
    import time
    seed = seed or MAINNET_SEEDS[0]
    out_dir = out_dir or os.path.join(os.path.expanduser("~"), ".bismuth-net")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, time.strftime("%Y-%m-%d") + ".jsonl")
    print(f"Recording to {path} every {interval}s for {rounds} rounds (seed {seed})...")
    for i in range(int(rounds)):
        sample = net_probe.record_sample(probe_client, seed)
        net_probe.append_jsonl(path, sample)
        print(f"  [{i+1}/{rounds}] ts={sample['ts']} height={sample.get('block_height')} diff={sample.get('difficulty')}")
        if i + 1 < int(rounds):
            time.sleep(float(interval))
    return 0


def cmd_net_report(path, metric=None):
    """Phase 4: analyze a recorded JSONL dataset and print a research report."""
    rows = net_probe.load_jsonl(path)
    print(net_probe.report_series(rows, metric=metric))
    return 0


def cmd_net_ban(logfile):
    """Phase 5: analyze an observer-node ban log (read from a local file)."""
    with open(logfile, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    events = net_probe.parse_ban_log(text)
    print(net_probe.ban_report(events))


def cmd_net_observe(logfile, n=20):
    """One-shot observer snapshot from a node log: bans + peers + consensus +
    recent blocks (height:hash from ip). Prints to stdout only; no file writing."""
    with open(logfile, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    print(net_probe.observe(text, n=n))
    return 0
    return 0


def cmd_send(wallet, to, amount, op="", data="", assume_yes=False):
    print(mainnet_rpc.MAINNET_WARNING)
    print()
    rpc = mainnet_rpc.MainnetRPC(make_client(wallet_file=wallet))
    # parse/coerce against the small trial limit before touching anything
    recipient, amt, operation, data = mainnet_rpc.parse_send_args(
        "send {} {} {} {}".format(to, amount, op, data)
    )
    print(f"Sending {amt} real BIS to {recipient} (operation={operation!r}, data={data!r})")
    print(f"This is REAL BIS on MAINNET and is irreversible.")
    if not assume_yes:
        answer = input('Type "send" to confirm: ').strip()
        if answer.lower() != "send":
            print("aborted - nothing sent")
            return 1
    try:
        txid = rpc.sign_and_send(
            recipient, amt, operation=operation, data=data, confirm=True
        )
    except mainnet_rpc.MainnetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"\nbroadcast transaction: {txid}")
    return 0


def main(argv):
    if len(argv) < 1:
        print(__doc__)
        return 1
    command = argv[0]
    args = argv[1:]
    try:
        if command == "status":
            return cmd_status(make_client()) or 0
        if command == "height":
            return cmd_height(make_client()) or 0
        if command == "block":
            return cmd_block(make_client(), args[0]) or 0
        if command == "balance":
            return cmd_balance(make_client(), args[0]) or 0
        if command == "tx":
            return cmd_tx(make_client(), args[0]) or 0
        if command == "wallet" and args and args[0] == "new":
            return cmd_wallet_new(args[1]) or 0
        if command == "send":
            return cmd_send(**parse_send_options(args)) or 0
        if command == "net" and args and args[0] == "probe":
            return cmd_net_probe() or 0
        if command == "net" and args and args[0] == "health":
            return cmd_net_health() or 0
        if command == "net" and args and args[0] == "fork-check":
            if len(args) < 2:
                raise ValueError("fork-check requires a HEIGHT\nusage: net fork-check <height>")
            return cmd_net_fork_check(int(args[1])) or 0
        if command == "net" and args and args[0] == "mine-stats":
            if len(args) < 2:
                raise ValueError("mine-stats requires a HEIGHT\nusage: net mine-stats <height> [seed]")
            seed = args[2] if len(args) > 2 else None
            return cmd_net_mine_stats(int(args[1]), seed) or 0
        if command == "net" and args and args[0] == "record":
            opts = parse_net_opts(args[1:])
            return cmd_net_record(opts["out"], opts["interval"], opts.get("rounds", 5), opts.get("seed")) or 0
        if command == "net" and args and args[0] == "report":
            opts = parse_net_opts(args[1:])
            file = opts.get("from_json")
            if not file:
                raise ValueError("report requires --from-json FILE")
            return cmd_net_report(file, opts.get("metric")) or 0
        if command == "net" and args and args[0] == "ban-analyze":
            if len(args) < 2:
                raise ValueError("ban-analyze requires a LOGFILE\nusage: net ban-analyze <node.log>")
            return cmd_net_ban(args[1]) or 0
        if command == "net" and args and args[0] == "observe":
            if len(args) < 2:
                raise ValueError("observe requires a NODE_LOG\nusage: net observe <node.log> [--n N]")
            n = 20
            if "--n" in args:
                n = int(args[args.index("--n") + 1])
            return cmd_net_observe(args[1], n=n) or 0
        print(f"unknown command: {command}", file=sys.stderr)
        return 1
    except (IndexError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # wrapped for CLI friendliness
        print(f"error: {exc}", file=sys.stderr)
        return 1


def parse_net_opts(args):
    """Parse net subcommand options: --out, --interval, --rounds, --seed, --from-json, --metric."""
    opts = {"out": None, "interval": 30, "rounds": 5, "from_json": None, "metric": None, "seed": None}
    it = iter(args)
    for token in it:
        if token == "--out":
            opts["out"] = next(it)
        elif token == "--interval":
            opts["interval"] = int(next(it))
        elif token == "--rounds":
            opts["rounds"] = int(next(it))
        elif token == "--seed":
            opts["seed"] = next(it)
        elif token == "--from-json":
            opts["from_json"] = next(it)
        elif token == "--metric":
            opts["metric"] = next(it)
    return opts


def parse_send_options(args):
    opts = {}
    it = iter(args)
    for token in it:
        if token == "--wallet":
            opts["wallet"] = next(it)
        elif token == "--to":
            opts["to"] = next(it)
        elif token == "--amount":
            opts["amount"] = Decimal(next(it))
        elif token == "--op":
            opts["op"] = next(it)
        elif token == "--data":
            opts["data"] = next(it)
        elif token == "--yes":
            opts["assume_yes"] = True
    for required in ("wallet", "to", "amount"):
        if required not in opts:
            raise ValueError(f"send requires --{required}")
    opts.setdefault("op", "")
    opts.setdefault("data", "")
    opts.setdefault("assume_yes", False)
    return opts


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
