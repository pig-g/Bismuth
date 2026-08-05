from pathlib import Path
import importlib.util
import os
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
LAB_DIR = REPO_ROOT / "labs" / "10-insecure-defaults"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "threat_model", str(LAB_DIR / "threat_model.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_threat_model_covers_key_custody_risks():
    m = load_module()
    names = [t.name for t in m.THREATS]
    assert "private-key-to-node signing" in names
    assert "key generation on the node" in names
    assert "mempool wipe" in names
    # every threat has a safe fix
    for t in m.THREATS:
        assert t.safe_guidance.strip()
        assert t.severity in ("High", "Medium", "Low")


def test_high_severity_matches_private_key_send():
    m = load_module()
    priv = next(t for t in m.THREATS if t.name == "private-key-to-node signing")
    assert priv.severity == "High"
    assert "never send a private key to a node" in priv.safe_guidance.lower()


def test_scanner_flags_real_source_private_key_pattern():
    m = load_module()
    # simulate a tiny python file containing the risky pattern
    with tempfile.TemporaryDirectory() as tmp:
        victim = os.path.join(tmp, "commands.py")
        with open(victim, "w") as fh:
            fh.write("def txsend(socket, a):\n")
            fh.write("    remote_tx_privkey = a  # forward key\n")
            fh.write("    connections.send(s, remote_tx_privkey)\n")
        m.scan_file(victim, m.THREATS)
        priv = next(t for t in m.THREATS if t.name == "private-key-to-node signing")
        hit_lines = priv.hit_lines
        assert any(p == victim for (p, _, _) in hit_lines)


def test_scanner_reports_nothing_on_clean_file():
    m = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        clean = os.path.join(tmp, "clean.py")
        with open(clean, "w") as fh:
            fh.write("def f():\n    return 1\n")
        m.scan_file(clean, m.THREATS)
        # concrete check: the private-key threat must not match a clean file
        priv = next(t for t in m.THREATS if t.name == "private-key-to-node signing")
        assert not any(p == clean for (p, _, _) in priv.hit_lines)


def test_scanner_preserves_prior_hits_between_files_safely():
    m = load_module()
    # hit_lines accumulate; this is by design (aggregate report). ensure no crash
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "a.py")
        with open(p, "w") as fh:
            fh.write("remote_tx_privkey = 1\n")
        m.scan_file(p, m.THREATS)


def test_main_runs():
    m = load_module()
    m.main()
