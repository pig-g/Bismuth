import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LAB = REPO_ROOT / "labs" / "mainnet-interaction"


def load():
    spec = importlib.util.spec_from_file_location("net_probe", LAB / "net_probe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


np = load()


class FakeClient:
    def __init__(self, version="mainnet0023", status=None, error=None):
        self.version = version
        self.status = status or {}
        self.error = error
        self.commands = []

    def command(self, cmd, opts=None):
        self.commands.append((cmd, opts))
        if cmd == "getversion":
            if self.error == "getversion":
                raise RuntimeError("down")
            return self.version
        if cmd == "statusjson":
            if self.error == "status":
                raise RuntimeError("down")
            return self.status
        raise AssertionError("unexpected command: " + cmd)


STATUS_OK = {
    "blocks": 1000, "difficulty": 88.1, "consensus": 1000, "consensus_percent": 80.0,
    "last_block_ago": 10, "connections": 4,
}


def fake_factory(spec):
    def factory(seed):
        return spec[seed]
    return factory


def test_probe_seed_captures_fields():
    c = FakeClient(version="mainnet0022", status=dict(STATUS_OK, blocks=1005))
    p = np.probe_seed(lambda seed: c, "seed1:5658")
    assert p.ok
    assert p.seed == "seed1:5658"
    assert p.version == "mainnet0022"
    assert p.blocks == 1005
    assert p.difficulty == 88.1
    assert p.consensus_percent == 80.0
    assert p.last_block_ago == 10
    cmds = {c for c, _ in c.commands}
    assert cmds <= {"getversion", "statusjson"}


def test_consensus_height_is_most_common():
    seeds = {
        "a": FakeClient(status=dict(STATUS_OK, blocks=1000)),
        "b": FakeClient(status=dict(STATUS_OK, blocks=1000)),
        "c": FakeClient(status=dict(STATUS_OK, blocks=1000)),
        "d": FakeClient(status=dict(STATUS_OK, blocks=990)),
    }
    r = np.probe_all(fake_factory(seeds), list(seeds))
    assert r.consensus_height() == 1000


def test_divergence_flags_straggler():
    seeds = {
        "a": FakeClient(status=dict(STATUS_OK, blocks=1000)),
        "b": FakeClient(status=dict(STATUS_OK, blocks=1000)),
        "c": FakeClient(status=dict(STATUS_OK, blocks=1000)),
        "straggler": FakeClient(status=dict(STATUS_OK, blocks=990)),
    }
    r = np.probe_all(fake_factory(seeds), list(seeds))
    assert r.diverging_seeds() == ["straggler"]


def test_no_divergence_when_uniform():
    seeds = {
        "a": FakeClient(status=dict(STATUS_OK, blocks=1000)),
        "b": FakeClient(status=dict(STATUS_OK, blocks=1001)),
    }
    r = np.probe_all(fake_factory(seeds), list(seeds))
    assert r.diverging_seeds() == []


def test_version_mismatch_detected():
    seeds = {
        "a": FakeClient(version="mainnet0023"),
        "b": FakeClient(version="mainnet0022"),
    }
    r = np.probe_all(fake_factory(seeds), list(seeds))
    assert r.version_mismatch is True
    assert r.versions() == {"mainnet0023", "mainnet0022"}


def test_single_seed_failure_is_isolated():
    seeds = {
        "ok1": FakeClient(status=dict(STATUS_OK, blocks=1000)),
        "ok2": FakeClient(status=dict(STATUS_OK, blocks=1000)),
        "down": FakeClient(error="status"),
    }
    r = np.probe_all(fake_factory(seeds), list(seeds))
    assert not r.height_of("down")
    assert r.height_of("ok1") == 1000
    down = [p for p in r.probes if p.seed == "down"][0]
    assert not down.ok
    assert down.error


def test_report_contains_flags():
    seeds = {
        "a": FakeClient(version="mainnet0023", status=dict(STATUS_OK, blocks=1000)),
        "b": FakeClient(version="mainnet0022", status=dict(STATUS_OK, blocks=990)),
    }
    r = np.probe_all(fake_factory(seeds), list(seeds))
    txt = np.report(r)
    assert "DIVERGENCE" in txt
    assert "VERSION MISMATCH" in txt
    assert "Consensus height" in txt


def _healthy_result():
    seeds = {
        "a": FakeClient(version="mainnet0023", status=dict(STATUS_OK)),
        "b": FakeClient(version="mainnet0023", status=dict(STATUS_OK)),
        "c": FakeClient(version="mainnet0023", status=dict(STATUS_OK)),
    }
    return np.probe_all(fake_factory(seeds), list(seeds))


def test_health_score_healthy():
    r = _healthy_result()  # STATUS_OK: blocks=1000, last=10s, cons=80%, uniform version
    h = np.health_score(r)
    assert h["score"] == 100
    assert h["grade"] == "HEALTHY"
    assert not h["reasons"]


def test_health_score_deducts_on_stall():
    seeds = {
        "a": FakeClient(status=dict(STATUS_OK, last_block_ago=900)),
        "b": FakeClient(status=dict(STATUS_OK)),
    }
    r = np.probe_all(fake_factory(seeds), list(seeds))
    h = np.health_score(r)
    assert h["score"] < 100
    assert any("stall" in x for x in h["reasons"])
    assert h["grade"] != "HEALTHY"


def test_health_score_deducts_on_divergence_and_version():
    seeds = {
        "a": FakeClient(version="mainnet0023", status=dict(STATUS_OK, blocks=1000)),
        "b": FakeClient(version="mainnet0022", status=dict(STATUS_OK, blocks=990)),
    }
    r = np.probe_all(fake_factory(seeds), list(seeds))
    h = np.health_score(r)
    assert h["score"] <= 70  # 20 divergence + 10 version
    assert any("divergence" in x for x in h["reasons"])
    assert any("version mismatch" in x for x in h["reasons"])


def test_health_score_no_seeds():
    r = np.ProbeResult()
    h = np.health_score(r)
    assert h["score"] == 0
    assert h["grade"] == "SUSPICIOUS"


def test_fork_check_agrees():
    block = {"4928852": {"block_height": 4928852, "block_hash": "hashA"}}
    seeds = {"s1": FakeClient(), "s2": FakeClient()}
    # FakeClient.command doesn't handle api_getblockfromheight, so stub it:
    for s in seeds.values():
        def _blk(cmd, opts=None, _b=block):
            return _b if cmd == "api_getblockfromheight" else FakeClient.command(s, cmd, opts)
        s.command = _blk
    rep = np.fork_check(fake_factory(seeds), list(seeds), 4928852)
    assert rep["fork"] is False
    assert set(rep["hashes"].values()) == {"hashA"}


def test_fork_check_detects_split():
    seeds = {
        "s1": FakeClient(),
        "s2": FakeClient(),
    }
    block_a = {"4928852": {"block_hash": "hashA"}}
    block_b = {"4928852": {"block_hash": "hashB"}}
    def fa(cmd, opts=None):
        return block_a if cmd == "api_getblockfromheight" else FakeClient.command(seeds["s1"], cmd, opts)
    def fb(cmd, opts=None):
        return block_b if cmd == "api_getblockfromheight" else FakeClient.command(seeds["s2"], cmd, opts)
    seeds["s1"].command = fa
    seeds["s2"].command = fb
    rep = np.fork_check(fake_factory(seeds), list(seeds), 4928852)
    assert rep["fork"] is True
    assert len(rep["distinct_hashes"]) == 2


def test_fork_report_marks_fork():
    seeds = {"s1": FakeClient(), "s2": FakeClient()}
    def fa(cmd, opts=None):
        return {"h": {"block_hash": "A"}}
    def fb(cmd, opts=None):
        return {"h": {"block_hash": "B"}}
    seeds["s1"].command = fa
    seeds["s2"].command = fb
    rep = np.fork_check(fake_factory(seeds), list(seeds), 5)
    txt = np.fork_report(rep)
    assert "FORK" in txt


class FakeMinerClient(FakeClient):
    """FakeClient that also answers the Phase 3/4 mining RPCs."""
    def __init__(self, blocks, difficulty=None, mempool=3, status=None):
        super().__init__(status=status or {"blocks": 1000, "consensus_percent": 80.0, "last_block_ago": 10})
        self._blocks = blocks
        self.difficulty = difficulty or {"difficulty": 87.9, "block_time": 63.2, "time_to_generate": 32.6}
        self.mempool = mempool

    def command(self, cmd, opts=None):
        if cmd == "api_getblockrange":
            return self._blocks
        if cmd == "diffgetjson":
            return self.difficulty
        if cmd == "mpgetjson":
            return [1] * self.mempool
        return super().command(cmd, opts)


def _sample_blocks(base=1000.0, n=5):
    """Blocks spaced ~10s apart so mean interval is computable and deterministic."""
    return {str(base + i): {"mining_tx": {"timestamp": base + i * 10.0}} for i in range(n)}


def test_mine_stats_computes_intervals():
    blocks = _sample_blocks(n=5)
    c = FakeMinerClient(blocks)
    s = np.mine_stats(lambda seed: c, "seed", 1040, n_blocks=5)
    assert s["mean_interval_s"] == 10.0
    assert s["n_blocks"] == 5
    assert s["mempool_txs"] == 3
    assert s["difficulty"] == 87.9


def test_mine_stats_offset_vs_target():
    blocks = _sample_blocks(n=4)
    c = FakeMinerClient(blocks)
    s = np.mine_stats(lambda seed: c, "s", 1030, n_blocks=4)
    assert s["offset_vs_target_s"] == -50.0


def test_mine_stats_handles_empty():
    c = FakeMinerClient({})
    s = np.mine_stats(lambda seed: c, "s", 100, n_blocks=10)
    assert s["mean_interval_s"] is None
    assert "n/a" in np.mine_report(s)


def test_mine_report_contains_fields():
    blocks = _sample_blocks(n=5)
    c = FakeMinerClient(blocks)
    s = np.mine_stats(lambda seed: c, "seed", 1040, n_blocks=5)
    txt = np.mine_report(s)
    assert "mean block interval" in txt
    assert "difficulty" in txt
    assert "mempool" in txt


def test_record_sample_collects_metrics():
    seeds = {
        "a": FakeMinerClient(_sample_blocks(n=5), mempool=2),
    }
    s = np.record_sample(fake_factory(seeds), "a")
    assert s["ts"] > 0
    assert s["seed"] == "a"
    assert s["block_height"] == 1000
    assert s["difficulty"] == 87.9
    assert s["mempool_txs"] == 2


def test_append_and_load_jsonl_roundtrip(tmp_path):
    p = tmp_path / "data.jsonl"
    np.append_jsonl(p, {"ts": 1.0, "block_height": 1000})
    np.append_jsonl(p, {"ts": 2.0, "block_height": 1001})
    rows = np.load_jsonl(p)
    assert len(rows) == 2
    assert rows[0]["block_height"] == 1000
    assert rows[1]["block_height"] == 1001


def test_report_series_empty():
    assert "no recorded data" in np.report_series([])


def test_report_series_single_metric():
    rows = [{"block_height": 1000}, {"block_height": 1010}, {"block_height": 1020}]
    out = np.report_series(rows, metric="block_height")
    assert "block_height" in out
    assert "min=1000.000" in out
    assert "max=1020.000" in out


def test_report_series_trend():
    rows = [{"difficulty": 80.0}, {"difficulty": 90.0}, {"difficulty": 100.0}]
    out = np.report_series(rows)
    assert "difficulty" in out


def test_report_series_ignores_non_numeric():
    rows = [{"block_height": None}, {"block_height": "n/a"}, {"block_height": 5}]
    out = np.report_series(rows, metric="block_height")
    assert "min=5.000" in out


def test_parse_ban_log_warnings_and_bans():
    text = ("Added 2 warning(s) to 1.2.3.4: Forked (4 / 30)\n"
            "Added 10 warning(s) to 5.6.7.8: Consensus deviation too high (10 / 30)\n"
            "5.6.7.8 is banned: Consensus deviation too high\n")
    events = np.parse_ban_log(text)
    assert len(events) == 3
    assert events[0]["type"] == "warning"
    assert events[0]["reason"] == "Forked"
    assert events[0]["running"] == 4
    assert events[2]["type"] == "ban"
    assert events[2]["reason"] == "Consensus deviation too high"


def test_ban_report_empty():
    assert "no ban activity" in np.ban_report([])


def test_ban_report_groups_by_reason():
    text = ("Added 2 warning(s) to 1.1.1.1: Forked (2 / 30)\n"
            "1.2.3.4 is banned: Rollback\n"
            "5.6.7.8 is banned: Rollback\n")
    events = np.parse_ban_log(text)
    out = np.ban_report(events)
    assert "Rollback x2" in out
    assert "Consensus blockers observed" in out


def test_ban_report_unknown_reason_flagged():
    text = "9.9.9.9 is banned: Something new\n"
    events = np.parse_ban_log(text)
    out = np.ban_report(events)
    assert "unknown" in out