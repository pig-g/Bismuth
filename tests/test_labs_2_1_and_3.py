from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "labs" / "01-test-bis-workflow" / "cli.py"
LAB_2_1 = REPO_ROOT / "labs" / "02-1-sqlite-state-trace" / "README.md"
LAB_3 = REPO_ROOT / "labs" / "03-signing-identity" / "README.md"


def assert_ordered(text, commands):
    cursor = 0
    for command in commands:
        marker = f"\n{command}\n"
        found = text.find(marker, cursor)
        assert found >= 0, f"missing ordered command: {command}"
        cursor = found + len(marker)


def test_lab_2_1_guides_the_sqlite_persistence_boundary():
    text = LAB_2_1.read_text()
    assert CLI.is_file()
    assert "Lab 2.1: SQLite State Trace" in text
    assert_ordered(
        text,
        [
            "wallets",
            "mine 1",
            "send alice bob 1",
            "mempool",
            "sqltx last",
            "mine 1",
            "mempool",
            "sqltx last",
            "quit",
        ],
    )
    for concept in (
        "regmode.db",
        "transactions",
        "signature[:56]",
        "RAM mempool",
        "read-only",
        "parameterized",
        "temporary directory",
        "no mainnet",
    ):
        assert concept in text


def test_lab_3_guides_local_identity_verification_and_tampering():
    text = LAB_3.read_text()
    assert CLI.is_file()
    assert "Lab 3: Signing Identity" in text
    assert_ordered(
        text,
        [
            "wallets",
            "mine 1",
            "send alice bob 1",
            "mine 1",
            "identity last",
            "quit",
        ],
    )
    for concept in (
        "timestamp, address, recipient, amount, operation, openfield",
        "signature_valid",
        "address_matches_public_key",
        "txid_matches_signature_prefix",
        "tampered_amount_rejected",
        "public_key_sha256",
        "private key",
        "local",
        "no mainnet",
    ):
        assert concept in text


def test_existing_cli_exposes_both_follow_up_learning_commands():
    source = CLI.read_text()
    assert "sqltx <last-or-txid>" in source
    assert "identity <last-or-txid>" in source
    assert "read_ledger_transaction" in source
    assert "verify_transaction_identity" in source
