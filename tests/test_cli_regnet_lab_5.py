import importlib.util
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = REPO_ROOT / "labs" / "01-test-bis-workflow" / "cli.py"
LAB_5 = REPO_ROOT / "labs" / "05-block-sqlite-structure" / "README.md"
LABS_GUIDE = REPO_ROOT / "labs" / "README.md"
ROOT_README = REPO_ROOT / "README.md"
PORT_RELEASE_TIMEOUT = 25
TXID = "AbCdEf0123456789+/AbCdEf0123456789+/AbCdEf0123456789+/Ab"
BLOCK_HASH = "c" * 56
OTHER_TXID = "Z" * 56


def load_cli_module():
    spec = importlib.util.spec_from_file_location("lab_5_cli", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_block_ledger(path):
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE transactions ("
            "block_height INTEGER, timestamp NUMERIC, address TEXT, recipient TEXT, "
            "amount NUMERIC, signature TEXT, public_key TEXT, block_hash TEXT, "
            "fee NUMERIC, reward NUMERIC, operation TEXT, openfield TEXT)"
        )
        connection.execute("CREATE TABLE misc (block_height INTEGER, difficulty TEXT)")
        connection.execute(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                2,
                "1.00",
                "a" * 56,
                "b" * 56,
                "1.00000000",
                TXID + "tail",
                "public",
                BLOCK_HASH,
                "0.01000000",
                0,
                "regnet-cli",
                "alice-to-bob",
            ),
        )
        connection.execute(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                2,
                "2.00",
                "mining",
                "a" * 56,
                0,
                "0",
                "0",
                BLOCK_HASH,
                0,
                "12.59999600",
                "0",
                "nonce",
            ),
        )
        connection.execute("INSERT INTO misc VALUES (?, ?)", (2, "16.0000000000"))


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


def assert_ordered(text, commands):
    cursor = 0
    for command in commands:
        marker = f"\n{command}\n"
        found = text.find(marker, cursor)
        assert found >= 0, f"missing ordered command: {command}"
        cursor = found + 1


def extract_exercise(text):
    exercise = text.split("<!-- exercise:start -->", 1)[1].split(
        "<!-- exercise:end -->", 1
    )[0]
    return [
        line
        for line in exercise.replace("```text", "").replace("```", "").splitlines()
        if line
    ]


def test_learner_json_removes_full_transaction_cryptographic_material(capsys):
    cli = load_cli_module()
    cli.print_json(
        {
            "txid": TXID,
            "hash": "full-signature-from-api-gettransaction",
            "pubkey": "decoded-full-public-key",
            "block_hash": BLOCK_HASH,
            "transactions": [
                {
                    "txid": TXID,
                    "signature": "full-block-signature",
                    "public_key": "encoded-full-public-key",
                }
            ],
        }
    )
    output = capsys.readouterr().out
    assert TXID in output
    assert BLOCK_HASH in output
    for secret_like in (
        "full-signature-from-api-gettransaction",
        "decoded-full-public-key",
        "full-block-signature",
        "encoded-full-public-key",
    ):
        assert secret_like not in output


def test_raw_transaction_rpc_format_is_not_available_to_learners(tmp_path):
    cli = load_cli_module()

    class QueryClient:
        address = "a" * 56

        def command(self, command, options=None):
            raise AssertionError("unsafe raw RPC should be rejected before transport")

    console = cli.RegnetCLI(
        QueryClient(),
        SimpleNamespace(address="b" * 56),
        tmp_path / "regmode.db",
    )
    try:
        console.execute(f"rpc api_gettransaction {TXID} false")
    except cli.CLIError as exc:
        assert "formatted safe output" in str(exc)
    else:
        raise AssertionError("raw positional transaction output was accepted")


def test_transaction_block_and_rpc_aliases_sanitize_cryptographic_material(
    tmp_path, capsys
):
    cli = load_cli_module()
    formatted_transaction = {
        "txid": TXID,
        "hash": "tx-command-full-signature",
        "pubkey": "tx-command-full-public-key",
        "blockheight": 2,
        "blockhash": BLOCK_HASH,
    }
    block_response = {
        "2": {
            "block_height": 2,
            "block_hash": BLOCK_HASH,
            "transactions": [
                {
                    "txid": TXID,
                    "signature": "block-command-full-signature",
                    "pubkey": "block-command-full-public-key",
                    "reward": "0",
                },
                {
                    "txid": "0",
                    "signature": "reward-full-signature",
                    "public_key": "reward-full-public-key",
                    "reward": "12.59999600",
                },
            ],
        }
    }

    class QueryClient:
        address = "a" * 56

        def __init__(self):
            self.responses = [
                ["raw existence probe"],
                formatted_transaction,
                formatted_transaction,
                block_response,
                block_response,
            ]

        def command(self, command, options=None):
            return self.responses.pop(0)

    console = cli.RegnetCLI(
        QueryClient(),
        SimpleNamespace(address="b" * 56),
        tmp_path / "regmode.db",
    )
    console.last_txid = TXID
    console.last_tx_confirmed = True
    assert console.execute("tx last") is True
    assert console.execute("block tx") is True
    assert console.execute("rpc api_getblockfromheight 2") is True

    output = capsys.readouterr().out
    for secret_like in (
        "tx-command-full-signature",
        "tx-command-full-public-key",
        "block-command-full-signature",
        "block-command-full-public-key",
        "reward-full-signature",
        "reward-full-public-key",
    ):
        assert secret_like not in output


def test_read_ledger_block_maps_rows_and_matches_rpc_identity(tmp_path):
    cli = load_cli_module()
    ledger = tmp_path / "regmode.db"
    create_block_ledger(ledger)

    result = cli.read_ledger_block(
        ledger,
        2,
        expected_block_hash=BLOCK_HASH,
        expected_transaction_count=2,
        expected_transaction_ids=[TXID],
        selected_transaction_id=TXID,
    )

    assert result == {
        "database": "temporary regnet ledger",
        "tables": ["transactions", "misc"],
        "block_height": 2,
        "block_hash": BLOCK_HASH,
        "transaction_count": 2,
        "difficulty": "16.0000000000",
        "all_rows_share_block_identity": True,
        "rpc_block_hash_matches": True,
        "rpc_transaction_count_matches": True,
        "rpc_transaction_ids_match": True,
        "selected_transaction_matches": True,
        "rpc_matches_sqlite": True,
        "rows": [
            {
                "kind": "user_transaction",
                "timestamp": "1.00",
                "txid": TXID,
                "address": "a" * 56,
                "recipient": "b" * 56,
                "amount": "1.00000000",
                "fee": "0.01000000",
                "reward": "0.00000000",
                "operation": "regnet-cli",
                "openfield": "alice-to-bob",
            },
            {
                "kind": "mining_reward",
                "timestamp": "2.00",
                "recipient": "a" * 56,
                "amount": "0.00000000",
                "fee": "0.00000000",
                "reward": "12.59999600",
                "operation": "0",
                "openfield": "nonce",
            },
        ],
    }


def test_read_ledger_block_reports_malformed_numeric_rows_as_cli_errors(tmp_path):
    cli = load_cli_module()
    ledger = tmp_path / "regmode.db"
    create_block_ledger(ledger)
    with sqlite3.connect(ledger) as connection:
        connection.execute(
            "UPDATE transactions SET reward = ? WHERE reward != 0",
            ("not-a-number",),
        )

    try:
        cli.read_ledger_block(
            ledger,
            2,
            expected_block_hash=BLOCK_HASH,
            expected_transaction_count=2,
        )
    except cli.CLIError as exc:
        assert "malformed numeric field" in str(exc)
    else:
        raise AssertionError("malformed SQLite numeric field was accepted")


def test_read_ledger_block_rejects_nonfinite_values_and_difficulty(tmp_path):
    cli = load_cli_module()
    ledger = tmp_path / "regmode.db"
    create_block_ledger(ledger)
    with sqlite3.connect(ledger) as connection:
        connection.execute(
            "UPDATE transactions SET timestamp = ? WHERE reward = 0",
            ("NaN",),
        )

    try:
        cli.read_ledger_block(
            ledger,
            2,
            expected_block_hash=BLOCK_HASH,
            expected_transaction_count=2,
        )
    except cli.CLIError as exc:
        assert "malformed numeric field" in str(exc)
    else:
        raise AssertionError("nonfinite transaction field was accepted")

    with sqlite3.connect(ledger) as connection:
        connection.execute(
            "UPDATE transactions SET timestamp = ? WHERE reward = 0",
            ("1.00",),
        )
        connection.execute("UPDATE misc SET difficulty = ?", ("Infinity",))

    try:
        cli.read_ledger_block(
            ledger,
            2,
            expected_block_hash=BLOCK_HASH,
            expected_transaction_count=2,
        )
    except cli.CLIError as exc:
        assert "malformed difficulty" in str(exc)
    else:
        raise AssertionError("nonfinite difficulty was accepted")


def test_sqlblock_tx_reports_a_missing_rpc_transaction_as_a_cli_error(tmp_path):
    cli = load_cli_module()

    class MissingTransactionClient:
        address = "a" * 56

        def command(self, command, options=None):
            assert command == "api_gettransaction"
            assert options == [TXID, True]
            return None

    console = cli.RegnetCLI(
        MissingTransactionClient(),
        SimpleNamespace(address="b" * 56),
        tmp_path / "regmode.db",
    )
    console.last_txid = TXID
    console.last_tx_confirmed = True

    try:
        console.execute("sqlblock tx")
    except cli.CLIError as exc:
        assert "RPC returned no confirmed transaction" in str(exc)
    else:
        raise AssertionError("missing transaction RPC response escaped the prompt")


def test_block_tx_reports_a_missing_rpc_transaction_as_a_cli_error(tmp_path):
    cli = load_cli_module()

    class MissingTransactionClient:
        address = "a" * 56

        def command(self, command, options=None):
            assert command == "api_gettransaction"
            return None

    console = cli.RegnetCLI(
        MissingTransactionClient(),
        SimpleNamespace(address="b" * 56),
        tmp_path / "regmode.db",
    )
    console.last_txid = TXID
    console.last_tx_confirmed = True

    try:
        console.execute("block tx")
    except cli.CLIError as exc:
        assert "RPC returned no confirmed transaction" in str(exc)
    else:
        raise AssertionError("missing transaction RPC response escaped block tx")


def test_sqlblock_tx_rejects_rpc_and_sqlite_transaction_identity_mismatch(tmp_path):
    cli = load_cli_module()
    ledger = tmp_path / "regmode.db"
    create_block_ledger(ledger)

    class QueryClient:
        address = "a" * 56

        def __init__(self):
            self.responses = [
                {
                    "txid": TXID,
                    "blockheight": 2,
                    "blockhash": BLOCK_HASH,
                },
                {
                    "2": {
                        "block_height": 2,
                        "block_hash": BLOCK_HASH,
                        "transactions": [
                            {"txid": OTHER_TXID, "reward": "0"},
                            {"txid": "0", "reward": "12.59999600"},
                        ],
                    }
                },
            ]

        def command(self, command, options=None):
            return self.responses.pop(0)

    console = cli.RegnetCLI(
        QueryClient(), SimpleNamespace(address="b" * 56), ledger
    )
    console.last_txid = TXID
    console.last_tx_confirmed = True

    try:
        console.execute("sqlblock tx")
    except cli.CLIError as exc:
        assert "selected transaction" in str(exc)
    else:
        raise AssertionError("RPC block omitted the selected transaction")


def test_rpc_block_rejects_a_transaction_with_no_reward_field(tmp_path):
    cli = load_cli_module()

    class QueryClient:
        address = "a" * 56

        def command(self, command, options=None):
            return {
                "2": {
                    "block_height": 2,
                    "block_hash": BLOCK_HASH,
                    "transactions": [{"txid": TXID}],
                }
            }

    console = cli.RegnetCLI(
        QueryClient(),
        SimpleNamespace(address="b" * 56),
        tmp_path / "regmode.db",
    )
    try:
        console.query_rpc_block(2)
    except cli.CLIError as exc:
        assert "malformed reward" in str(exc)
    else:
        raise AssertionError("RPC transaction without reward was accepted")


def test_sqlblock_tx_rejects_malformed_transaction_and_block_identity(tmp_path):
    cli = load_cli_module()
    valid_transaction = {
        "txid": TXID,
        "blockheight": 2,
        "blockhash": BLOCK_HASH,
    }
    valid_block = {
        "2": {
            "block_height": 2,
            "block_hash": BLOCK_HASH,
            "transactions": [
                {"txid": TXID, "reward": "0"},
                {"txid": "0", "reward": "12.59999600"},
            ],
        }
    }
    cases = (
        ([{**valid_transaction, "txid": OTHER_TXID}], "transaction ID"),
        ([{**valid_transaction, "blockheight": "2"}], "block height"),
        ([{**valid_transaction, "blockhash": "invalid"}], "block hash"),
        (
            [valid_transaction, {"2": {**valid_block["2"], "block_height": 3}}],
            "requested height",
        ),
        (
            [
                valid_transaction,
                {"2": {**valid_block["2"], "block_hash": "d" * 56}},
            ],
            "confirmed transaction",
        ),
    )

    for responses, message in cases:
        class QueryClient:
            address = "a" * 56

            def __init__(self):
                self.responses = list(responses)

            def command(self, command, options=None):
                return self.responses.pop(0)

        console = cli.RegnetCLI(
            QueryClient(),
            SimpleNamespace(address="b" * 56),
            tmp_path / "regmode.db",
        )
        console.last_txid = TXID
        console.last_tx_confirmed = True
        try:
            console.execute("sqlblock tx")
        except cli.CLIError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"malformed identity was accepted: {message}")


def test_sqlblock_tx_resolves_the_confirmed_block_and_rejects_paths(tmp_path, capsys):
    cli = load_cli_module()
    ledger = tmp_path / "regmode.db"
    create_block_ledger(ledger)

    class QueryClient:
        address = "a" * 56

        def command(self, command, options=None):
            if command == "api_gettransaction":
                assert options == [TXID, True]
                return {"txid": TXID, "blockheight": 2, "blockhash": BLOCK_HASH}
            if command == "api_getblockfromheight":
                assert options == [2]
                return {
                    "2": {
                        "block_height": 2,
                        "block_hash": BLOCK_HASH,
                        "transactions": [
                            {"txid": TXID, "reward": "0"},
                            {"reward": "12.59999600"},
                        ],
                    }
                }
            raise AssertionError(f"unexpected RPC: {command} {options}")

    console = cli.RegnetCLI(
        QueryClient(),
        SimpleNamespace(address="b" * 56),
        ledger,
    )
    console.last_txid = TXID
    console.last_tx_confirmed = True

    assert console.execute("sqlblock tx") is True
    output = capsys.readouterr().out
    assert '"rpc_matches_sqlite": true' in output
    assert '"kind": "user_transaction"' in output
    assert '"kind": "mining_reward"' in output
    assert str(ledger) not in output

    for command in (
        "sqlblock",
        "sqlblock tx extra",
        "sqlblock ../../mainnet.db",
        "sqlblock 0",
    ):
        try:
            console.execute(command)
        except cli.CLIError:
            pass
        else:
            raise AssertionError(f"unsafe sqlblock command accepted: {command}")


def test_lab_5_guides_block_to_sqlite_structure():
    text = LAB_5.read_text()
    assert "Lab 5: Block-to-SQLite Structure" in text
    commands = [
        "wallets",
        "mine 1",
        "send alice bob 1",
        "mine 1",
        "sqlblock tx",
        "quit",
    ]
    assert extract_exercise(text) == commands
    assert_ordered(text, commands)
    for concept in (
        "same `block_height`",
        "same `block_hash`",
        "transactions",
        "misc",
        "mining reward",
        "difficulty",
        "read-only",
        "parameterized",
        "no mainnet",
        "not an arbitrary SQL",
    ):
        assert concept in text


def test_external_labs_guide_covers_download_setup_and_labs_zero_through_eight():
    text = LABS_GUIDE.read_text()
    for concept in (
        "Bismuth Labs 0–8",
        "https://github.com/pig-g/Bismuth.git",
        "hermes/lab-1-test-bis-workflow",
        "Download ZIP",
        "Python 3.11",
        "macOS",
        "Linux",
        "./labs/00-regnet-first-run/verify.sh",
        ".venv/bin/python ./labs/01-test-bis-workflow/cli.py",
        "Terminal",
        "regnet>",
        "port `3030`",
        "no mainnet",
        "private key",
        "quit",
    ):
        assert concept in text
    for relative in (
        "00-regnet-first-run/README.md",
        "01-test-bis-workflow/README.md",
        "02-transaction-lifecycle/README.md",
        "02-1-sqlite-state-trace/README.md",
        "03-signing-identity/README.md",
        "04-competing-spend-rejection/README.md",
        "05-block-sqlite-structure/README.md",
        "06-difficulty-simulation/README.md",
        "07-fork-selection/README.md",
        "08-tokens-no-vm/README.md",
    ):
        assert f"]({relative})" in text


def test_repository_readme_links_the_newcomer_labs_guide():
    text = ROOT_README.read_text()
    assert "[Practical Labs 0–8](labs/README.md)" in text


def test_lab_5_exact_real_process_exercise_maps_one_confirmed_block():
    assert wait_for_port_closed(3030, timeout=PORT_RELEASE_TIMEOUT)
    exercise = "\n".join(
        (
            "wallets",
            "mine 1",
            "send alice bob 1",
            "mine 1",
            "sqlblock tx",
            "quit",
            "",
        )
    )

    result = subprocess.run(
        [sys.executable, str(CLI_PATH)],
        cwd="/tmp",
        input=exercise,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    txids = re.findall(r"alice -> bob: 1\.00000000 test BIS\ntransaction: (\S+)", result.stdout)
    assert len(txids) == 1
    txid = txids[0]
    assert result.stdout.count(f'"txid": "{txid}"') >= 1
    assert '"rpc_matches_sqlite": true' in result.stdout
    assert '"rpc_block_hash_matches": true' in result.stdout
    assert '"rpc_transaction_count_matches": true' in result.stdout
    assert '"rpc_transaction_ids_match": true' in result.stdout
    assert '"selected_transaction_matches": true' in result.stdout
    assert '"kind": "user_transaction"' in result.stdout
    assert '"kind": "mining_reward"' in result.stdout
    assert re.search(r'"difficulty": "[0-9.]+"', result.stdout)
    assert '"signature":' not in result.stdout
    assert '"public_key":' not in result.stdout
    assert "Regnet stopped; temporary wallets and ledger removed." in result.stdout
    assert "private" not in result.stdout.lower()
    assert wait_for_port_closed(3030, timeout=PORT_RELEASE_TIMEOUT)
