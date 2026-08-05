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