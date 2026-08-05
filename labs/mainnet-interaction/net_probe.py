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