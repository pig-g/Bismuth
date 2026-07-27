import re
import socket
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "labs" / "01-test-bis-workflow" / "cli.py"
LAB_4 = REPO_ROOT / "labs" / "04-competing-spend-rejection" / "README.md"
PORT_RELEASE_TIMEOUT = 25


def port_is_open(port):
    with socket.socket() as candidate:
        candidate.settimeout(0.2)
        return candidate.connect_ex(("127.0.0.1", port)) == 0


def wait_for_port_closed(port, timeout):
    deadline = time.monotonic() + timeout
    while port_is_open(port):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def test_port_preflight_waits_for_close_without_terminating_a_listener(monkeypatch):
    states = iter((True, True, False))
    sleeps = []
    monkeypatch.setattr("test_cli_regnet_lab_4.port_is_open", lambda _port: next(states))
    monkeypatch.setattr("test_cli_regnet_lab_4.time.sleep", sleeps.append)

    assert wait_for_port_closed(3030, timeout=1) is True
    assert sleeps == [0.05, 0.05]


def assert_ordered(text, commands):
    cursor = 0
    for command in commands:
        marker = f"\n{command}\n"
        found = text.find(marker, cursor)
        assert found >= 0, f"missing ordered command: {command}"
        cursor = found + len(marker)


def test_lab_4_explains_account_model_competing_spend_rejection():
    text = LAB_4.read_text()
    assert "Lab 4: Competing Spend Rejection" in text
    assert_ordered(
        text,
        [
            "wallets",
            "mine 1",
            "balance alice",
            "send alice bob 10",
            "mempool",
            "send alice bob 10",
            "mempool",
            "tx last",
            "mine 1",
            "mempool",
            "tx last",
            "balance bob",
            "ledger bob 10",
            "quit",
        ],
    )
    for concept in (
        "account model",
        "not a UTXO",
        "debit_mempool",
        "Cannot afford to pay fees",
        "first transaction",
        "last transaction",
        "one confirmed transfer",
        "no mainnet",
        "private key",
    ):
        assert concept in text


def test_lab_4_exact_real_process_exercise_rejects_only_the_competing_spend():
    assert wait_for_port_closed(3030, timeout=PORT_RELEASE_TIMEOUT)
    exercise = "\n".join(
        (
            "wallets",
            "mine 1",
            "balance alice",
            "send alice bob 10",
            "mempool",
            "send alice bob 10",
            "mempool",
            "tx last",
            "mine 1",
            "mempool",
            "tx last",
            "balance bob",
            "ledger bob 10",
            "quit",
            "",
        )
    )

    result = subprocess.run(
        [sys.executable, str(CLI)],
        cwd="/tmp",
        input=exercise,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    accepted = re.findall(r"alice -> bob: 10\.00000000 test BIS\ntransaction: (\S+)", result.stdout)
    assert len(accepted) == 1
    txid = accepted[0]
    assert result.stdout.count("transaction was rejected") == 1
    assert result.stdout.count("Mempool: Cannot afford to pay fees") == 1
    assert result.stdout.count(f'"txid": "{txid}"') >= 3
    assert "last transaction is unconfirmed; run mine 1 first" in result.stdout
    assert f'RPC api_gettransaction ["{txid}", true]' in result.stdout
    assert '"balance": "10.00000000"' in result.stdout
    assert "Regnet stopped; temporary wallets and ledger removed." in result.stdout
    assert "private" not in result.stdout.lower()
    assert wait_for_port_closed(3030, timeout=PORT_RELEASE_TIMEOUT)
