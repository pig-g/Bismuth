import base64
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace

from Cryptodome.Hash import SHA
from Cryptodome.PublicKey import RSA
from Cryptodome.Signature import PKCS1_v1_5


REPO_ROOT = Path(__file__).resolve().parents[1]
LAB_DIR = REPO_ROOT / "labs" / "01-test-bis-workflow"
SESSION_PATH = LAB_DIR / "session.py"
CLI_PATH = LAB_DIR / "cli.py"
OWNED_CLEANUP_TIMEOUT = 25
OWNED_STARTUP_TIMEOUT = 30


def port_is_open(port):
    with socket.socket() as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def terminate_owned_program(process):
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=OWNED_CLEANUP_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_owned_program(program, *, input_text, timeout):
    process = subprocess.Popen(
        [sys.executable, str(program)],
        cwd="/tmp",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        process.send_signal(signal.SIGTERM)
        try:
            process.communicate(timeout=OWNED_CLEANUP_TIMEOUT)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)
        raise
    return subprocess.CompletedProcess(
        process.args, process.returncode, stdout=stdout, stderr=stderr
    )


def load_cli_module():
    spec = importlib.util.spec_from_file_location("lab_1_cli", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_session_module():
    spec = importlib.util.spec_from_file_location("lab_1_session", SESSION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_signal_exception_bypasses_dependency_exception_handlers():
    cli = load_cli_module()
    session = load_session_module()
    assert issubclass(cli.SessionInterrupted, BaseException)
    assert not issubclass(cli.SessionInterrupted, Exception)
    assert issubclass(session.SessionInterrupted, BaseException)
    assert not issubclass(session.SessionInterrupted, Exception)


def test_cli_accepts_signature_derived_transaction_ids_without_weakening_hash_validation():
    cli = load_cli_module()
    txid = "AbCdEf0123456789+/AbCdEf0123456789+/AbCdEf0123456789+/Ab"
    assert len(txid) == 56

    cli.validate_rpc_options("api_gettransaction", [txid, True])

    for invalid_txid in (txid[:-1], txid[:-1] + "%", "a" * 57):
        try:
            cli.validate_rpc_options("api_gettransaction", [invalid_txid, True])
        except cli.CLIError:
            pass
        else:
            raise AssertionError(f"accepted malformed transaction ID: {invalid_txid!r}")
    try:
        cli.validate_rpc_options("api_getblockfromhash", [txid])
    except cli.CLIError:
        pass
    else:
        raise AssertionError("accepted a non-hex block hash")


def test_cli_adds_signature_derived_transaction_ids_to_ledger_rows():
    cli = load_cli_module()
    txid = "AbCdEf0123456789+/AbCdEf0123456789+/AbCdEf0123456789+/Ab"
    rows = cli.add_transaction_ids(
        [{"signature": txid + "signature-tail"}, {"signature": "0"}]
    )

    assert rows[0]["txid"] == txid
    assert "txid" not in rows[1]


def test_cli_reads_only_the_exact_transaction_from_temporary_ledger(tmp_path):
    cli = load_cli_module()
    ledger = tmp_path / "regmode.db"
    txid = "AbCdEf0123456789+/AbCdEf0123456789+/AbCdEf0123456789+/Ab"
    with sqlite3.connect(ledger) as connection:
        connection.execute(
            "CREATE TABLE transactions ("
            "block_height INTEGER, timestamp NUMERIC, address TEXT, recipient TEXT, "
            "amount NUMERIC, signature TEXT, public_key TEXT, block_hash TEXT, "
            "fee NUMERIC, reward NUMERIC, operation TEXT, openfield TEXT)"
        )
        connection.execute(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (2, "1.00", "a" * 56, "b" * 56, "1.00000000", txid + "tail", "public", "c" * 56, "0.01000000", 0, "regnet-cli", "alice-to-bob"),
        )

    assert cli.read_ledger_transaction(ledger, "Z" * 56) == {
        "database": "temporary regnet ledger",
        "table": "transactions",
        "row_found": False,
        "txid": "Z" * 56,
    }
    assert cli.read_ledger_transaction(ledger, txid) == {
        "database": "temporary regnet ledger",
        "table": "transactions",
        "row_found": True,
        "txid": txid,
        "block_height": 2,
        "timestamp": 1,
        "address": "a" * 56,
        "recipient": "b" * 56,
        "amount": 1,
        "operation": "regnet-cli",
        "openfield": "alice-to-bob",
    }


def test_sqltx_last_uses_the_owned_temporary_ledger(tmp_path, capsys):
    cli = load_cli_module()
    ledger = tmp_path / "regmode.db"
    txid = "AbCdEf0123456789+/AbCdEf0123456789+/AbCdEf0123456789+/Ab"
    with sqlite3.connect(ledger) as connection:
        connection.execute(
            "CREATE TABLE transactions ("
            "block_height INTEGER, timestamp NUMERIC, address TEXT, recipient TEXT, "
            "amount NUMERIC, signature TEXT, public_key TEXT, block_hash TEXT, "
            "fee NUMERIC, reward NUMERIC, operation TEXT, openfield TEXT)"
        )

    console = cli.RegnetCLI(
        SimpleNamespace(address="a" * 56),
        SimpleNamespace(address="b" * 56),
        ledger,
    )
    console.last_txid = txid

    assert console.execute("sqltx last") is True
    output = capsys.readouterr().out
    assert '"database": "temporary regnet ledger"' in output
    assert '"row_found": false' in output
    assert str(ledger) not in output

    for command in ("sqltx", "sqltx last extra", "sqltx ../../mainnet.db"):
        try:
            console.execute(command)
        except cli.CLIError:
            pass
        else:
            raise AssertionError(f"unsafe sqltx command accepted: {command}")

    try:
        cli.read_ledger_transaction(tmp_path / "missing.db", txid)
    except cli.CLIError as exc:
        assert "temporary ledger query failed" in str(exc)
    else:
        raise AssertionError("missing temporary ledger did not raise CLIError")


def test_cli_verifies_identity_and_rejects_a_tampered_amount(tmp_path, capsys):
    cli = load_cli_module()
    key = RSA.generate(1024)
    public_key = key.publickey().export_key().decode("utf-8")
    encoded_public_key = base64.b64encode(public_key.encode()).decode()
    address = hashlib.sha224(public_key.encode()).hexdigest()
    timestamp = "1.00"
    recipient = "b" * 56
    amount = "1.00000000"
    operation = "regnet-cli"
    openfield = "alice-to-bob"
    buffer = str(
        (timestamp, address, recipient, amount, operation, openfield)
    ).encode()
    signature = base64.b64encode(PKCS1_v1_5.new(key).sign(SHA.new(buffer))).decode()
    raw_transaction = [
        2,
        timestamp,
        address,
        recipient,
        amount,
        signature,
        encoded_public_key,
        "c" * 56,
        "0.01000000",
        0,
        operation,
        openfield,
    ]

    result = cli.verify_transaction_identity(raw_transaction, signature[:56])

    assert result == {
        "signature_valid": True,
        "address_matches_public_key": True,
        "txid_matches_signature_prefix": True,
        "tampered_amount_rejected": True,
        "public_key_sha256": hashlib.sha256(public_key.encode()).hexdigest(),
    }
    rendered = str(result)
    assert signature not in rendered
    assert public_key not in rendered
    mismatch = cli.verify_transaction_identity(raw_transaction, "Z" * 56)
    assert mismatch["txid_matches_signature_prefix"] is False

    class ConfirmedClient:
        def __init__(self, client_address):
            self.address = client_address

        def command(self, command, options):
            assert command == "api_gettransaction"
            assert options == [signature[:56], False]
            return raw_transaction

    console = cli.RegnetCLI(
        ConfirmedClient(address),
        SimpleNamespace(address=recipient),
        tmp_path / "regmode.db",
    )
    console.last_txid = signature[:56]
    console.last_tx_confirmed = True
    assert console.execute("identity last") is True
    output = capsys.readouterr().out
    assert '"signature_valid": true' in output
    assert '"address_matches_public_key": true' in output
    assert '"tampered_amount_rejected": true' in output
    assert signature not in output
    assert public_key not in output


def test_harness_allows_the_full_bounded_owned_cleanup_window():
    node_term_wait = 10
    node_kill_wait = 5
    port_close_wait = 5
    assert OWNED_CLEANUP_TIMEOUT > node_term_wait + node_kill_wait + port_close_wait


def test_harness_uses_graceful_owned_cleanup_before_force_kill():
    events = []

    class SlowProcess:
        def poll(self):
            return None

        def send_signal(self, sent_signal):
            events.append(("signal", sent_signal))

        def wait(self, timeout):
            events.append(("wait", timeout))
            if timeout == OWNED_CLEANUP_TIMEOUT:
                raise subprocess.TimeoutExpired("owned", timeout)

        def kill(self):
            events.append(("kill", None))

    terminate_owned_program(SlowProcess())

    assert events == [
        ("signal", signal.SIGTERM),
        ("wait", OWNED_CLEANUP_TIMEOUT),
        ("kill", None),
        ("wait", 5),
    ]


def test_local_session_runs_round_trip_and_cleans_up_regnet():
    assert not port_is_open(3030)

    result = run_owned_program(
        SESSION_PATH,
        input_text="",
        timeout=45,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "LOCAL REGNET SESSION PASS" in result.stdout
    assert "Alice -> Bob: 1.00000000 test BIS" in result.stdout
    assert "Bob -> Alice: 0.25000000 test BIS" in result.stdout
    assert "Alice transaction:" in result.stdout
    assert "Bob transaction:" in result.stdout
    assert "Bob final balance: 0.73988000 test BIS" in result.stdout
    assert "private" not in result.stdout.lower()
    assert not port_is_open(3030)


def test_local_session_termination_cleans_up_regnet(tmp_path):
    assert not port_is_open(3030)
    output_path = tmp_path / "session-output.log"
    with output_path.open("w+") as output:
        process = subprocess.Popen(
            [sys.executable, str(SESSION_PATH)],
            cwd="/tmp",
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            deadline = time.monotonic() + OWNED_STARTUP_TIMEOUT
            while time.monotonic() < deadline and not port_is_open(3030):
                assert process.poll() is None
                time.sleep(0.05)
            assert port_is_open(3030)
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=OWNED_CLEANUP_TIMEOUT)
        finally:
            terminate_owned_program(process)
        output.seek(0)
        text = output.read()

    assert process.returncode != 0
    assert "LOCAL REGNET SESSION PASS" not in text
    assert not port_is_open(3030)


def test_regnet_cli_runs_real_rpc_exercise_and_cleans_up():
    assert not port_is_open(3030)
    exercise = "\n".join(
        (
            "wallets",
            "mine 1",
            "block last",
            "send alice bob 1",
            "mempool",
            "sqltx last",
            "tx last",
            "block tx",
            "mine 1",
            "mempool",
            "sqltx last",
            "identity last",
            "tx last",
            "block tx",
            "blocks 10",
            "balance bob",
            "ledger bob 10",
            "rpc api_getblockfromheight",
            "rpc api_getaddressinfo {}",
            "rpc api_getbalance not-a-list -99",
            "rpc api_getblockfromheight -7",
            "rpc addlistlimjson not-an-address -999",
            "rpc api_getconfig",
            "rpc api_clearmempool",
            "quit",
            "",
        )
    )

    result = run_owned_program(
        CLI_PATH,
        input_text=exercise,
        timeout=45,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    txid_match = re.search(r"transaction: (\S+)", result.stdout)
    assert txid_match is not None
    txid = txid_match.group(1)
    assert "BISMUTH REGNET CLI" in result.stdout
    assert "alice:" in result.stdout
    assert "bob:" in result.stdout
    assert "RPC regtest_generate" in result.stdout
    assert "alice -> bob: 1.00000000 test BIS" in result.stdout
    assert "last transaction is unconfirmed; run mine 1 first" in result.stdout
    assert "last sent transaction is unconfirmed; run mine 1 first" in result.stdout
    assert '"balance": "1.00000000"' in result.stdout
    assert f'RPC api_gettransaction ["{txid}", true]' in result.stdout
    assert "RPC mpgetjson []" in result.stdout
    assert result.stdout.count('"database": "temporary regnet ledger"') == 2
    assert '"row_found": false' in result.stdout
    assert '"row_found": true' in result.stdout
    assert '"signature_valid": true' in result.stdout
    assert '"address_matches_public_key": true' in result.stdout
    assert '"txid_matches_signature_prefix": true' in result.stdout
    assert '"tampered_amount_rejected": true' in result.stdout
    assert '"public_key_sha256":' in result.stdout
    assert result.stdout.count(f'"txid": "{txid}"') >= 4
    assert '"transactions":' in result.stdout
    assert "BLOCK HISTORY" in result.stdout
    assert "height 1" in result.stdout
    assert "RPC api_getblockfromheight expects 1 argument(s)" in result.stdout
    assert "api_getaddressinfo requires a 56-character" in result.stdout
    assert "api_getbalance requires a JSON list" in result.stdout
    assert "api_getblockfromheight requires a positive integer" in result.stdout
    assert "addlistlimjson requires a 56-character" in result.stdout
    assert '"readiness_token": "[REDACTED]"' in result.stdout
    assert "RPC api_clearmempool is not allowed" in result.stdout
    assert "private" not in result.stdout.lower()
    assert "Regnet stopped; temporary wallets and ledger removed." in result.stdout
    assert not port_is_open(3030)


def test_regnet_cli_refuses_and_preserves_foreign_listener():
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 3030))
    listener.listen()
    try:
        result = subprocess.run(
            [sys.executable, str(CLI_PATH)],
            cwd="/tmp",
            input="quit\n",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert listener.getsockname()[1] == 3030
    finally:
        listener.close()

    assert result.returncode != 0
    assert "Port 3030 is already occupied" in result.stderr


def test_regnet_cli_interrupt_cleans_owned_node(tmp_path):
    assert not port_is_open(3030)
    output_path = tmp_path / "cli-output.log"
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    with output_path.open("w+") as output:
        process = subprocess.Popen(
            [sys.executable, str(CLI_PATH)],
            cwd="/tmp",
            stdin=subprocess.PIPE,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
        )
        try:
            deadline = time.monotonic() + OWNED_STARTUP_TIMEOUT
            while time.monotonic() < deadline:
                assert process.poll() is None
                if "regnet> " in output_path.read_text():
                    break
                time.sleep(0.05)
            assert "regnet> " in output_path.read_text()
            assert port_is_open(3030)
            process.send_signal(signal.SIGINT)
            process.wait(timeout=OWNED_CLEANUP_TIMEOUT)
        finally:
            terminate_owned_program(process)
        output.seek(0)
        text = output.read()

    assert process.returncode != 0
    assert "interrupted by signal" in text
    assert not port_is_open(3030)
