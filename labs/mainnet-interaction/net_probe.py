#!/usr/bin/env python3
"""Phase 0: per-seed diagnostic probe for the Bismuth mainnet.

Polls multiple public seeds individually, each through its own client, and
reports height / protocol-version / consensus / difficulty / staleness so a
learner can see at a glance whether the network is healthy and in consensus.

Safety: strictly read-only. Every command goes through a client injected from
outside (a fake in tests, a BismuthClient in production) and only safe RPCs
are issued. No wallets, no keys, no writes.
"""

from dataclasses import dataclass, field

# Read-only RPCs we may issue per seed. Mirrors mainnet_rpc allowlist.
ALLOWED_RPCS = {"getversion", "statusjson"}

# Height skew (blocks) above which we flag a seed as diverging from consensus.
DIVERGENCE_HEIGHT = 2


@dataclass
class SeedProbe:
    seed: str
    version: str | None = None
    blocks: int | None = None
    difficulty: float | None = None
    consensus: int | None = None
    consensus_percent: float | None = None
    last_block_ago: float | None = None
    connections: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class ProbeResult:
    probes: list = field(default_factory=list)

    def height_of(self, seed):
        for p in self.probes:
            if p.seed == seed and p.ok:
                return p.blocks
        return None

    def consensus_height(self):
        """Most common non-None blocks height across healthy probes, else None."""
        heights = sorted(p.blocks for p in self.probes if p.ok and p.blocks is not None)
        if not heights:
            return None
        from collections import Counter
        return Counter(heights).most_common(1)[0][0]

    def versions(self):
        return {p.version for p in self.probes if p.ok and p.version}

    def diverging_seeds(self, tolerance=DIVERGENCE_HEIGHT):
        """Seeds whose height differs from the consensus height by > tolerance."""
        consensus = self.consensus_height()
        if consensus is None:
            return []
        return [
            p.seed
            for p in self.probes
            if p.ok and p.blocks is not None and abs(p.blocks - consensus) > tolerance
        ]

    @property
    def version_mismatch(self) -> bool:
        return len(self.versions()) > 1


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def probe_seed(client_factory, seed, *, allowed=ALLOWED_RPCS):
    """Poll one seed through a fresh client for the health RPCs.

    `client_factory(seed)` must return an object exposing `.command(cmd, opts)`
    and pointing at the given seed. Uses only commands in `allowed`.
    """
    probe = SeedProbe(seed=seed)
    try:
        client = client_factory(seed)
        version = client.command("getversion")
        if "getversion" in allowed:
            probe.version = str(version) if version else None
        status = client.command("statusjson") if "statusjson" in allowed else {}
        if isinstance(status, dict):
            probe.blocks = _safe_int(status.get("blocks"))
            probe.difficulty = _safe_float(status.get("difficulty"))
            probe.consensus = _safe_int(status.get("consensus"))
            probe.consensus_percent = _safe_float(status.get("consensus_percent"))
            probe.last_block_ago = _safe_float(status.get("last_block_ago"))
            probe.connections = _safe_int(status.get("connections"))
    except Exception as exc:  # per-seed isolation: one bad seed must not kill all
        probe.error = f"{type(exc).__name__}: {exc}"
    return probe


def probe_all(client_factory, seeds, *, allowed=ALLOWED_RPCS):
    """Poll every seed and assemble a ProbeResult (sequential; safe)."""
    result = ProbeResult()
    for seed in seeds:
        result.probes.append(probe_seed(client_factory, seed, allowed=allowed))
    return result


def report(result: ProbeResult, *, height_tolerance=DIVERGENCE_HEIGHT):
    """Human-readable diagnostic report + machine-readable flags."""
    lines = []
    consensus = result.consensus_height()
    lines.append(f"Consensus height: {consensus}")
    for p in result.probes:
        if not p.ok:
            lines.append(f"  [ERR ] {p.seed:24} {p.error}")
            continue
        skew = "" if not consensus or p.blocks is None else f" skew={p.blocks - consensus:+d}"
        lines.append(
            f"  [ OK ] {p.seed:24} h={p.blocks} v={p.version} "
            f"diff={p.difficulty} cons={p.consensus_percent}% last={p.last_block_ago:.0f}s{skew}"
        )
    diverging = result.diverging_seeds(tolerance=height_tolerance)
    if diverging:
        lines.append(f"DIVERGENCE: seeds far from consensus: {', '.join(diverging)}")
    else:
        lines.append("DIVERGENCE: none (all within tolerance)")
    if result.version_mismatch:
        lines.append(f"VERSION MISMATCH: {sorted(result.versions())}")
    else:
        versions = result.versions()
        lines.append(f"VERSION: uniform ({', '.join(sorted(versions)) if versions else 'n/a'})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 1: network health score (0-100) + grade.
# ---------------------------------------------------------------------------

# A fresh, healthy Bismuth mainnet targets ~60s blocks. Voting basis:
# if a block was produced too long ago we suspect a stall.
HEALTHY_LAST_BLOCK_S = 180
SUSPICIOUS_LAST_BLOCK_S = 600

# Deduct points for a low consensus percentage.

def health_score(result: ProbeResult) -> dict:
    """Returns {score, grade, reasons, checks}.

    Score starts at 100 and deducts for concrete problems we can observe
    from a ProbeResult. `reasons` lists human-readable findings.
    """
    score = 100
    reasons = []

    probes = [p for p in result.probes if p.ok]
    if not probes:
        return {"score": 0, "grade": "SUSPICIOUS",
                "reasons": ["no reachable seeds"], "checks": {}}

    # 1. staleness: any seed beyond healthy freshness deducts.
    stalest = max((p.last_block_ago or 0) for p in probes)
    if stalest > SUSPICIOUS_LAST_BLOCK_S:
        score -= 25
        reasons.append(f"stall: {stalest:.0f}s since last block")
    elif stalest > HEALTHY_LAST_BLOCK_S:
        score -= 10
        reasons.append(f"old: {stalest:.0f}s since last block")

    # 2. consensus_percent: low agreement among connected peers.
    lo = min(p.consensus_percent for p in probes if p.consensus_percent is not None) or 0
    if lo < 40:
        score -= 15
        reasons.append(f"low consensus_percent: {lo:.0f}%")
    elif lo < 60:
        score -= 5
        reasons.append(f"moderate consensus_percent: {lo:.0f}%")

    # 3. divergence: seeds disagreeing on height.
    if result.diverging_seeds():
        score -= 20
        reasons.append(f"divergence: {', '.join(result.diverging_seeds())}")

    # 4. version mismatch: heterogeneous protocol versions (fork split risk).
    if result.version_mismatch:
        score -= 10
        reasons.append(f"version mismatch: {sorted(result.versions())}")

    score = max(0, min(100, score))
    if score >= 80:
        grade = "HEALTHY"
    elif score >= 50:
        grade = "DEGRADED"
    else:
        grade = "SUSPICIOUS"

    return {"score": score, "grade": grade, "reasons": reasons,
            "checks": {
                "stalest_last_block_s": stalest,
                "consensus_percent_min": lo,
                "n_seeds_ok": len(probes),
                "diverging": result.diverging_seeds(),
                "versions": sorted(result.versions()),
            }}


# ---------------------------------------------------------------------------
# Phase 2: fork detection via cross-seed block-hash comparison.
# ---------------------------------------------------------------------------

def fork_check(client_factory, seeds, height, *, check_height=DIVERGENCE_HEIGHT):
    """Compare the block hash at `height` across seeds to detect a chain split.

    Returns a ForkReport with the hashes seen per seed and whether more than one
    distinct hash exists (a potential fork / inconsistent history).
    """
    hashes = {}     # seed -> hash
    errors = {}     # seed -> error
    for seed in seeds:
        try:
            c = client_factory(seed)
            block = c.command("api_getblockfromheight", [height])
            if isinstance(block, dict):
                # response shaped {str(height): {block_height, block_hash, ...}}
                sub = block.get(str(height)) or block.get(height)
                h = (sub or {}).get("block_hash") if isinstance(sub, dict) else None
                hashes[seed] = h
            else:
                hashes[seed] = None
        except Exception as exc:
            errors[seed] = f"{type(exc).__name__}: {exc}"
    distinct = {h for h in hashes.values() if h}
    split = len(distinct) > 1
    return {
        "height": height,
        "hashes": hashes,
        "errors": errors,
        "distinct_hashes": sorted(distinct) if distinct else [],
        "fork": split,
    }


def fork_report(report: dict) -> str:
    lines = [f"Fork check at height {report['height']}:"]
    for seed, h in report["hashes"].items():
        lines.append(f"  {seed:24} {h or 'n/a'}")
    for seed, err in report["errors"].items():
        lines.append(f"  [ERR] {seed:24} {err}")
    if report["fork"]:
        lines.append("FORK: seeds report different block hashes (potential chain split)")
    else:
        lines.append("FORK: none (all seeds agree on the same block hash)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 3: mining / mempool diagnostics.
# ---------------------------------------------------------------------------

# Bismuth targets ~60s block generation.
TARGET_BLOCK_S = 60.0


def safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_blockrange(raw):
    """Turn api_getblockrange response (str JSON or dict) into {height: mining tx}."""
    import ast
    if isinstance(raw, str):
        try:
            raw = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, b in raw.items():
        if isinstance(b, dict):
            out[str(k)] = b.get("mining_tx") or {}
    return out


def mine_stats(client_factory, seed, height, *, n_blocks=10):
    """Block-interval stats (mean / spread vs 60s) + current difficulty + mempool
    load, all queried read-only from a single seed."""
    start = height - n_blocks + 1
    start = max(start, 1)
    raw = client_factory(seed).command("api_getblockrange", [start, height])
    blocks = _parse_blockrange(raw)
    ts = [b.get("timestamp") for b in blocks.values()]
    timestamps = sorted(safe_float(t) for t in ts if safe_float(t) is not None)

    intervals = []
    for i in range(1, len(timestamps)):
        d = timestamps[i] - timestamps[i - 1]
        if d > 0:
            intervals.append(d)

    stats = {"seed": seed, "n_blocks": len(timestamps)}
    if intervals:
        mean = sum(intervals) / len(intervals)
        spread = max(intervals) - min(intervals)
        stats["mean_interval_s"] = round(mean, 1)
        stats["min_interval_s"] = round(min(intervals), 1)
        stats["max_interval_s"] = round(max(intervals), 1)
        offset = mean - TARGET_BLOCK_S
        stats["offset_vs_target_s"] = round(offset, 1)
        stats["diff_mean_s"] = round(spread, 1)
    else:
        stats["mean_interval_s"] = None

    # difficulty / mempool from diffgetjson + mpgetjson on the same seed.
    try:
        diff = client_factory(seed).command("diffgetjson")
        if isinstance(diff, dict):
            stats["difficulty"] = safe_float(diff.get("difficulty"))
            stats["block_time"] = safe_float(diff.get("block_time"))
            stats["time_to_generate"] = safe_float(diff.get("time_to_generate"))
    except Exception:
        pass
    try:
        mp = client_factory(seed).command("mpgetjson")
        stats["mempool_txs"] = len(mp) if isinstance(mp, (list, dict)) else None
    except Exception:
        pass
    return stats


def mine_report(stats: dict) -> str:
    lines = [f"Mining stats @ seed {stats['seed']} (last {stats.get('n_blocks')} blocks):"]
    mi = stats.get("mean_interval_s")
    if mi is not None:
        off = stats.get("offset_vs_target_s")
        lines.append(f"  mean block interval: {mi}s (target ~{TARGET_BLOCK_S:.0f}s, offset {off:+.0f}s)")
        lines.append(f"  interval range: {stats.get('min_interval_s')}s - {stats.get('max_interval_s')}s (spread {stats.get('diff_mean_s')}s)")
    else:
        lines.append("  mean block interval: n/a (no timestamps)")
    if stats.get("difficulty") is not None:
        lines.append(f"  difficulty: {stats['difficulty']:.4f}  block_time: {stats.get('block_time')}s  time_to_generate: {stats.get('time_to_generate')}s")
    mp = stats.get("mempool_txs")
    lines.append(f"  mempool pending txs: {mp if mp is not None else 'n/a'}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 4: time-series research dataset (local JSONL recording + report).
# ---------------------------------------------------------------------------

import json as _json
import time as _time


def record_sample(client_factory, seed, height=None, *, n_blocks=10, extra=None):
    """Collect one timestamped sample of key metrics (read-only)."""
    probe = probe_seed(client_factory, seed)
    h = height or probe.blocks or 0
    try:
        mine = mine_stats(client_factory, seed, h, n_blocks=n_blocks)
    except Exception:
        mine = {}
    sample = {
        "ts": round(_time.time(), 3),
        "seed": seed,
        "version": probe.version,
        "block_height": probe.blocks,
        "consensus_percent": probe.consensus_percent,
        "last_block_ago": probe.last_block_ago,
        "difficulty": mine.get("difficulty") if isinstance(mine, dict) else None,
        "mean_interval_s": mine.get("mean_interval_s") if isinstance(mine, dict) else None,
        "mempool_txs": mine.get("mempool_txs") if isinstance(mine, dict) else None,
    }
    if extra:
        sample.update(extra)
    return sample


def append_jsonl(path, sample):
    """Atomically append one sample as a JSON line. Local file only."""
    import os
    path = str(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(_json.dumps(sample) + "\n")
    return path


def load_jsonl(path):
    """Read a JSONL file into a list of dicts."""
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(_json.loads(line))
                except _json.JSONDecodeError:
                    continue
    return rows


def _pick(row, metric, default=None):
    v = row.get(metric)
    if isinstance(v, (int, float)):
        return v
    return default


def report_series(rows, metric=None):
    """Analyze a recorded series. If metric given, report just that column; otherwise
    summarise all known numeric metrics across healthy rows."""
    import statistics as st

    if not rows:
        return "report: no recorded data"

    if metric:
        vals = [v for v in (_pick(r, metric) for r in rows) if v is not None]
        if not vals:
            return f"report: metric '{metric}' has no numeric data"
        return (
            f"Metric: {metric}  ({len(rows)} samples)\n"
            f"  min={min(vals):.3f}  max={max(vals):.3f}  mean={st.mean(vals):.3f}  "
            f"latest={vals[-1]:.3f}"
        )

    metrics = ["block_height", "consensus_percent", "last_block_ago", "difficulty", "mean_interval_s", "mempool_txs"]
    lines = [f"Research report: {len(rows)} samples"]
    for m in metrics:
        vals = [v for v in (_pick(r, m) for r in rows) if v is not None]
        if not vals:
            continue
        trend = ""
        if len(vals) >= 2:
            delta = vals[-1] - vals[0]
            arrow = "↗" if delta > 0 else ("↘" if delta < 0 else "→")
            trend = f"  first={vals[0]:.3f} last={vals[-1]:.3f} {arrow}"
        lines.append(f"  {m}: min={min(vals):.3f} max={max(vals):.3f} mean={st.mean(vals):.3f}{trend}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 5: observer-node banlog analysis.
# ---------------------------------------------------------------------------

# Known ban reason catalogue (mirrors warnings seen in node.py / peershandler.py /
# digest.py / worker.py). Weight is the warning score each reason contributes.
BAN_REASONS = {
    "Failed to deliver the longest chain": 1,
    "Forked": 2,
    "Rollback": 2,
    "Operation timeout": 2,
    "Rejected block": 2,
    "Consensus deviation too high": 10,
}


def parse_ban_log(text):
    """Parse observer-node log text into ban/warning events.

    Matches the peer-handler log lines, e.g.:
      Added 2 warning(s) to 1.2.3.4: Forked (4 / 30)
      1.2.3.4 is banned: Consensus deviation too high
    Returns a dict with lists of events.
    """
    import re
    events = []
    warning_re = re.compile(r"Added (\d+) warning\(s\) to ([\d.]+): (.+?) \((\d+) / (\d+)\)")
    ban_re = re.compile(r"([\d.]+) is banned: (.+)")
    for line in text.splitlines():
        m = warning_re.search(line)
        if m:
            events.append({
                "type": "warning",
                "count": int(m.group(1)),
                "ip": m.group(2),
                "reason": m.group(3).strip(),
                "running": int(m.group(4)),
                "threshold": int(m.group(5)),
            })
            continue
        m = ban_re.search(line)
        if m:
            events.append({"type": "ban", "ip": m.group(1), "reason": m.group(2).strip()})
    return events


def ban_report(events, *, threshold=30):
    """Summarize parsed ban events: bans by reason (the catalogue) and warnings."""
    bans = [e for e in events if e["type"] == "ban"]
    warnings = [e for e in events if e["type"] == "warning"]
    lines = [f"Ban analysis: {len(events)} events ({len(bans)} bans, {len(warnings)} warnings)"]
    if not events:
        lines.append("  no ban activity recorded")
        return "\n".join(lines)

    # bans grouped by reason -> the catalogue in practice
    from collections import Counter
    ban_reasons = Counter(e["reason"] for e in bans)
    lines.append("  Bans by reason:")
    if ban_reasons:
        for reason, count in ban_reasons.most_common():
            known = "" if reason in BAN_REASONS else " (unknown)"
            lines.append(f"    - {reason} x{count}{known}")
    else:
        lines.append("    (none)")

    # warning counts per IP -> who is closest to being banned
    warn_by_ip = Counter(e["ip"] for e in warnings)
    lines.append("  Warning accumulation (top IPs, threshold {0}):".format(threshold))
    for ip, count in warn_by_ip.most_common(5):
        lines.append(f"    - {ip}: {count} warnings")

    # consensus health: what blocked consensus formation (why did bans happen)
    lines.append("  Consensus blockers observed:")
    blockers = set(e["reason"] for e in bans + warnings)
    if blockers:
        for b in sorted(blockers):
            lines.append(f"    - {b}")
    else:
        lines.append("    (none)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# network observe: one-shot read-only snapshot for manual inspection (stdout only,
# no file writing). Mirrors observer_snapshot.sh for the CLI.
# ---------------------------------------------------------------------------
def observe(logtext, n=20):
    """Build a human-readable one-shot snapshot from observer-node log text.

    Returns a multi-line string (stdout-friendly). No files are written.
    Sections: bans, peer health, consensus opinion, recent blocks (height:hash from
    ip) + a block-source tally. n = how many recent blocks to show.
    """
    import re
    from collections import Counter
    lines = []

    # --- bans ---
    events = parse_ban_log(logtext)
    lines.append(ban_report(events))

    # --- peer health from status lines ---
    def last_num(pattern, group=0):
        ms = re.findall(pattern, logtext)
        return ms[-1] if ms else "n/a"
    known = last_num(r"Known Peers: (\d+)")
    out = last_num(r"Number of Outbound connections: (\d+)")
    nodes = last_num(r"Total number of nodes: (\d+)")
    cons = last_num(r"Consensus height: (\d+)")
    pct = last_num(r"Consensus height: \d+ = ([0-9.]+%)")
    lines.append("")
    lines.append("--- Peer health ---")
    lines.append(f"KnownPeers={known}  Outbound={out}  ConsensusNodes={nodes}")
    lines.append(f"ConsensusHeight={cons}  ConsensusPct={pct if pct!='n/a' else pct}")
    op = last_num(r"Last block opinion: (.*)")
    lines.append(f"Consensus opinion: {op}" if op != "n/a" else "Consensus opinion: n/a")

    # --- recent blocks (height:hash from ip) ---
    blocks = re.findall(r"Valid block: (\d+): ([0-9a-f]+) .*? digestion from ([0-9.]+)", logtext)
    lines.append("")
    lines.append(f"--- Last {n} blocks (height:hash from ip) ---")
    if blocks:
        for (h, hsh, ip) in blocks[-n:]:
            lines.append(f"  {h}: {hsh} from {ip}")
        src = Counter(ip for (_h, _hs, ip) in blocks[-n:])
        lines.append("Block sources (last {}):".format(n))
        for ip, c in src.most_common():
            lines.append(f"    {ip}: {c}")
        dom = src.most_common(1)
        if dom and dom[0][1] >= int(n * 0.7):
            lines.append(f"NOTE: {dom[0][0]} supplied {dom[0][1]}/{n} blocks (single-provider dominant)")
    else:
        lines.append("  (no valid-block events found)")

    # --- difficulty ---
    diffs = re.findall(r"Current difficulty: ([0-9.]+)", logtext)
    if diffs:
        lines.append(f"Difficulty: {diffs[-1]}")
    return "\n".join(lines)
