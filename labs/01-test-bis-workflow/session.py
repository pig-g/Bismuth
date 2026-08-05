#!/usr/bin/env python3
"""Run a complete local Alice/Bob test-BIS session with owned cleanup."""

from decimal import Decimal
from pathlib import Path
import secrets
import signal
from subprocess import STDOUT, Popen
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bismuthclient.bismuthclient import BismuthClient
import regnet_control

ALICE_TO_BOB = Decimal("1.00000000")
BOB_TO_ALICE = Decimal("0.25000000")
BOB_FINAL_BALANCE = Decimal("0.73988000")
SERVER = {f"{regnet_control.REGNET_HOST}:{regnet_control.REGNET_PORT}"}


class SessionInterrupted(BaseException):
    """Raised so POSIX termination signals still execute owned cleanup."""


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def install_signal_handlers():
    def interrupt(signum, _frame):
        raise SessionInterrupted(f"interrupted by signal {signum}")

    for name in ("SIGHUP", "SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), interrupt)


def create_client(wallet_file):
    return BismuthClient(servers_list=SERVER, wallet_file=str(wallet_file))


def generate_wallet(wallet_file):
    client = create_client(wallet_file)
    require(client.new_wallet(str(wallet_file)), "Could not create Bob's temporary wallet")
    client.load_wallet(str(wallet_file))
    require(client.address, "Bob's temporary wallet has no address")
    return client


def confirmed_transaction(client, txid, recipient, amount):
    transaction = client.command(command="api_gettransaction", options=[txid, True])
    require(transaction.get("txid") == txid, "Confirmed transaction was not found")
    require(transaction.get("recipient") == recipient, "Confirmed recipient changed")
    require(
        Decimal(str(transaction.get("amount"))) == amount,
        "Confirmed amount changed",
    )
    return transaction


def balance(client, address):
    response = client.command(command="balancegetjson", options=[address])
    return Decimal(str(response["balance"]))


def run_round_trip(alice_wallet, bob_wallet):
    alice = create_client(alice_wallet)
    bob = generate_wallet(bob_wallet)

    require(
        alice.command(command="regtest_generate", options=[1]) == "OK",
        "Could not mine Alice's local funding block",
    )
    alice_txid = alice.send(
        recipient=bob.address,
        amount=float(ALICE_TO_BOB),
        operation="lab1",
        data="alice-to-bob",
    )
    require(isinstance(alice_txid, str) and alice_txid, "Alice's transfer failed")
    require(
        alice.command(command="regtest_generate", options=[1]) == "OK",
        "Could not confirm Alice's transfer",
    )
    alice_transaction = confirmed_transaction(
        alice, alice_txid, bob.address, ALICE_TO_BOB
    )
    require(balance(alice, bob.address) == ALICE_TO_BOB, "Bob did not receive 1 test BIS")

    bob_txid = bob.send(
        recipient=alice.address,
        amount=float(BOB_TO_ALICE),
        operation="lab1",
        data="bob-to-alice",
    )
    require(isinstance(bob_txid, str) and bob_txid, "Bob's return transfer failed")
    require(
        alice.command(command="regtest_generate", options=[1]) == "OK",
        "Could not confirm Bob's return transfer",
    )
    bob_transaction = confirmed_transaction(
        alice, bob_txid, alice.address, BOB_TO_ALICE
    )
    bob_balance = balance(alice, bob.address)
    require(
        bob_balance == BOB_FINAL_BALANCE,
        "Bob's balance does not include the transfer and regnet fee",
    )

    return {
        "alice": alice.address,
        "bob": bob.address,
        "alice_txid": alice_txid,
        "bob_txid": bob_txid,
        "alice_block": alice_transaction["blockheight"],
        "bob_block": bob_transaction["blockheight"],
        "alice_balance": balance(alice, alice.address),
        "bob_balance": bob_balance,
    }


def run_local_session():
    if regnet_control.port_is_open():
        raise RuntimeError("Port 3030 is already occupied; refusing to touch its listener")

    process = None
    output = None
    with tempfile.TemporaryDirectory(prefix="bismuth-regnet-session-") as temporary:
        runtime_dir = Path(temporary)
        alice_wallet = runtime_dir / "alice.der"
        bob_wallet = runtime_dir / "bob.der"
        log_file = runtime_dir / "node-output.log"
        readiness_token = secrets.token_hex(16)
        command = [
            sys.executable,
            str(REPO_ROOT / "node.py"),
            "--config-custom",
            str(regnet_control.REGNET_CONFIG),
            "--regnet-dir",
            str(runtime_dir),
            "--wallet-file",
            str(alice_wallet),
            "--bind",
            regnet_control.REGNET_HOST,
            "--readiness-token",
            readiness_token,
        ]
        try:
            output = log_file.open("w")
            process = Popen(
                command,
                cwd=REPO_ROOT,
                stdout=output,
                stderr=STDOUT,
                text=True,
            )
            regnet_control.wait_for_regnet(process, readiness_token)
            return run_round_trip(alice_wallet, bob_wallet)
        finally:
            try:
                if process is not None:
                    regnet_control.stop_regnet_process(process)
            finally:
                if output is not None:
                    output.close()
            if not regnet_control.wait_for_port_closed(5):
                raise RuntimeError("Local regnet cleanup left port 3030 open")


def main():
    install_signal_handlers()
    try:
        result = run_local_session()
    except (
        KeyError,
        OSError,
        RuntimeError,
        SessionInterrupted,
        TypeError,
        ValueError,
    ) as exc:
        print(f"local regnet session: {exc}", file=sys.stderr)
        return 1

    print("LOCAL REGNET SESSION PASS")
    print(f"Alice: {result['alice']}")
    print(f"Bob: {result['bob']}")
    print(f"Alice -> Bob: {ALICE_TO_BOB:.8f} test BIS")
    print(f"Alice transaction: {result['alice_txid']}")
    print(f"Confirmed block: {result['alice_block']}")
    print(f"Bob -> Alice: {BOB_TO_ALICE:.8f} test BIS")
    print(f"Bob transaction: {result['bob_txid']}")
    print(f"Confirmed block: {result['bob_block']}")
    print(f"Alice final balance: {result['alice_balance']:.8f} test BIS")
    print(f"Bob final balance: {result['bob_balance']:.8f} test BIS")
    print("Local regnet stopped; temporary wallets and ledger removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
