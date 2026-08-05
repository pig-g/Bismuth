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