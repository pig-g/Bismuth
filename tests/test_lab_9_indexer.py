from pathlib import Path
import importlib.util
import sqlite3
import os
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
LAB_DIR = REPO_ROOT / "labs" / "09-consensus-vs-meaning"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "indexer_prototype", str(LAB_DIR / "indexer_prototype.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_db():
    con = sqlite3.connect(":memory:")
    return con


def test_indexer_derives_meaning_without_touching_consensus_rows():
    m = load_module()
    con = make_db()
    m.build_raw_ledger(con)
    consensus_rows = m.consensus_layer(con)
    # consensus layer preserves the opaque strings verbatim
    ops = [operation for (_, _, operation, _) in consensus_rows]
    assert "alias:register" in ops
    assert "token:issue" in ops
    assert "token:transfer" in ops

    result = m.new_indexer_prototype(con)
    assert "gem" in result
    assert result["gem"]["mentions"] == 4
    assert result["gem"]["distinct_addresses"] == 4
    assert result["gem"]["temperature"] > 0


def test_extending_index_does_not_change_raw_block_data():
    m = load_module()
    con = make_db()
    m.build_raw_ledger(con)
    before = list(con.execute("SELECT * FROM txns ORDER BY block_height, signature"))
    # run the new indexer
    m.new_indexer_prototype(con)
    after = list(con.execute("SELECT * FROM txns ORDER BY block_height, signature"))
    assert before == after  # meaning layer must not mutate consensus rows


def test_consensus_layer_treats_openfield_opaque():
    m = load_module()
    con = make_db()
    m.build_raw_ledger(con)
    rows = m.consensus_layer(con)
    # openfield strings pass through unparsed
    fields = [openfield for (_, _, _, openfield) in rows]
    assert "alice" in fields
    assert "gem:1000" in fields
    assert "merkle-ish" in fields


def test_main_runs():
    m = load_module()
    m.main()
